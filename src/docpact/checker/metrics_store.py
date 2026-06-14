"""SQLite-backed violation tracking and trend detection. Zero dependencies."""

from __future__ import annotations

import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from docpact.checker.models import Hallazgo, ResultadoProyecto

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS snapshots ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,"
    "total_files INTEGER NOT NULL, total_fns INTEGER NOT NULL,"
    "errors INTEGER NOT NULL, warnings INTEGER NOT NULL, score INTEGER NOT NULL);"
    "CREATE TABLE IF NOT EXISTS violations ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),"
    "rule_id TEXT NOT NULL, severity TEXT NOT NULL,"
    "file TEXT NOT NULL, function TEXT NOT NULL,"
    "line INTEGER NOT NULL, message TEXT NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_viol_rule ON violations(rule_id);"
    "CREATE INDEX IF NOT EXISTS idx_viol_func ON violations(function);"
    "CREATE INDEX IF NOT EXISTS idx_viol_snap ON violations(snapshot_id);"
    "CREATE TABLE IF NOT EXISTS daily_metrics ("
    "day TEXT NOT NULL, rule_id TEXT NOT NULL, count INTEGER NOT NULL,"
    "PRIMARY KEY (day, rule_id));"
)


def _connect(project_root: Path) -> sqlite3.Connection:
    db = project_root / ".docpact" / "metrics.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), isolation_level="DEFERRED")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return conn


def record_run(result: ResultadoProyecto, project_root: Path | str = ".") -> int:
    """Record a verification run. Returns the snapshot id."""
    project_root = Path(project_root)
    now = time.time()
    day = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")

    hallazgos: list[Hallazgo] = []
    for a in result.archivos:
        for fn in a.funciones:
            hallazgos.extend(fn.hallazgos)

    errors = sum(1 for h in hallazgos if h.tipo == "error")
    warnings = len(hallazgos) - errors

    conn = _connect(project_root)
    try:
        sid = conn.execute(
            "INSERT INTO snapshots VALUES (NULL,?,?,?,?,?,?)",
            (now, result.total_archivos, result.total_funciones,
             errors, warnings, result.calcular_score()),
        ).lastrowid

        conn.executemany(
            "INSERT INTO violations VALUES (NULL,?,?,?,?,?,?,?)",
            [(sid, h.campo, h.tipo, h.archivo, h.funcion, h.linea, h.mensaje)
             for h in hallazgos],
        )

        daily: dict[str, int] = defaultdict(int)
        for h in hallazgos:
            daily[h.campo] += 1
        for rule_id, count in daily.items():
            conn.execute(
                "INSERT INTO daily_metrics VALUES (?,?,?) "
                "ON CONFLICT(day, rule_id) DO UPDATE SET count = count + excluded.count",
                (day, rule_id, count),
            )

        conn.commit()
        return sid
    finally:
        conn.close()


def get_trends(rule_id: str, days: int = 30, project_root: Path | str = ".") -> dict[str, Any]:
    """Trend direction for a rule: increasing / decreasing / stable."""
    project_root = Path(project_root)
    utcnow = datetime.now(timezone.utc)
    cutoff = (utcnow - timedelta(days=days)).strftime("%Y-%m-%d")
    mid = (utcnow - timedelta(days=days // 2)).strftime("%Y-%m-%d")

    conn = _connect(project_root)
    try:
        rows = conn.execute(
            "SELECT day, count FROM daily_metrics "
            "WHERE rule_id=? AND day>=? ORDER BY day", (rule_id, cutoff),
        ).fetchall()

        if not rows:
            return {"rule_id": rule_id, "direction": "stable",
                    "current_avg": 0, "previous_avg": 0, "data_points": 0}

        older = [r["count"] for r in rows if r["day"] < mid]
        newer = [r["count"] for r in rows if r["day"] >= mid]
        prev_avg = sum(older) / len(older) if older else 0
        curr_avg = sum(newer) / len(newer) if newer else 0

        if curr_avg > prev_avg * 1.15:
            direction = "increasing"
        elif curr_avg < prev_avg * 0.85:
            direction = "decreasing"
        else:
            direction = "stable"

        return {"rule_id": rule_id, "direction": direction,
                "current_avg": round(curr_avg, 2), "previous_avg": round(prev_avg, 2),
                "data_points": len(rows)}
    finally:
        conn.close()


def get_top_violators(top_n: int = 10, days: int = 30,
                      project_root: Path | str = ".") -> list[dict[str, Any]]:
    """Functions with the most violations in the last N days."""
    project_root = Path(project_root)
    cutoff_ts = time.time() - days * 86400

    conn = _connect(project_root)
    try:
        rows = conn.execute(
            "SELECT v.function, v.file, COUNT(*) as violations, "
            "SUM(v.severity='error') as errors, "
            "SUM(v.severity='warning') as warnings "
            "FROM violations v JOIN snapshots s ON v.snapshot_id=s.id "
            "WHERE s.ts>=? GROUP BY v.function, v.file "
            "ORDER BY violations DESC LIMIT ?",
            (cutoff_ts, top_n),
        ).fetchall()

        return [{"function": r["function"], "file": r["file"],
                 "violations": r["violations"],
                 "errors": r["errors"], "warnings": r["warnings"]}
                for r in rows]
    finally:
        conn.close()


def get_violation_history(rule_id: str, days: int = 30,
                          project_root: Path | str = ".") -> list[dict[str, Any]]:
    """Daily violation counts for a rule over the last N days."""
    project_root = Path(project_root)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    conn = _connect(project_root)
    try:
        rows = conn.execute(
            "SELECT day, count FROM daily_metrics "
            "WHERE rule_id=? AND day>=? ORDER BY day", (rule_id, cutoff),
        ).fetchall()
        return [{"day": r["day"], "count": r["count"]} for r in rows]
    finally:
        conn.close()

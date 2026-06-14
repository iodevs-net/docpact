"""Tests for docpact.checker.metrics_store."""

from __future__ import annotations

import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from docpact.checker.metrics_store import (
    _connect,
    get_top_violators,
    get_trends,
    get_violation_history,
    record_run,
)
from docpact.checker.models import (
    Hallazgo,
    ResultadoArchivo,
    ResultadoFuncion,
    ResultadoProyecto,
)


def _make_result(*hallazgos: Hallazgo) -> ResultadoProyecto:
    """Build a ResultadoProyecto from raw hallazgos, grouping by file."""
    by_file: dict[str, list[Hallazgo]] = defaultdict(list)
    for h in hallazgos:
        by_file[h.archivo].append(h)
    archivos = []
    for archivo, hs in by_file.items():
        fns: dict[str, list[Hallazgo]] = defaultdict(list)
        for h in hs:
            fns[h.funcion].append(h)
        funciones = [
            ResultadoFuncion(nombre=name, archivo=archivo, linea=h.linea,
                             tiene_contrato=True, hallazgos=fns[name])
            for name, h in ((n, fns[n][0]) for n in fns)
        ]
        archivos.append(ResultadoArchivo(archivo=archivo, funciones=funciones))
    return ResultadoProyecto(archivos=archivos)


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path


H1 = Hallazgo(tipo="error", campo="side_effects", funcion="process_data",
               archivo="src/main.py", linea=42, mensaje="Missing side_effects")
H2 = Hallazgo(tipo="warning", campo="rn", funcion="process_data",
               archivo="src/main.py", linea=42, mensaje="RN not found")
H3 = Hallazgo(tipo="error", campo="side_effects", funcion="fetch_user",
               archivo="src/api.py", linea=10, mensaje="Undeclared effect")


class TestRecordRun:
    def test_returns_snapshot_id(self, root: Path) -> None:
        result = _make_result(H1, H2)
        sid = record_run(result, root)
        assert isinstance(sid, int)
        assert sid >= 1

    def test_incrementing_ids(self, root: Path) -> None:
        result = _make_result(H1)
        sid1 = record_run(result, root)
        sid2 = record_run(result, root)
        assert sid2 == sid1 + 1

    def test_empty_result(self, root: Path) -> None:
        result = ResultadoProyecto()
        sid = record_run(result, root)
        assert sid >= 1

    def test_stores_violations(self, root: Path) -> None:
        record_run(_make_result(H1, H2, H3), root)
        conn = _connect(root)
        try:
            rows = conn.execute("SELECT * FROM violations").fetchall()
            assert len(rows) == 3
        finally:
            conn.close()

    def test_daily_metrics_accumulates(self, root: Path) -> None:
        result = _make_result(H1, H3)
        record_run(result, root)
        record_run(result, root)
        history = get_violation_history("side_effects", days=1, project_root=root)
        assert len(history) == 1
        assert history[0]["count"] == 4  # 2 per run * 2 runs


class TestGetTrends:
    def test_no_data(self, root: Path) -> None:
        trends = get_trends("side_effects", days=30, project_root=root)
        assert trends["direction"] == "stable"
        assert trends["data_points"] == 0

    def test_with_data(self, root: Path) -> None:
        record_run(_make_result(H1, H3), root)
        trends = get_trends("side_effects", days=30, project_root=root)
        assert trends["rule_id"] == "side_effects"
        assert trends["direction"] in ("increasing", "decreasing", "stable")
        assert trends["data_points"] >= 1

    def test_unknown_rule(self, root: Path) -> None:
        record_run(_make_result(H1), root)
        trends = get_trends("nonexistent", days=30, project_root=root)
        assert trends["direction"] == "stable"
        assert trends["data_points"] == 0


class TestGetTopViolators:
    def test_no_data(self, root: Path) -> None:
        assert get_top_violators(days=30, project_root=root) == []

    def test_ranking(self, root: Path) -> None:
        record_run(_make_result(H1, H2, H3), root)
        top = get_top_violators(top_n=5, days=30, project_root=root)
        assert len(top) == 2
        # process_data has 2 violations (H1 + H2), fetch_user has 1 (H3)
        assert top[0]["function"] == "process_data"
        assert top[0]["violations"] == 2
        assert top[0]["errors"] == 1
        assert top[0]["warnings"] == 1
        assert top[1]["function"] == "fetch_user"
        assert top[1]["violations"] == 1

    def test_top_n_limit(self, root: Path) -> None:
        record_run(_make_result(H1, H2, H3), root)
        top = get_top_violators(top_n=1, days=30, project_root=root)
        assert len(top) == 1


class TestGetViolationHistory:
    def test_no_data(self, root: Path) -> None:
        assert get_violation_history("side_effects", days=30, project_root=root) == []

    def test_returns_counts(self, root: Path) -> None:
        record_run(_make_result(H1, H3), root)
        history = get_violation_history("side_effects", days=1, project_root=root)
        assert len(history) == 1
        assert history[0]["count"] == 2
        assert history[0]["day"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def test_accumulation_across_runs(self, root: Path) -> None:
        for _ in range(3):
            record_run(_make_result(H1), root)
        history = get_violation_history("side_effects", days=1, project_root=root)
        assert history[0]["count"] == 3

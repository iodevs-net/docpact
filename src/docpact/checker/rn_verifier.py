"""Verificador de patrones RN — valida que el código implemente las reglas.

Escanea el proyecto buscando CONTRATOs con rn: [RN-XXX], luego verifica
que cada RN tenga su patrón de implementación en el fuente.
Cuando un patrón define check_before/blocks, también verifica que la
verificación (blocks) aparezca ANTES de la operación (check_before).

Resultado por RN:
  PASS      — keyword(s) encontrado(s) en el archivo indicado
  FAIL      — keyword(s) ausente(s)
  NO_PATTERN— no hay patrón definido para esta RN

Resultado de orden (order):
  PASS       — check aparece antes de operation (correcto)
  ORDER_FAIL — check aparece después de operation (incorrecto)
  NO_CHECK   — keyword(s) no encontrados o sin check_before definido

Los patrones se cargan desde:
  1. docpact.toml [docpact.rn_patterns_file] (JSON)
  2. .docpact/rn_patterns.json (proyecto)
  3. Patrones embebidos (fallback)

Solo depende de stdlib (pathlib, json).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("docpact.verifier")

# ── Patrones RN embebidos (fallback para proyectos sin configuración) ────────
# Para proyectos nuevos, definir patrones en .docpact/rn_patterns.json
# o en docpact.toml [docpact.rn_patterns_file]

RN_PATTERNS: dict[str, dict] = {
    # Fallback patterns (ioDesk-3) - projects define their own in .docpact/rn_patterns.json
    "RN-008": {
        "description": "RESTRINGIDO no crea tickets",
        "file": "soporte/services/tickets.py",
        "must_contain": ["RESTRINGIDO", "PermissionError"],
        "check_before": ".create(",
        "blocks": "RESTRINGIDO",
    },
    "RN-006": {
        "description": "resuelto es terminal",
        "file": "soporte/constants.py",
        "must_contain": ["resuelto", "ESTADOS_TERMINALES"],
    },
    "RN-TNT-001": {
        "description": "TenantManager fail-closed",
        "file": "nucleo/managers.py",
        "must_contain": [".none()"],
    },
    "RN-SEC-002": {
        "description": "Lockout tras 5 intentos",
        "file": "nucleo/middleware/ip_block.py",
        "must_contain": ["blocked_ip", "is_ip_blocked"],
        "check_before": "cache.set",
        "blocks": "blocked_ip",
    },
}


def _load_patterns(project_root: Path | None = None) -> dict[str, dict]:
    """Carga patrones RN desde JSON.

    Prioridad:
    1. project_root/.docpact/rn_patterns.json
    2. Patrones embebidos (fallback)
    """
    patterns: dict[str, dict] = {}

    # Intentar cargar desde proyecto
    if project_root is not None:
        patterns_file = project_root / ".docpact" / "rn_patterns.json"
        if patterns_file.exists():
            try:
                data = json.loads(patterns_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "patterns" in data:
                    patterns = data["patterns"]
                elif isinstance(data, dict):
                    patterns = data
                logger.debug("Loaded %d RN patterns from %s", len(patterns), patterns_file)
                return patterns
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load RN patterns from %s: %s", patterns_file, e)

    # Fallback: patrones embebidos (vacío por defecto)
    return patterns


def _get_patterns(project_root: Path | None = None) -> dict[str, dict]:
    """Obtiene patrones RN, cacheando el resultado."""
    global RN_PATTERNS
    if not RN_PATTERNS:
        RN_PATTERNS = _load_patterns(project_root)
    return RN_PATTERNS


def _read_file(path: Path) -> str | None:
    """Lee archivo; retorna None si no existe."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _check_order(source: str, check_keyword: str, operation_keyword: str) -> str:
    """Verifica que check_keyword aparezca ANTES de operation_keyword en source.

    Returns:
        'PASS'       — check aparece antes de operation (orden correcto)
        'ORDER_FAIL' — check aparece después de operation (orden incorrecto)
        'NO_CHECK'   — alguno de los keywords no se encontró en source
    """
    check_pos: tuple[int, int] | None = None  # (line, col)
    operation_pos: tuple[int, int] | None = None

    for i, line in enumerate(source.splitlines(), start=1):
        if check_keyword in line and check_pos is None:
            check_pos = (i, line.index(check_keyword))
        if operation_keyword in line and operation_pos is None:
            operation_pos = (i, line.index(operation_keyword))
        if check_pos and operation_pos:
            break

    if check_pos is None or operation_pos is None:
        return "NO_CHECK"

    if check_pos < operation_pos:
        return "PASS"
    return "ORDER_FAIL"


def verify_rn(rn_id: str, project_root: Path) -> dict:
    """Verifica un solo patrón RN en el código fuente.

    Returns dict con keys: rn_id, description, file, status, found, missing, order.
    status es 'PASS', 'FAIL', o 'NO_PATTERN'.
    order es 'PASS', 'ORDER_FAIL', 'NO_CHECK', o '' (sin check definido).
    """
    patterns = _get_patterns(project_root)
    pattern = patterns.get(rn_id)
    if pattern is None:
        return {
            "rn_id": rn_id,
            "description": "",
            "file": "",
            "status": "NO_PATTERN",
            "found": [],
            "missing": [],
            "order": "",
        }

    file_path = project_root / pattern["file"]
    source = _read_file(file_path)
    if source is None:
        return {
            "rn_id": rn_id,
            "description": pattern["description"],
            "file": pattern["file"],
            "status": "FAIL",
            "found": [],
            "missing": list(pattern["must_contain"]),
            "order": "NO_CHECK",
        }

    found: list[str] = []
    missing: list[str] = []
    for keyword in pattern["must_contain"]:
        if keyword in source:
            found.append(keyword)
        else:
            missing.append(keyword)

    status = "PASS" if not missing else "FAIL"

    # Order verification: check comes before operation
    check_before = pattern.get("check_before")
    blocks = pattern.get("blocks")
    if check_before and blocks:
        order = _check_order(source, blocks, check_before)
    else:
        order = ""

    return {
        "rn_id": rn_id,
        "description": pattern["description"],
        "file": pattern["file"],
        "status": status,
        "found": found,
        "missing": missing,
        "order": order,
    }


def verify_all_rns(project_root: Path) -> list[dict]:
    """Verifica todos los patrones RN definidos."""
    patterns = _get_patterns(project_root)
    return [verify_rn(rn_id, project_root) for rn_id in patterns]


def print_results(results: list[dict]) -> None:
    """Imprime resultados formateados a stdout."""
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    no_pattern = sum(1 for r in results if r["status"] == "NO_PATTERN")

    print(f"\n{'=' * 72}")
    print(f"  RN Pattern Verifier — {len(results)} RNs checked")
    print(f"{'=' * 72}\n")

    icons = {"PASS": "✅", "FAIL": "❌", "NO_PATTERN": "⚠️"}
    order_icons = {"PASS": "✅", "ORDER_FAIL": "❌", "NO_CHECK": "—"}
    for r in results:
        icon = icons[r["status"]]
        order = r.get("order", "")
        order_str = order_icons.get(order, "—") if order else ""
        line = f"  {icon} {r['rn_id']:<16} {r['status']:<12} ORDER: {order_str:<4}"
        if r["description"]:
            line += f" {r['description']}"
        print(line)
        if r["status"] == "FAIL" and r["missing"]:
            print(f"     Missing: {', '.join(r['missing'])}")
            print(f"     File: {r['file']}")

    print(f"\n{'─' * 72}")
    print(f"  PASS: {passed}  FAIL: {failed}  NO_PATTERN: {no_pattern}")
    print(f"{'─' * 72}\n")

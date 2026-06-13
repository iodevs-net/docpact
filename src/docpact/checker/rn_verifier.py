"""Verificador de patrones RN hardcoded — valida que el código implemente las reglas.

Escanea el proyecto buscando CONTRATOs con rn: [RN-XXX], luego verifica
que cada RN tenga su patrón de implementación en el fuente.

Resultado por RN:
  PASS      — keyword(s) encontrado(s) en el archivo indicado
  FAIL      — keyword(s) ausente(s)
  NO_PATTERN— no hay patrón definido para esta RN

Solo depende de stdlib (pathlib).
"""

from __future__ import annotations

from pathlib import Path
# ── Patrones RN — cada entrada mapea un ID a su verificación ──────────────

RN_PATTERNS: dict[str, dict] = {
    "RN-008": {
        "description": "RESTRINGIDO no puede crear tickets",
        "file": "soporte/services/tickets.py",
        "must_contain": ["RESTRINGIDO", "PermissionError"],
    },
    "RN-006": {
        "description": "resuelto es el unico estado terminal",
        "file": "soporte/constants.py",
        "must_contain": ["resuelto", "ESTADOS_TERMINALES"],
    },
    "RN-004": {
        "description": "no saltos entre estados",
        "file": "soporte/state_machine/builder.py",
        "must_contain": ["TRANSICIONES_PERMITIDAS"],
    },
    "RN-TNT-001": {
        "description": "TenantManager fail-closed",
        "file": "nucleo/managers.py",
        "must_contain": [".none()"],
    },
    "RN-SEG-002": {
        "description": "solo supervision asigna tareas",
        "file": "soporte/views/ticket_gestion.py",
        "must_contain": ["puede_asignar_tareas"],
    },
    "RN-SEC-001": {
        "description": "sesion expira 1 hora",
        "file": "nucleo/middleware/session_inactivity.py",
        "must_contain": ["3600"],
    },
    "RN-SEC-002": {
        "description": "lockout tras 5 intentos",
        "file": "nucleo/middleware/ip_block.py",
        "must_contain": ["blocked_ip", "is_ip_blocked"],
    },
    "RN-C-016": {
        "description": "credenciales fuera de logs",
        "file": "config/settings/logging.py",
        "must_contain": ["FILTERED_PASSWORD", "sanitize"],
    },
    "RN-CL-002": {
        "description": "clientes solo ven su info",
        "file": "nucleo/selectors/media.py",
        "must_contain": ["find_media_owner"],
    },
    "RN-010": {
        "description": "consumo al 100% bloquea",
        "file": "soporte/services/sesiones.py",
        "must_contain": ["disponibles", "horas_extra_aprobadas"],
    },
}


def _read_file(path: Path) -> str | None:
    """Lee archivo; retorna None si no existe."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return None


def verify_rn(rn_id: str, project_root: Path) -> dict:
    """Verifica un solo patrón RN en el código fuente.

    Returns dict con keys: rn_id, description, file, status, found, missing.
    status es 'PASS', 'FAIL', o 'NO_PATTERN'.
    """
    pattern = RN_PATTERNS.get(rn_id)
    if pattern is None:
        return {
            "rn_id": rn_id,
            "description": "",
            "file": "",
            "status": "NO_PATTERN",
            "found": [],
            "missing": [],
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
        }

    found: list[str] = []
    missing: list[str] = []
    for keyword in pattern["must_contain"]:
        if keyword in source:
            found.append(keyword)
        else:
            missing.append(keyword)

    status = "PASS" if not missing else "FAIL"
    return {
        "rn_id": rn_id,
        "description": pattern["description"],
        "file": pattern["file"],
        "status": status,
        "found": found,
        "missing": missing,
    }


def verify_all_rns(project_root: Path) -> list[dict]:
    """Verifica todos los patrones RN definidos."""
    return [verify_rn(rn_id, project_root) for rn_id in RN_PATTERNS]


def print_results(results: list[dict]) -> None:
    """Imprime resultados formateados a stdout."""
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    no_pattern = sum(1 for r in results if r["status"] == "NO_PATTERN")

    print(f"\n{'=' * 60}")
    print(f"  RN Pattern Verifier — {len(results)} RNs checked")
    print(f"{'=' * 60}\n")

    icons = {"PASS": "✅", "FAIL": "❌", "NO_PATTERN": "⚠️"}
    for r in results:
        icon = icons[r["status"]]
        line = f"  {icon} {r['rn_id']:<16} {r['status']:<12}"
        if r["description"]:
            line += f" {r['description']}"
        print(line)
        if r["status"] == "FAIL" and r["missing"]:
            print(f"     Missing: {', '.join(r['missing'])}")
            print(f"     File: {r['file']}")

    print(f"\n{'─' * 60}")
    print(f"  PASS: {passed}  FAIL: {failed}  NO_PATTERN: {no_pattern}")
    print(f"{'─' * 60}\n")

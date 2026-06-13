"""Tests del verificador de patrones RN (rn_verifier)."""

from __future__ import annotations

from pathlib import Path
from io import StringIO
import sys

from docpact.checker.rn_verifier import (
    RN_PATTERNS,
    _check_order,
    verify_rn,
    verify_all_rns,
    print_results,
)


# ── Helpers ───────────────────────────────────────────────────────


def _write_source(root: Path, rel_path: str, content: str) -> Path:
    """Crea un archivo fuente dentro de root con el contenido dado."""
    file_path = root / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path


# ── verify_rn ─────────────────────────────────────────────────────


def test_verify_rn_pass(tmp_path: Path) -> None:
    """Patron encontrado en fuente -> status PASS."""
    _write_source(
        tmp_path,
        "soporte/services/tickets.py",
        "class Tickets:\n    def crear(self, user):\n"
        "        if user.rol == 'RESTRINGIDO':\n"
        "            raise PermissionError('No puede crear tickets')\n",
    )
    result = verify_rn("RN-008", tmp_path)

    assert result["rn_id"] == "RN-008"
    assert result["status"] == "PASS"
    assert result["found"] == ["RESTRINGIDO", "PermissionError"]
    assert result["missing"] == []


def test_verify_rn_fail(tmp_path: Path) -> None:
    """Keyword faltante -> status FAIL con la lista de missing."""
    _write_source(
        tmp_path,
        "soporte/services/tickets.py",
        "class Tickets:\n    def crear(self, user):\n"
        "        if user.rol == 'RESTRINGIDO':\n"
        "            pass\n",
    )
    result = verify_rn("RN-008", tmp_path)

    assert result["rn_id"] == "RN-008"
    assert result["status"] == "FAIL"
    assert "PermissionError" in result["missing"]
    assert "RESTRINGIDO" in result["found"]


def test_verify_rn_fail_file_missing(tmp_path: Path) -> None:
    """Archivo fuente no existe -> FAIL con todos los keywords en missing."""
    result = verify_rn("RN-008", tmp_path)

    assert result["status"] == "FAIL"
    assert result["found"] == []
    assert result["missing"] == ["RESTRINGIDO", "PermissionError"]
    assert result["file"] == "soporte/services/tickets.py"


def test_verify_rn_no_pattern(tmp_path: Path) -> None:
    """RN no definida en RN_PATTERNS -> NO_PATTERN."""
    result = verify_rn("RN-99999", tmp_path)

    assert result["rn_id"] == "RN-99999"
    assert result["status"] == "NO_PATTERN"
    assert result["found"] == []
    assert result["missing"] == []
    assert result["file"] == ""


# ── verify_all_rns ────────────────────────────────────────────────


def test_verify_all_rns(tmp_path: Path) -> None:
    """verify_all_rns retorna una lista con un resultado por cada patron."""
    results = verify_all_rns(tmp_path)

    assert isinstance(results, list)
    assert len(results) == len(RN_PATTERNS)

    checked_ids = {r["rn_id"] for r in results}
    assert checked_ids == set(RN_PATTERNS.keys())

    # Sin archivos creados, todos deben ser FAIL
    for r in results:
        assert r["status"] in ("FAIL", "NO_PATTERN")


def test_verify_all_rns_mixed(tmp_path: Path) -> None:
    """Algunos archivos existen con keywords, otros no -> mix de PASS/FAIL."""
    # Crear fuente para RN-006 con todos los keywords
    _write_source(
        tmp_path,
        "soporte/constants.py",
        "ESTADOS_TERMINALES = ['resuelto']\n",
    )
    # Crear fuente para RN-TNT-001 con keyword
    _write_source(
        tmp_path,
        "nucleo/managers.py",
        "class TenantManager:\n    def get(self):\n        return self.none()\n",
    )

    results = verify_all_rns(tmp_path)

    r006 = next(r for r in results if r["rn_id"] == "RN-006")
    assert r006["status"] == "PASS"

    rtnt = next(r for r in results if r["rn_id"] == "RN-TNT-001")
    assert rtnt["status"] == "PASS"


# ── print_results ─────────────────────────────────────────────────


def test_print_results(tmp_path: Path) -> None:
    """print_results emite output que contiene los IDs de las RNs."""
    _write_source(
        tmp_path,
        "soporte/services/tickets.py",
        "RESTRINGIDO and PermissionError",
    )
    results = verify_all_rns(tmp_path)

    captured = StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        print_results(results)
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()

    # Debe contener todos los IDs verificados
    for r in results:
        assert r["rn_id"] in output

    # Debe contener contadores de resultado
    assert "PASS:" in output
    assert "FAIL:" in output


def test_print_results_shows_missing(tmp_path: Path) -> None:
    """print_results muestra keywords faltantes para FAIL."""
    _write_source(
        tmp_path,
        "soporte/services/tickets.py",
        "if user.rol == 'RESTRINGIDO':\n    pass  # allowed",
    )
    result = verify_rn("RN-008", tmp_path)
    assert result["status"] == "FAIL"

    captured = StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        print_results([result])
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    assert "PermissionError" in output


# ── _check_order ──────────────────────────────────────────────────


def test_check_order_pass() -> None:
    """check keyword appears BEFORE operation keyword -> PASS."""
    source = (
        "if user.rol == 'RESTRINGIDO':\n"
        "    raise PermissionError('No puede')\n"
        "ticket.create(data)\n"
    )
    assert _check_order(source, "RESTRINGIDO", ".create(") == "PASS"


def test_check_order_fail() -> None:
    """check keyword appears AFTER operation keyword -> ORDER_FAIL."""
    source = (
        "ticket.create(data)\n"
        "if user.rol == 'RESTRINGIDO':\n"
        "    raise PermissionError('No puede')\n"
    )
    assert _check_order(source, "RESTRINGIDO", ".create(") == "ORDER_FAIL"


def test_check_order_no_check() -> None:
    """check keyword not found in source -> NO_CHECK."""
    source = "ticket.create(data)\n"
    assert _check_order(source, "RESTRINGIDO", ".create(") == "NO_CHECK"


def test_check_order_no_operation() -> None:
    """operation keyword not found in source -> NO_CHECK."""
    source = "if user.rol == 'RESTRINGIDO':\n    raise PermissionError\n"
    assert _check_order(source, "RESTRINGIDO", ".create(") == "NO_CHECK"


def test_check_order_same_line() -> None:
    """check and operation on same line -> check comes first (PASS)."""
    source = "if RESTRINGIDO: raise Error before .create(\n"
    assert _check_order(source, "RESTRINGIDO", ".create(") == "PASS"


def test_check_order_same_line_reversed() -> None:
    """operation before check on same line -> ORDER_FAIL."""
    source = ".create(data) if RESTRINGIDO\n"
    assert _check_order(source, "RESTRINGIDO", ".create(") == "ORDER_FAIL"


# ── verify_rn order integration ──────────────────────────────────


def test_verify_rn_order_pass(tmp_path: Path) -> None:
    """RN with check_before: check before operation -> order PASS."""
    _write_source(
        tmp_path,
        "soporte/services/tickets.py",
        "class Tickets:\n"
        "    def crear(self, user):\n"
        "        if user.rol == 'RESTRINGIDO':\n"
        "            raise PermissionError('No puede crear tickets')\n"
        "        ticket = Ticket.objects.create(data)\n",
    )
    result = verify_rn("RN-008", tmp_path)

    assert result["status"] == "PASS"
    assert result["order"] == "PASS"


def test_verify_rn_order_fail(tmp_path: Path) -> None:
    """RN with check_before: check after operation -> order ORDER_FAIL."""
    _write_source(
        tmp_path,
        "soporte/services/tickets.py",
        "class Tickets:\n"
        "    def crear(self, user):\n"
        "        ticket = Ticket.objects.create(data)\n"
        "        if user.rol == 'RESTRINGIDO':\n"
        "            raise PermissionError('No puede crear tickets')\n",
    )
    result = verify_rn("RN-008", tmp_path)

    assert result["status"] == "PASS"
    assert result["order"] == "ORDER_FAIL"


def test_verify_rn_order_no_check(tmp_path: Path) -> None:
    """RN with check_before: check keyword missing -> order NO_CHECK."""
    _write_source(
        tmp_path,
        "soporte/services/tickets.py",
        "class Tickets:\n"
        "    def crear(self, user):\n"
        "        ticket = Ticket.objects.create(data)\n",
    )
    result = verify_rn("RN-008", tmp_path)

    assert result["status"] == "FAIL"
    assert result["order"] == "NO_CHECK"


def test_verify_rn_order_empty_string_when_no_check_before(tmp_path: Path) -> None:
    """RN without check_before/blocks -> order is empty string."""
    _write_source(
        tmp_path,
        "soporte/constants.py",
        "ESTADOS_TERMINALES = ['resuelto']\n",
    )
    result = verify_rn("RN-006", tmp_path)

    assert result["status"] == "PASS"
    assert result["order"] == ""


def test_verify_rn_order_no_pattern() -> None:
    """RN not in patterns -> order is empty string."""
    result = verify_rn("RN-99999", Path("/nonexistent"))

    assert result["status"] == "NO_PATTERN"
    assert result["order"] == ""


def test_verify_rn_order_file_missing() -> None:
    """RN with check_before but file missing -> order NO_CHECK."""
    result = verify_rn("RN-008", Path("/nonexistent"))

    assert result["status"] == "FAIL"
    assert result["order"] == "NO_CHECK"


def test_verify_rn_all_have_order_key(tmp_path: Path) -> None:
    """All RN results must include the 'order' key."""
    results = verify_all_rns(tmp_path)
    for r in results:
        assert "order" in r, f"{r['rn_id']} missing 'order' key"
        assert r["order"] in ("", "PASS", "ORDER_FAIL", "NO_CHECK")


def test_print_results_shows_order_column(tmp_path: Path) -> None:
    """print_results includes ORDER column in output."""
    _write_source(
        tmp_path,
        "soporte/services/tickets.py",
        "if user.rol == 'RESTRINGIDO':\n"
        "    raise PermissionError('No puede')\n"
        "ticket.create(data)\n",
    )
    result = verify_rn("RN-008", tmp_path)
    assert result["order"] == "PASS"

    captured = StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        print_results([result])
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    assert "ORDER:" in output

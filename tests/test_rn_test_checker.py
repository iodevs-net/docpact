"""Tests del verificador de tests de RN (rn_test_checker)."""

from pathlib import Path

from docpact.checker.rn_test_checker import check_rn_tests


def test_sin_rn_ids_retorna_vacio():
    """Lista vacía de RNs debe retornar lista vacía."""
    errores = check_rn_tests([], Path("/tmp"))
    assert errores == []


def test_sin_proyecto_root_retorna_vacio():
    """proyecto_root=None debe retornar lista vacía."""
    errores = check_rn_tests(["RN-010"], None)
    assert errores == []


def test_rn_sin_test_reporta_error(tmp_path: Path):
    """RN-010 sin test debe retornar error."""
    (tmp_path / "tests" / "rn").mkdir(parents=True, exist_ok=True)
    errores = check_rn_tests(["RN-010"], tmp_path, "mi_funcion")
    assert len(errores) == 1
    assert "mi_funcion" in errores[0].mensaje
    assert "RN-010" in errores[0].mensaje
    assert "test_rn_010.py" in errores[0].mensaje


def test_rn_con_test_no_reporta_error(tmp_path: Path):
    """RN-010 con test existente no debe reportar error."""
    rn_dir = tmp_path / "tests" / "rn"
    rn_dir.mkdir(parents=True, exist_ok=True)
    (rn_dir / "test_rn_010.py").write_text("# Test RN-010")
    errores = check_rn_tests(["RN-010"], tmp_path)
    assert errores == []


def test_multiples_rns_con_test(tmp_path: Path):
    """Múltiples RNs con tests existentes no deben reportar error."""
    rn_dir = tmp_path / "tests" / "rn"
    rn_dir.mkdir(parents=True, exist_ok=True)
    (rn_dir / "test_rn_010.py").write_text("")
    (rn_dir / "test_rn_005.py").write_text("")
    errores = check_rn_tests(["RN-010", "RN-005"], tmp_path)
    assert errores == []


def test_multiples_rns_sin_test(tmp_path: Path):
    """Múltiples RNs sin tests deben reportar todos los errores."""
    (tmp_path / "tests" / "rn").mkdir(parents=True, exist_ok=True)
    errores = check_rn_tests(["RN-010", "RN-005", "RN-020"], tmp_path)
    assert len(errores) == 3


def test_directorio_rn_sin_errores(tmp_path: Path):
    """Si tests/rn/ no existe, no es error (el checker omite)."""
    errores = check_rn_tests(["RN-010"], tmp_path)
    assert len(errores) == 0


def test_rn_con_id_sin_prefijo_omitido(tmp_path: Path):
    """IDs sin prefijo RN- se omiten sin error."""
    (tmp_path / "tests" / "rn").mkdir(parents=True, exist_ok=True)
    errores = check_rn_tests(["REGLAC-001"], tmp_path)
    assert errores == []


def test_rn_con_prefijo_largo_requiere_test(tmp_path: Path):
    """RN-SEG-005 requiere test_rn_SEG-005.py."""
    rn_dir = tmp_path / "tests" / "rn"
    rn_dir.mkdir(parents=True, exist_ok=True)
    (rn_dir / "test_rn_SEG-005.py").write_text("")
    errores = check_rn_tests(["RN-SEG-005"], tmp_path)
    assert errores == []

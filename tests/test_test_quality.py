"""Tests para check_rn_test_quality.

Cubre deteccion de tests placeholder: cuerpo vacio, sin asserts, asserts triviales.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from docpact.checker.rn_test_checker import check_rn_test_quality, _es_assert_trivial


# ── Tests de la funcion pura _es_assert_trivial ─────────────────────────


def test_es_assert_trivial_detecta_true():
    """assert True es trivial."""
    import ast
    node = ast.parse("assert True").body[0]
    assert _es_assert_trivial(node) is True


def test_es_assert_trivial_detecta_constante_numerica():
    """assert 1 es trivial."""
    import ast
    node = ast.parse("assert 1").body[0]
    assert _es_assert_trivial(node) is True


def test_es_assert_trivial_detecta_string():
    """assert 'x' es trivial."""
    import ast
    node = ast.parse("assert 'x'").body[0]
    assert _es_assert_trivial(node) is True


def test_es_assert_trivial_detecta_none():
    """assert None NO es trivial — siempre falla (None es falsy)."""
    import ast
    node = ast.parse("assert None").body[0]
    assert _es_assert_trivial(node) is False


def test_es_assert_trivial_no_detecta_comparacion():
    """assert x == y NO es trivial."""
    import ast
    node = ast.parse("assert x == y").body[0]
    assert _es_assert_trivial(node) is False


def test_es_assert_trivial_no_detecta_llamada():
    """assert fn(x) NO es trivial."""
    import ast
    node = ast.parse("assert validar(x)").body[0]
    assert _es_assert_trivial(node) is False


# ── Tests de check_rn_test_quality ──────────────────────────────────────


def _crear_test_file(tmp_path: Path, name: str, content: str) -> Path:
    test_dir = tmp_path / "tests" / "rn"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / name
    test_file.write_text(content)
    return test_file


def test_quality_detecta_cuerpo_vacio(tmp_path):
    """Test con cuerpo vacio (solo pass) es detectado como placebo."""
    _crear_test_file(tmp_path, "test_rn_X.py", '''
def test_algo():
    pass
''')
    errores = check_rn_test_quality(tmp_path)
    assert any("placeholder" in e.mensaje.lower() for e in errores)


def test_quality_detecta_sin_asserts(tmp_path):
    """Test sin asserts (solo setup) es detectado como placebo."""
    _crear_test_file(tmp_path, "test_rn_Y.py", '''
def test_algo():
    x = 1
    y = 2
''')
    errores = check_rn_test_quality(tmp_path)
    assert any("sin asserts" in e.mensaje.lower() for e in errores)


def test_quality_detecta_assert_trivial(tmp_path):
    """Test con solo assert True es detectado como placebo."""
    _crear_test_file(tmp_path, "test_rn_Z.py", '''
def test_algo():
    assert True
''')
    errores = check_rn_test_quality(tmp_path)
    assert any("triviales" in e.mensaje.lower() for e in errores)


def test_quality_pasa_test_real(tmp_path):
    """Test con assert significativo NO es flaggeado como placebo."""
    _crear_test_file(tmp_path, "test_rn_W.py", '''
def test_algo():
    x = calcular()
    assert x == 42
''')
    errores = check_rn_test_quality(tmp_path)
    assert errores == []


def test_quality_no_detecta_ignora_funciones_no_test(tmp_path):
    """Funciones que no empiezan con test_ son ignoradas."""
    _crear_test_file(tmp_path, "test_rn_V.py", '''
def helper():
    pass

def test_algo():
    assert True
''')
    errores = check_rn_test_quality(tmp_path)
    # El helper no cuenta, pero el test_algo con assert True si
    assert any("triviales" in e.mensaje.lower() for e in errores)


def test_quality_sin_tests_dir(tmp_path):
    """Si tests/rn/ no existe, retorna lista vacia (no falla)."""
    errores = check_rn_test_quality(tmp_path)
    assert errores == []

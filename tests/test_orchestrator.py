"""Tests del orquestador — flujo completo de verificación."""

from pathlib import Path

from docpact.api import check_file, check_proyecto
from docpact.config import DocpactConfig

FIXTURES = Path(__file__).parent / "fixtures"


def test_check_file_encuentra_contratos():
    """check_file debe encontrar contratos en archivos con CONTRATO."""
    path = FIXTURES / "contrato_completo.py"
    resultado = check_file(path)
    assert resultado.total_funciones > 0
    assert resultado.funciones_con_contrato > 0


def test_check_file_sin_contrato():
    """check_file sobre archivo sin CONTRATO → 0 contratos."""
    path = FIXTURES / "sin_contrato.py"
    resultado = check_file(path)
    # La función existe pero no tiene CONTRATO
    assert resultado.funciones_con_contrato == 0


def test_check_file_strict():
    """strict=True debe reportar funciones sin CONTRATO como errores."""
    path = FIXTURES / "sin_contrato.py"
    resultado = check_file(path, strict=True)
    assert resultado.total_errores > 0
    assert any("sin CONTRATO" in h.mensaje for f in resultado.funciones for h in f.hallazgos)


def test_check_file_ninguno_ok():
    """CONTRATO con side_effects: ninguno y sin llamadas → sin errores."""
    path = FIXTURES / "contrato_minimo.py"
    resultado = check_file(path)
    for func in resultado.funciones:
        assert func.valido, f"{func.nombre} tiene errores: {func.hallazgos}"


def test_check_proyecto_directorio():
    """check_proyecto sobre directorio de fixtures debe procesar todos los archivos."""
    resultado = check_proyecto(FIXTURES)
    assert resultado.total_funciones > 0
    assert resultado.total_archivos >= 4  # 4 fixtures


def test_check_proyecto_score_sensible():
    """check_proyecto debe retornar score entre 0 y 100."""
    resultado = check_proyecto(FIXTURES)
    score = resultado.calcular_score()
    assert 0 <= score <= 100


def test_check_proyecto_con_strict():
    """check_proyecto con strict detecta funciones sin CONTRATO."""
    resultado = check_proyecto(FIXTURES, strict=True)
    # sin_contrato.py y contrato_invalido.py tienen funciones sin CONTRATO
    assert resultado.total_errores > 0


def test_hallazgo_tipos_correctos():
    """Hallazgos deben tener tipo 'error' o 'warning'."""
    path = FIXTURES / "sin_contrato.py"
    resultado = check_file(path, strict=True)
    for func in resultado.funciones:
        for h in func.hallazgos:
            assert h.tipo in ("error", "warning")


def test_resultado_proyecto_propiedades():
    """Propiedades de ResultadoProyecto deben ser consistentes."""
    resultado = check_proyecto(FIXTURES)
    # Total de funciones debe ser >= suma de funciones_con_contrato
    assert resultado.total_funciones >= resultado.funciones_con_contrato
    # Errores y warnings deben ser enteros no negativos
    assert resultado.total_errores >= 0
    assert resultado.total_warnings >= 0


def test_nivel_es_string_valido():
    """nivel debe ser un string L0-L4."""
    resultado = check_proyecto(FIXTURES)
    nivel = resultado.nivel
    assert nivel.startswith("L")
    assert any(l in nivel for l in ["L0", "L1", "L2", "L3", "L4"])

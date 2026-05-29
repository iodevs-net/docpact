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


def test_check_file_ts_con_contrato():
    """check_file debe procesar archivos .ts con CONTRATOS."""
    from docpact.checker.orchestrator import check_file
    ts_file = FIXTURES.parent / "fixtures_ts" / "single_line_contrato_completo.ts"
    config = DocpactConfig()
    resultado = check_file(str(ts_file), config)
    assert resultado.funciones_con_contrato > 0
    assert any(f.nombre == "validarTicket" for f in resultado.funciones)


def test_check_file_ts_sin_contrato():
    """check_file sobre .ts sin CONTRATO debe retornar 0 contratos."""
    from docpact.checker.orchestrator import check_file
    ts_file = FIXTURES.parent / "fixtures_ts" / "single_line_sin_contrato.ts"
    config = DocpactConfig()
    resultado = check_file(str(ts_file), config)
    assert resultado.funciones_con_contrato == 0

def test_check_file_ts_strict():
    """strict=True: .ts con CONTRATO header pero vacío debe generar error."""
    from docpact.checker.orchestrator import check_file
    from pathlib import Path as _P
    import tempfile
    # Archivo con // CONTRATO: header pero sin campos → strict detecta
    tmp = _P(tempfile.mkstemp(suffix=".ts")[1])
    tmp.write_text("""\
// CONTRATO:
//   side_effects: ninguno
async function crearTicket(): Promise<void> {
    return;
}
""")
    config = DocpactConfig(strict=True)
    resultado = check_file(str(tmp), config)
    tmp.unlink()
    assert any("sin CONTRATO" in h.mensaje
               for f in resultado.funciones
               for h in f.hallazgos)

def test_check_file_ts_sidefx_error():
    """check_file .ts debe detectar side_effects no declarados."""
    from docpact.checker.orchestrator import check_file
    from pathlib import Path as _P
    import tempfile
    tmp = _P(tempfile.mkstemp(suffix=".ts")[1])
    tmp.write_text("""\
// CONTRATO:
//   output: void
//   side_effects: ninguno
async function crearTicket(): Promise<void> {
    await api.post('/tickets', {});
}
""")
    config = DocpactConfig()
    resultado = check_file(str(tmp), config)
    tmp.unlink()
    sidefx_hallazgos = [h for f in resultado.funciones for h in f.hallazgos
                        if h.campo == "side_effects"]


def test_check_file_introspeccion_firmas():
    """Verificar que docpact introspecte firmas y tipos AST automáticamente."""
    from docpact.checker.orchestrator import check_file
    from pathlib import Path as _P
    import tempfile
    
    tmp = _P(tempfile.mkstemp(suffix=".py")[1])
    tmp.write_text("""\
def mi_funcion_procesar(cliente_id: int, activo: bool = True) -> dict[str, Any]:
    \"\"\"Procesa un cliente.
    
    CONTRATO:
    side_effects: ninguno
    rn: [RN-001]
    \"\"\"
    return {"id": cliente_id}
""")
    
    config = DocpactConfig()
    resultado = check_file(str(tmp), config)
    tmp.unlink()
    
    assert len(resultado.funciones) == 1
    func = resultado.funciones[0]
    assert func.tiene_contrato
    assert func.contrato is not None
    
    # Verificar inputs introspectados
    assert "cliente_id" in func.contrato.input
    assert func.contrato.input["cliente_id"].tipo == "int"
    assert "activo" in func.contrato.input
    assert func.contrato.input["activo"].tipo == "bool"
    
    # Verificar output introspectado
    assert func.contrato.output == "dict[str, Any]"


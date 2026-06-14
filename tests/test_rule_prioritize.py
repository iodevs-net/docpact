"""Tests para docpact.checker.rule_prioritize — scoring ponderado."""

from pathlib import Path

from docpact.checker.rule_prioritize import (
    priorizar_reglas,
    _contar_funciones,
    _tiene_tests,
    _score_recencia,
)


def _proyecto(tmp_path: Path) -> Path:
    """Crea estructura mínima de proyecto para tests."""
    src = tmp_path / "app"
    src.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    (src / "orders.py").write_text(
        "def create(): pass\ndef update(): pass\ndef delete(): pass\n"
        "def validate(): pass\ndef notify(): pass\n"
    )
    (src / "auth.py").write_text("def login(): pass\ndef logout(): pass\n")
    (tests / "test_auth.py").write_text("# test")
    (src / "audit.py").write_text("def log(): pass\n")
    return tmp_path


class TestContarFunciones:
    def test_cuenta_def_y_async(self, tmp_path):
        f = tmp_path / "m.py"
        f.write_text("def a(): pass\nasync def b(): pass\ndef c(): pass\n")
        assert _contar_funciones(f) == 3

    def test_sin_funciones(self, tmp_path):
        f = tmp_path / "m.py"
        f.write_text("x = 1\n")
        assert _contar_funciones(f) == 0

    def test_archivo_inexistente(self, tmp_path):
        assert _contar_funciones(tmp_path / "nope.py") == 1


class TestTieneTests:
    def test_con_test(self, tmp_path):
        root = _proyecto(tmp_path)
        assert _tiene_tests("app/auth.py", root) is True

    def test_sin_test(self, tmp_path):
        root = _proyecto(tmp_path)
        assert _tiene_tests("app/orders.py", root) is False


class TestScoreRecencia:
    def test_archivo_reciente(self, tmp_path):
        f = tmp_path / "nuevo.py"
        f.write_text("x = 1")
        assert _score_recencia(f) > 0.9

    def test_archivo_inexistente(self, tmp_path):
        assert _score_recencia(tmp_path / "no.py") == 0.5


class TestPriorizarReglas:
    def test_vacio(self):
        assert priorizar_reglas([]) == []

    def test_ordena_descendente(self, tmp_path):
        root = _proyecto(tmp_path)
        reglas = [
            {"tipo": "validacion", "titulo": "A", "archivo": "app/audit.py", "linea": 1},
            {"tipo": "security", "titulo": "B", "archivo": "app/orders.py", "linea": 1},
            {"tipo": "negocio", "titulo": "C", "archivo": "app/auth.py", "linea": 1},
        ]
        resultado = priorizar_reglas(reglas, raiz=root)
        prios = [r["prioridad"] for r in resultado]
        assert prios == sorted(prios, reverse=True)

    def test_campos_scores_presentes(self, tmp_path):
        root = _proyecto(tmp_path)
        reglas = [{"tipo": "negocio", "titulo": "X", "archivo": "app/orders.py", "linea": 1}]
        r = priorizar_reglas(reglas, raiz=root)[0]
        for k in ("prioridad", "score_riesgo", "score_cobertura", "score_criticidad", "score_recencia"):
            assert k in r, f"Falta {k}"

    def test_security_mayor_riesgo_que_validacion(self, tmp_path):
        root = _proyecto(tmp_path)
        reglas = [
            {"tipo": "security", "titulo": "S", "archivo": "app/audit.py", "linea": 1},
            {"tipo": "validacion", "titulo": "V", "archivo": "app/audit.py", "linea": 1},
        ]
        resultado = priorizar_reglas(reglas, raiz=root)
        assert resultado[0]["tipo"] == "security"

    def test_no_test_alta_criticidad(self, tmp_path):
        root = _proyecto(tmp_path)
        reglas = [
            {"tipo": "negocio", "titulo": "T", "archivo": "app/auth.py", "linea": 1},   # has test
            {"tipo": "negocio", "titulo": "U", "archivo": "app/orders.py", "linea": 1},  # no test
        ]
        resultado = priorizar_reglas(reglas, raiz=root)
        # orders has more funcs so higher coverage, auth has test so lower criticality
        # The combined effect should place orders first or equal
        assert resultado[0]["score_criticidad"] >= resultado[1]["score_criticidad"]

    def test_mas_funciones_mayor_cobertura(self, tmp_path):
        root = _proyecto(tmp_path)
        reglas = [
            {"tipo": "negocio", "titulo": "A", "archivo": "app/orders.py", "linea": 1},  # 5 funcs
            {"tipo": "negocio", "titulo": "B", "archivo": "app/audit.py", "linea": 1},   # 1 func
        ]
        resultado = priorizar_reglas(reglas, raiz=root)
        assert resultado[0]["score_cobertura"] > resultado[1]["score_cobertura"]

    def test_tipo_desconocido_score_bajo(self, tmp_path):
        root = _proyecto(tmp_path)
        reglas = [{"tipo": "desconocido", "titulo": "X", "archivo": "app/audit.py", "linea": 1}]
        r = priorizar_reglas(reglas, raiz=root)[0]
        assert r["score_riesgo"] == 0.3

    def test_preserva_campos_originales(self, tmp_path):
        root = _proyecto(tmp_path)
        reglas = [{"tipo": "negocio", "titulo": "T", "archivo": "app/audit.py", "linea": 1, "evidencia": "x"}]
        r = priorizar_reglas(reglas, raiz=root)[0]
        assert r["titulo"] == "T"
        assert r["evidencia"] == "x"

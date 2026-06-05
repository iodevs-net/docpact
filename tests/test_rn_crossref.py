"""Tests del verificador de cross-reference RN (F4).

Verifica que si A declara RN-XXX y llama a B, B tambien tenga RN-XXX.
Testea _extraer_llamadas, _tiene_rn_en_codigo, verificar_cross_reference.

Nota: _extraer_llamadas usa regex que solo captura funciones con nombre
>= 2 chars, empezando con minuscula, que NO sean metodos (sin .previo)
NI definiciones (sin def previo), NI builtins/keywords de Python.
"""
from docpact.checker.rn_crossref import (
    _extraer_llamadas,
    _tiene_rn_en_codigo,
    verificar_cross_reference,
    build_funcion_map,
)


class TestExtraerLlamadas:
    """_extraer_llamadas — extrae llamadas a funciones via regex."""

    def test_llamada_simple(self):
        """foo() → detecta foo."""
        assert "foo" in _extraer_llamadas("foo()\n")

    def test_llamada_con_args(self):
        """procesar(ticket, usuario) → detecta procesar."""
        assert "procesar" in _extraer_llamadas("procesar(ticket, usuario)")

    def test_minimo_dos_caracteres(self):
        """Funciones de 1 char (a(), b()) NO se detectan."""
        assert _extraer_llamadas("a()\nb()\nc()") == set()

    def test_no_captura_def(self):
        """'def foo():' no se detecta como llamada a foo."""
        assert "foo" not in _extraer_llamadas("def foo():\n    pass")

    def test_no_captura_metodos(self):
        """split no se detecta (tiene .previo). Edge case: regex captura substring 'plit'."""
        llamadas = _extraer_llamadas("x.split(',')")
        assert "split" not in llamadas  # no detecta split completo

    def test_no_captura_uppercase(self):
        """Ticket empieza mayuscula, no se detecta."""
        llamadas = _extraer_llamadas("Ticket.objects.create(titulo='test')")
        assert "Ticket" not in llamadas
        assert "create" not in llamadas  # tiene .previo

    def test_filtra_builtins(self):
        """len, range, print son builtins."""
        llamadas = _extraer_llamadas("len(x)\nrange(10)")
        assert "len" not in llamadas
        assert "range" not in llamadas

    def test_filtra_keywords(self):
        """if, for, while son keywords."""
        llamadas = _extraer_llamadas("if x > 0:\n    for y in range(10):")
        assert "if" not in llamadas
        assert "for" not in llamadas

    def test_varias_llamadas_validas(self):
        """Multiples llamadas validas."""
        llamadas = _extraer_llamadas("validar()\nprocesar()\nenviar()")
        assert "validar" in llamadas
        assert "procesar" in llamadas
        assert "enviar" in llamadas

    def test_sin_llamadas_retorna_vacio(self):
        """sin llamadas."""
        assert _extraer_llamadas("x = 1\ny = x + 2") == set()

    def test_string_contiene_llamada(self):
        """'foo()' en string se detecta (regex no distingue strings)."""
        assert "foo" in _extraer_llamadas("msg = 'foo()'")


class TestTieneRNEnCodigo:
    """_tiene_rn_en_codigo — verifica # RN-XXX en codigo."""

    def test_simple(self):
        assert _tiene_rn_en_codigo("# RN-010: regla", "RN-010")

    def test_multiple(self):
        codigo = "# RN-001 # RN-002"
        assert _tiene_rn_en_codigo(codigo, "RN-001")
        assert _tiene_rn_en_codigo(codigo, "RN-002")

    def test_sin_match(self):
        assert not _tiene_rn_en_codigo("x = 1", "RN-010")

    def test_parcial_no_falsa(self):
        """RN-010 no coincide con RN-0100 (busca '# RN-010' exacto)."""
        assert not _tiene_rn_en_codigo("# RN-0100", "RN-010")

    def test_en_medio_de_codigo(self):
        assert _tiene_rn_en_codigo("    # RN-005: validar", "RN-005")

    def test_sin_hash_no_detecta(self):
        """RN-010 sin # no se considera marcado."""
        assert not _tiene_rn_en_codigo("x = RN-010", "RN-010")


class TestVerificarCrossReference:
    """verificar_cross_reference — logica central F4."""

    def test_sin_error_si_destino_tiene_rn(self):
        """Destino declara RN-001 en CONTRATO y tiene marker → OK."""
        errores = verificar_cross_reference(
            archivo="test.py",
            codigo_funcion="destino()",
            rn_ids=["RN-001"],
            todas_las_funciones={
                "destino": [{"codigo": "def destino():\n    '''CONTRATO:\n    rn: [RN-001]\n    '''\n    # RN-001", "archivo": "test.py"}],
            },
        )
        assert errores == []

    def test_error_si_destino_declara_rn_pero_sin_marker(self):
        """Destino declara RN-001 en CONTRATO pero no tiene marker en body → error."""
        errores = verificar_cross_reference(
            archivo="test.py",
            codigo_funcion="destino()",
            rn_ids=["RN-001"],
            todas_las_funciones={
                "destino": [{"codigo": "def destino():\n    '''CONTRATO:\n    rn: [RN-001]\n    '''\n    x = 1", "archivo": "test.py"}],
            },
        )
        assert len(errores) == 1
        assert "RN-001" in errores[0].mensaje
        assert "destino" in errores[0].mensaje

    def test_sin_error_si_destino_NO_declara_rn(self):
        """FIX: si destino NO declara la RN, no es cross-reference problem.
        La llamante es responsable unica de la regla."""
        errores = verificar_cross_reference(
            archivo="test.py",
            codigo_funcion="destino()",
            rn_ids=["RN-001"],
            todas_las_funciones={
                "destino": [{"codigo": "def destino():\n    '''CONTRATO:\n    rn: []\n    '''\n    x = 1", "archivo": "test.py"}],
            },
        )
        assert errores == [], (
            f"No deberia haber error si destino no declara la RN. Got: {errores}"
        )

    def test_error_con_varias_rns(self):
        """Destino declara ambas RNs en CONTRATO pero solo tiene marker para una."""
        errores = verificar_cross_reference(
            archivo="test.py",
            codigo_funcion="destino()",
            rn_ids=["RN-001", "RN-002"],
            todas_las_funciones={
                "destino": [{"codigo": "def destino():\n    '''CONTRATO:\n    rn: [RN-001, RN-002]\n    '''\n    # RN-001", "archivo": "test.py"}],
            },
        )
        assert len(errores) == 1
        assert "RN-002" in errores[0].mensaje

    def test_sin_error_si_funcion_externa(self):
        """Funcion no encontrada en mapa se ignora."""
        errores = verificar_cross_reference(
            archivo="test.py",
            codigo_funcion="externa()",
            rn_ids=["RN-001"],
            todas_las_funciones={},
        )
        assert errores == []

    def test_sin_error_si_no_hay_llamadas(self):
        """Funcion sin llamadas → 0 errores."""
        errores = verificar_cross_reference(
            archivo="test.py",
            codigo_funcion="x = 1",
            rn_ids=["RN-001"],
            todas_las_funciones={},
        )
        assert errores == []


class TestBuildFuncionMap:
    """build_funcion_map — construye mapa nombre → codigo."""

    def test_construye_mapa(self):
        from collections import namedtuple

        RF = namedtuple("ResultadoFuncion", ["nombre", "archivo"])
        resultados = [RF("foo", "a.py"), RF("bar", "b.py")]
        fuentes = {"a.py": "# RN-001", "b.py": "x = 1"}
        mapa = build_funcion_map(resultados, fuentes)
        assert "foo" in mapa
        assert "bar" in mapa
        assert mapa["foo"][0]["codigo"] == "# RN-001"

    def test_ignora_sin_nombre(self):
        from collections import namedtuple

        RF = namedtuple("ResultadoFuncion", ["nombre", "archivo"])
        mapa = build_funcion_map([RF("", "a.py")], {"a.py": "codigo"})
        assert mapa == {}

    def test_ignora_sin_archivo(self):
        from collections import namedtuple

        RF = namedtuple("ResultadoFuncion", ["nombre", "archivo"])
        mapa = build_funcion_map([RF("foo", "")], {})
        assert mapa == {}

    def test_ignora_si_fuente_no_existe(self):
        from collections import namedtuple

        RF = namedtuple("ResultadoFuncion", ["nombre", "archivo"])
        mapa = build_funcion_map([RF("foo", "a.py")], {})
        assert mapa == {}

    def test_extrae_cuerpo_funcion_via_ast(self):
        """build_funcion_map extrae solo el cuerpo de la función, no el archivo."""
        from collections import namedtuple

        RF = namedtuple("ResultadoFuncion", ["nombre", "archivo"])
        fuente = (
            'def foo():\n'
            '    """Docstring."""\n'
            '    return 1\n'
            '\n'
            'def bar():\n'
            '    """Docstring."""\n'
            '    return 2\n'
        )
        resultados = [RF("foo", "a.py"), RF("bar", "a.py")]
        mapa = build_funcion_map(resultados, {"a.py": fuente})
        assert "foo" in mapa
        assert "bar" in mapa
        # foo NO debe contener el código de bar
        assert "return 2" not in mapa["foo"][0]["codigo"]
        assert "return 1" in mapa["foo"][0]["codigo"]

    def test_fallback_a_archivo_completo_si_no_es_python_valido(self):
        """Si el fuente no es Python válido, usa archivo completo como fallback."""
        from collections import namedtuple

        RF = namedtuple("ResultadoFuncion", ["nombre", "archivo"])
        resultados = [RF("foo", "a.py")]
        fuentes = {"a.py": "# just a comment, not valid python def"}
        mapa = build_funcion_map(resultados, fuentes)
        assert "foo" in mapa
        assert mapa["foo"][0]["codigo"] == "# just a comment, not valid python def"

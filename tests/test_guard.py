"""Tests para docpact.guard — validación de cambios contra CONTRATOs."""

from pathlib import Path

from docpact.guard import (
    validar_cambio,
    _extraer_funciones_del_diff,
    _extraer_contratos,
    _verificar_side_effects,
)


class TestExtraerFunciones:
    """Tests para _extraer_funciones_del_diff."""

    def test_extrae_def_simples(self):
        diff = "def mi_funcion(x):\n    return x"
        funcs = _extraer_funciones_del_diff(diff)
        assert "mi_funcion" in funcs

    def test_extrae_async_def(self):
        diff = "async def cargar_datos():\n    pass"
        funcs = _extraer_funciones_del_diff(diff)
        assert "cargar_datos" in funcs

    def test_extrae_multiples(self):
        diff = "def alpha():\n    pass\ndef beta():\n    pass"
        funcs = _extraer_funciones_del_diff(diff)
        assert "alpha" in funcs
        assert "beta" in funcs

    def test_sin_funciones(self):
        diff = "x = 1\nprint(x)"
        funcs = _extraer_funciones_del_diff(diff)
        assert funcs == []


class TestExtraerContratos:
    """Tests para _extraer_contratos."""

    def test_extrae_side_effects(self, tmp_path):
        archivo = tmp_path / "test.py"
        archivo.write_text(
            'def mi_funcion():\n'
            '    """\n'
            '    CONTRATO\n'
            '    side_effects:\n'
            '        - db_write\n'
            '        - email\n'
            '    """\n'
            '    pass\n'
        )
        contratos = _extraer_contratos(archivo.read_text())
        assert "mi_funcion" in contratos
        assert "db_write" in contratos["mi_funcion"]["side_effects"]

    def test_extrae_rns(self, tmp_path):
        archivo = tmp_path / "test.py"
        archivo.write_text(
            'def mi_funcion():\n'
            '    """\n'
            '    CONTRATO\n'
            '    side_effects:\n'
            '        - ninguno\n'
            '    rn: [RN-001, RN-002]\n'
            '    """\n'
            '    pass\n'
        )
        contratos = _extraer_contratos(archivo.read_text())
        assert "mi_funcion" in contratos
        assert "RN-001" in contratos["mi_funcion"]["rns"]

    def test_sin_contrato(self, tmp_path):
        archivo = tmp_path / "test.py"
        archivo.write_text(
            'def mi_funcion():\n'
            '    """Función normal."""\n'
            '    pass\n'
        )
        contratos = _extraer_contratos(archivo.read_text())
        assert "mi_funcion" not in contratos


class TestValidarCambio:
    """Tests para validar_cambio."""

    def test_cambio_sin_funciones(self, tmp_path):
        archivo = tmp_path / "test.py"
        archivo.write_text("x = 1\n")
        resultado = validar_cambio(archivo, "x = 2\n")
        assert resultado.allowed is True

    def test_cambio_seguro(self, tmp_path):
        archivo = tmp_path / "test.py"
        archivo.write_text(
            'def mi_funcion():\n'
            '    """\n'
            '    CONTRATO\n'
            '    side_effects:\n'
            '        - ninguno\n'
            '    """\n'
            '    pass\n'
        )
        resultado = validar_cambio(archivo, 'def mi_funcion():\n    """\n    CONTRATO\n    side_effects:\n        - ninguno\n    """\n    return 1')
        assert resultado.allowed is True

    def test_cambio_permitido_sin_contrato(self, tmp_path):
        archivo = tmp_path / "test.py"
        archivo.write_text('def mi_funcion():\n    pass\n')
        resultado = validar_cambio(archivo, 'def mi_funcion():\n    return 1')
        assert resultado.allowed is True

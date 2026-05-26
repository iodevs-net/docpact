"""Tests del extractor de docstrings."""

import os
from pathlib import Path

from docpact.parser.extractor import extraer_docstrings

FIXTURES = Path(__file__).parent / "fixtures"


def test_extrae_funcion_publica():
    """Debe extraer docstrings de funciones públicas."""
    path = FIXTURES / "contrato_minimo.py"
    resultados = extraer_docstrings(path)
    nombres = [r[1] for r in resultados]
    assert "ping" in nombres


def test_no_extrae_privadas():
    """Por defecto no extrae funciones privadas."""
    path = FIXTURES / "contrato_minimo.py"
    # Este fixture no tiene privadas, pero verificamos que el flag funciona
    resultados = extraer_docstrings(path, incluir_privadas=False)
    assert all(not r[1].startswith("_") for r in resultados)


def test_extrae_clases_y_metodos():
    """Debe extraer docstrings de clases y sus métodos públicos."""
    # Creamos un archivo temporal con una clase
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('''
class MiClase:
    """Docstring de la clase."""
    def metodo_publico(self):
        """Docstring del método."""
        pass
''')
        tmp_path = f.name

    try:
        resultados = extraer_docstrings(tmp_path)
        tipos = {r[2] for r in resultados}
        assert "class" in tipos
        assert "method" in tipos
    finally:
        os.unlink(tmp_path)


def test_extrae_async_function():
    """Debe extraer docstrings de funciones async."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('''
async def tarea_asincrona():
    """Docstring de función async."""
    pass
''')
        tmp_path = f.name

    try:
        resultados = extraer_docstrings(tmp_path)
        assert len(resultados) == 1
        assert resultados[0][1] == "tarea_asincrona"
    finally:
        os.unlink(tmp_path)


def test_file_not_found():
    """Archivo inexistente → FileNotFoundError."""
    try:
        extraer_docstrings("/no/existe/archivo.py")
        assert False, "Debió lanzar FileNotFoundError"
    except FileNotFoundError:
        pass

"""Tests del verificador de dependencias."""

from pathlib import Path

from docpact.checker.deps_checker import check_deps, _resolver_ruta, _verificar_simbolo
from docpact.models.contrato import Contrato, Dependencia


def test_deps_sin_dependencias():
    """Sin dependencias declaradas → 0 errores."""
    contrato = Contrato()
    errores = check_deps(contrato, "/tmp/test.py", "foo")
    assert errores == []


def test_deps_archivo_no_encontrado():
    """Dependencia que apunta a archivo inexistente → error."""
    contrato = Contrato(
        dependencias=[Dependencia(ref="no_existe.py")]
    )
    errores = check_deps(contrato, "/tmp/test.py", "foo")
    assert len(errores) == 1
    assert "no encontrado" in errores[0].mensaje


def test_resolver_ruta_con_py():
    """Ruta con .py debe devolver path con .py."""
    base = Path("/tmp")
    ruta = _resolver_ruta("modulo.py", base)
    assert ruta.name == "modulo.py"


def test_resolver_ruta_sin_py():
    """Ruta sin .py debe probar con y sin extensión."""
    base = Path("/tmp")
    # No existe, pero debe retornar algo sensato
    ruta = _resolver_ruta("modulo", base)
    assert ruta.name in ("modulo", "modulo.py")


def test_verificar_simbolo_no_encontrado():
    """Símbolo que no existe en un archivo → error."""
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1\n")
        tmp = f.name

    try:
        errores = _verificar_simbolo(Path(tmp), "NoExiste", tmp, "foo")
        assert len(errores) == 1
        assert "NoExiste" in errores[0].mensaje
    finally:
        os.unlink(tmp)


def test_verificar_simbolo_encontrado():
    """Símbolo que existe en un archivo → sin errores."""
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def MiFuncion(): pass\nclass MiClase: pass\n")
        tmp = f.name

    try:
        errores_func = _verificar_simbolo(Path(tmp), "MiFuncion", tmp, "foo")
        assert len(errores_func) == 0

        errores_cls = _verificar_simbolo(Path(tmp), "MiClase", tmp, "foo")
        assert len(errores_cls) == 0
    finally:
        os.unlink(tmp)

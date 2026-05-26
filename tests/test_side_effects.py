"""Tests del verificador de side effects (AST walker)."""

import ast

from docpact.checker.side_effects import check_side_effects, _extraer_llamadas, _clasificar_llamadas
from docpact.config import DocpactConfig
from docpact.models.contrato import Contrato, SideEffect


def _parse_funcion(codigo: str):
    """Helper: parsea código Python y retorna el nodo de la primera función."""
    tree = ast.parse(codigo)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    return None


def test_extraer_llamadas_simples():
    """Debe extraer llamadas directas."""
    codigo = """
def foo():
    registrar_evento_bitacora(ticket, editor, "texto")
    """
    node = _parse_funcion(codigo)
    llamadas = _extraer_llamadas(node)
    assert "registrar_evento_bitacora" in llamadas


def test_extraer_llamadas_encadenadas():
    """Debe extraer llamadas encadenadas (obj.method())."""
    codigo = """
def foo():
    Ticket.objects.create(titulo="test")
    """
    node = _parse_funcion(codigo)
    llamadas = _extraer_llamadas(node)
    assert "Ticket.objects.create" in llamadas


def test_extraer_llamadas_anidadas():
    """Debe extraer llamadas dentro de if/for/with."""
    codigo = """
def foo(ticket):
    if ticket.estado == "activo":
        NotificacionService.notificar(ticket)
    for x in range(10):
        BitacoraEntry.objects.create(ticket=ticket)
    """
    node = _parse_funcion(codigo)
    llamadas = _extraer_llamadas(node)
    assert "NotificacionService.notificar" in llamadas
    assert "BitacoraEntry.objects.create" in llamadas


def test_check_side_effects_ninguno_ok():
    """side_effects: ninguno + sin llamadas → sin errores."""
    codigo = """
def foo():
    pass
    """
    node = _parse_funcion(codigo)
    contrato = Contrato()
    config = DocpactConfig()
    errores = check_side_effects(node, contrato, config, "foo", "test.py")
    assert len(errores) == 0


def test_check_side_effects_declarados_pero_ausentes():
    """Side effects declarados pero no encontrados → warning."""
    codigo = """
def foo():
    resultado = 1 + 1
    """
    node = _parse_funcion(codigo)
    contrato = Contrato(side_effects=[SideEffect("envía notificaciones")])
    config = DocpactConfig()
    errores = check_side_effects(node, contrato, config, "foo", "test.py")
    # Debe advertir que el side effect declarado no se encontró
    assert any("envía notificaciones" in e.mensaje for e in errores)
    assert all(e.campo == "side_effects" for e in errores)


def test_check_side_effects_no_declarados():
    """side_effects: ninguno pero hay llamadas reales → error."""
    codigo = """
def foo():
    Ticket.objects.create(titulo="test")
    """
    node = _parse_funcion(codigo)
    contrato = Contrato()  # side_effects vacío = ninguno
    config = DocpactConfig()
    errores = check_side_effects(node, contrato, config, "foo", "test.py")
    assert len(errores) == 1
    assert "ninguno" in errores[0].mensaje
    assert "db_write" in errores[0].mensaje


def test_check_side_effects_multiples_categorias():
    """Debe detectar múltiples categorías de side effects."""
    codigo = """
def foo():
    Ticket.objects.create(titulo="test")
    send_mail("asunto", "cuerpo", ["a@b.com"])
    """
    node = _parse_funcion(codigo)
    contrato = Contrato()
    config = DocpactConfig()
    errores = check_side_effects(node, contrato, config, "foo", "test.py")
    assert len(errores) >= 1
    # Debe mencionar db_write y email en el error
    assert any("db_write" in e.mensaje for e in errores)

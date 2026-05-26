"""Tests del lexer de CONTRATO."""

from docpact.parser.lexer import tokenizar, TipoToken, Token


def test_lexer_detecta_marca_contrato():
    """Debe detectar la línea CONTRATO:."""
    doc = """
    CONTRATO:
      side_effects: ninguno
    """
    tokens = tokenizar(doc)
    assert len(tokens) >= 1
    assert tokens[0].tipo == TipoToken.MARCA_CONTRATO


def test_lexer_campo_simple():
    """Debe tokenizar un campo simple (side_effects: ninguno)."""
    doc = """
    CONTRATO:
      side_effects: ninguno
    """
    tokens = tokenizar(doc)
    campos = [t for t in tokens if t.tipo == TipoToken.CAMPO_SIMPLE]
    assert len(campos) == 1
    assert "side_effects" in campos[0].valor


def test_lexer_campo_compuesto():
    """Debe tokenizar campos compuestos (input:, rn:)."""
    doc = """
    CONTRATO:
      rn:
        - RN-002: regla de prueba
    """
    tokens = tokenizar(doc)
    compuestos = [t for t in tokens if t.tipo == TipoToken.CAMPO_COMPUESTO]
    items = [t for t in tokens if t.tipo == TipoToken.ITEM_LISTA]
    assert len(compuestos) == 1
    assert compuestos[0].valor == "rn"
    assert len(items) == 1
    assert "RN-002" in items[0].valor


def test_lexer_sin_contrato():
    """Docstring sin CONTRATO debe retornar lista vacía."""
    doc = """Solo una descripción narrativa."""
    tokens = tokenizar(doc)
    assert tokens == []


def test_lexer_descripcion_antes_del_contrato():
    """Descripción narrativa antes de CONTRATO: debe ignorarse."""
    doc = """Esta es la descripción.
    CONTRATO:
      side_effects: ninguno
    """
    tokens = tokenizar(doc)
    assert len(tokens) >= 2
    assert tokens[0].tipo == TipoToken.MARCA_CONTRATO


def test_lexer_item_lista_con_indentacion():
    """Items de lista con indentación correcta."""
    doc = """
    CONTRATO:
      borde:
        - tickets vacío: retorna 0
        - sesión sin fin: se ignora
    """
    tokens = tokenizar(doc)
    items = [t for t in tokens if t.tipo == TipoToken.ITEM_LISTA]
    assert len(items) == 2


def test_lexer_detecta_indentacion():
    """La indentación relativa debe calcularse correctamente."""
    doc = """
    CONTRATO:
      input:
        tickets: list — desc
      output: dict
    """
    tokens = tokenizar(doc)
    # base_indent = 4 (espacios antes de "CONTRATO:")
    # NIVEL1 = 6  (espacios antes de "  input:" y "  output:")
    for t in tokens:
        if t.tipo == TipoToken.MARCA_CONTRATO:
            assert t.indentacion == 0
        elif t.tipo in (TipoToken.CAMPO_SIMPLE, TipoToken.CAMPO_COMPUESTO):
            assert t.indentacion == 6  # base_indent + 2

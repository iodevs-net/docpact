"""Tests del parser de CONTRATO."""

from docpact.parser.lexer import tokenizar
from docpact.parser.parser import parsear


def test_parse_contrato_completo():
    """Debe parsear un CONTRATO con todos los campos."""
    doc = """
    CONTRATO:
      input:
        tickets: list[Ticket] — Lista de tickets
      output: dict — Horas calculadas
      side_effects: Crea registro en BD, Envía email
      rn:
        - RN-002: solo sesiones completadas
      borde:
        - tickets vacío: retorna 0
      dependencias:
        - soporte/models/ticket.py::Ticket
    """
    tokens = tokenizar(doc)
    contrato, errores = parsear(tokens)

    assert len(errores) == 0, f"Errores inesperados: {errores}"
    assert "tickets" in contrato.input
    assert contrato.input["tickets"].tipo == "list[Ticket]"
    assert contrato.output == "dict"
    assert contrato.output_descripcion == "Horas calculadas"
    assert len(contrato.side_effects) == 2
    assert contrato.side_effects[0].descripcion == "Crea registro en BD"
    assert len(contrato.rn) == 1
    assert contrato.rn[0].id == "RN-002"
    assert len(contrato.borde) == 1
    assert contrato.borde[0].condicion == "tickets vacío"
    assert len(contrato.dependencias) == 1
    assert contrato.dependencias[0].ref == "soporte/models/ticket.py::Ticket"


def test_parse_side_effects_ninguno():
    """side_effects: ninguno → lista vacía."""
    doc = """
    CONTRATO:
      side_effects: ninguno
    """
    tokens = tokenizar(doc)
    contrato, errores = parsear(tokens)
    assert len(contrato.side_effects) == 0


def test_parse_campos_opcionales_vacios():
    """Campos no declarados deben ser listas/dicts vacíos."""
    doc = """
    CONTRATO:
      side_effects: ninguno
    """
    tokens = tokenizar(doc)
    contrato, errores = parsear(tokens)
    assert contrato.input == {}
    assert contrato.output is None
    assert contrato.rn == []
    assert contrato.borde == []
    assert contrato.dependencias == []


def test_parse_sin_tokens():
    """Lista vacía de tokens → error y Contrato vacío."""
    contrato, errores = parsear([])
    assert len(errores) == 1
    assert "No se encontró bloque CONTRATO" in errores[0].mensaje
    assert contrato.input == {}


def test_parse_sin_contrato_en_docstring():
    """Docstring sin CONTRATO → parsear retorna error."""
    doc = """Solo descripción."""
    tokens = tokenizar(doc)
    assert tokens == []
    contrato, errores = parsear(tokens)
    assert len(errores) == 1


def test_parse_multiple_input_params():
    """Debe parsear múltiples parámetros de input."""
    doc = """
    CONTRATO:
      input:
        usuario: AbstractUser — Usuario que ejecuta
        ticket_id: int — ID del ticket
        motivo: str — Razón
      side_effects: ninguno
    """
    tokens = tokenizar(doc)
    contrato, errores = parsear(tokens)
    assert len(contrato.input) == 3
    assert contrato.input["ticket_id"].tipo == "int"


def test_parse_sin_descripcion_en_input():
    """Input sin descripción debe parsear igual."""
    doc = """
    CONTRATO:
      input:
        usuario: AbstractUser
      side_effects: ninguno
    """
    tokens = tokenizar(doc)
    contrato, errores = parsear(tokens)
    assert "usuario" in contrato.input
    assert contrato.input["usuario"].tipo == "AbstractUser"
    assert contrato.input["usuario"].descripcion == ""


def test_parse_rn_sin_descripcion():
    """RN sin descripción debe tener id pero descripción vacía."""
    doc = """
    CONTRATO:
      rn:
        - RN-010
      side_effects: ninguno
    """
    tokens = tokenizar(doc)
    contrato, errores = parsear(tokens)
    assert len(contrato.rn) == 1
    assert contrato.rn[0].id == "RN-010"
    assert contrato.rn[0].descripcion == ""

"""Tests para marker_honesty: detección de markers decorativos/de delegación."""
from __future__ import annotations

import ast

from docpact.checker.marker_honesty import (
    check_marker_honesty,
    check_marcador_concentrado,
)


# ---- check_marker_honesty -------------------------------------------------


def test_marker_en_return_con_delegacion_emite_warn():
    """Marker en return que solo delega a otro método → WARN."""
    codigo = '''
def cancelar(ticket, editor, motivo):
    """CONTRATO:
    rn: [RN-TKT-003]
    """
    return TicketService.cancelar(ticket, editor, motivo)  # RN-TKT-003
'''
    node = ast.parse(codigo).body[0]
    errores = check_marker_honesty(node, ["RN-TKT-003"], codigo, "cancelar")
    assert len(errores) == 1
    assert "delegación" in errores[0].mensaje
    assert "RN-TKT-003" in errores[0].mensaje
    assert errores[0].linea > 0


def test_marker_en_logica_real_NO_emite_warn():
    """Marker en línea con lógica de la regla → no warning."""
    codigo = '''
def cancelar(ticket, editor, motivo):
    """CONTRATO:
    rn: [RN-TKT-003]
    """
    if ticket.estado == "resuelto":  # RN-TKT-003
        raise ValidationError("No se puede cancelar")
    ticket.estado = "anulado"
    ticket.save()
'''
    node = ast.parse(codigo).body[0]
    errores = check_marker_honesty(node, ["RN-TKT-003"], codigo, "cancelar")
    assert errores == []


def test_marker_en_asignacion_con_delegacion_emite_warn():
    """Marker en `x = Service.method()` → WARN."""
    codigo = '''
def hacer_algo():
    """CONTRATO:
    rn: [RN-001]
    """
    resultado = Service.process()  # RN-001
    return resultado
'''
    node = ast.parse(codigo).body[0]
    errores = check_marker_honesty(node, ["RN-001"], codigo, "hacer_algo")
    assert len(errores) == 1
    assert "RN-001" in errores[0].mensaje


def test_marker_en_funcion_sin_rn_NO_emite_warn():
    """Si el marker no está en la lista de RNs del CONTRATO, se ignora."""
    codigo = '''
def helper():
    """CONTRATO:
    rn: []
    """
    return Service.process()  # RN-999
'''
    node = ast.parse(codigo).body[0]
    errores = check_marker_honesty(node, [], codigo, "helper")
    assert errores == []


def test_multiples_markers_algunos_delegan():
    """Algunos markers en lógica, otros en delegación."""
    codigo = '''
def mi_funcion():
    """CONTRATO:
    rn: [RN-001, RN-002]
    """
    if True:  # RN-001
        pass
    return Service.process()  # RN-002
'''
    node = ast.parse(codigo).body[0]
    errores = check_marker_honesty(node, ["RN-001", "RN-002"], codigo, "mi_funcion")
    # Solo RN-002 debe generar warning (está en delegación)
    assert len(errores) == 1
    assert "RN-002" in errores[0].mensaje


def test_contrato_vacio_retorna_lista_vacia():
    """Si el CONTRATO no tiene RNs, no hay qué validar."""
    codigo = '''
def helper():
    return Service.process()  # RN-001
'''
    node = ast.parse(codigo).body[0]
    errores = check_marker_honesty(node, [], codigo, "helper")
    assert errores == []


def test_call_a_funcion_local_no_es_delegacion():
    """`x = func()` (sin X.y) NO se considera delegación."""
    codigo = '''
def mi_funcion():
    """CONTRATO:
    rn: [RN-001]
    """
    return validar()  # RN-001
'''
    node = ast.parse(codigo).body[0]
    errores = check_marker_honesty(node, ["RN-001"], codigo, "mi_funcion")
    # validar() es función local (no es X.y), no es delegación
    assert errores == []


def test_docstring_no_se_considera_delegacion():
    """El docstring nunca emite warnings (no es código ejecutable)."""
    codigo = '''def mi_funcion():
    """CONTRATO:
    rn: [RN-001]  # RN-001 en el docstring
    """
    return True
'''
    node = ast.parse(codigo).body[0]
    errores = check_marker_honesty(node, ["RN-001"], codigo, "mi_funcion")
    assert errores == []


# ---- check_marcador_concentrado ------------------------------------------


def test_menos_de_umbral_no_warns():
    """Función con 3 RNs (umbral 5) → no warning."""
    resultado = check_marcador_concentrado(
        ["RN-001", "RN-002", "RN-003"],
        "mi_funcion",
        umbral=5,
    )
    assert resultado is None


def test_mas_de_umbral_emite_warn():
    """Función con 7 RNs (umbral 5) → WARN."""
    resultado = check_marcador_concentrado(
        ["RN-001", "RN-002", "RN-003", "RN-004", "RN-005", "RN-006", "RN-007"],
        "mi_funcion",
        umbral=5,
    )
    assert resultado is not None
    assert "7 RNs" in resultado.mensaje
    assert "mi_funcion" in resultado.mensaje


def test_umbral_configurable():
    """El umbral se puede ajustar."""
    rns = ["RN-001", "RN-002", "RN-003", "RN-004"]
    # Con umbral 3 → warn
    assert check_marcador_concentrado(rns, "f", umbral=3) is not None
    # Con umbral 10 → no warn
    assert check_marcador_concentrado(rns, "f", umbral=10) is None


def test_exacto_en_umbral_no_warns():
    """5 RNs con umbral 5 → no warn (el > es estricto)."""
    rns = ["RN-001", "RN-002", "RN-003", "RN-004", "RN-005"]
    assert check_marcador_concentrado(rns, "f", umbral=5) is None

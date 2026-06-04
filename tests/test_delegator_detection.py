"""Tests para Mejora #4: delegator detection en check_side_effects.

Verifica que cuando una funcion declara side_effects pero delega a un
service (method call), NO se genere el warning de 'no se detectaron
llamadas con patrones conocidos'.
"""
from __future__ import annotations

import ast

import pytest

from docpact.checker.side_effects import check_side_effects
from docpact.config import DocpactConfig
from docpact.models.contrato import Contrato, SideEffect


def _make_contrato(side_effects_descs: list[str]) -> Contrato:
    """Helper: crea un Contrato con los side_effects dados."""
    return Contrato(
        input={},
        output="",
        side_effects=[SideEffect(descripcion=d) for d in side_effects_descs],
        rn=[],
        dependencias=[],
    )


def _make_config() -> DocpactConfig:
    return DocpactConfig()


def test_delegator_con_method_call_no_genera_warning():
    """Funcion que delega a un service (method call) NO genera warning."""
    codigo = '''
def view_que_delega(request, ticket_id):
    ticket = TicketService.suspender(ticket_id=ticket_id, editor=request.user)
    return redirect("ticket_detalle", ticket_id=ticket_id)
'''
    node = ast.parse(codigo).body[0]
    contrato = _make_contrato(["db_write", "email"])
    errores = check_side_effects(node, contrato, _make_config(),
                                 "view_que_delega", "test.py")
    # Como hay method calls (TicketService.suspender), es delegator
    assert errores == [], (
        f"Delegator no deberia generar warning. Got: {[e.mensaje for e in errores]}"
    )


def test_sin_method_calls_sí_genera_warning():
    """Funcion sin method calls (cuerpo vacio) SI genera warning."""
    codigo = '''
def funcion_vacia():
    pass
'''
    node = ast.parse(codigo).body[0]
    contrato = _make_contrato(["db_write"])
    errores = check_side_effects(node, contrato, _make_config(),
                                 "funcion_vacia", "test.py")
    assert len(errores) == 1
    assert "patrones conocidos" in errores[0].mensaje


def test_bare_function_calls_sin_method_calls_sí_genera_warning():
    """Function calls simples (sin .method) NO son delegators."""
    codigo = '''
def fn():
    imprimir("hola")
    loggear("evento")
'''
    node = ast.parse(codigo).body[0]
    contrato = _make_contrato(["db_write"])
    errores = check_side_effects(node, contrato, _make_config(),
                                 "fn", "test.py")
    # No hay method calls, asi que el warning se genera
    assert len(errores) == 1


def test_delegator_con_multiples_method_calls_no_warning():
    """Multiples method calls = delegator complejo, no warning."""
    codigo = '''
def view_compleja(request):
    usuario = UserService.actualizar(user_id=request.user.id, data=request.POST)
    ticket = TicketService.crear(usuario=usuario, data=request.POST)
    return ticket
'''
    node = ast.parse(codigo).body[0]
    contrato = _make_contrato(["db_write", "email", "audit"])
    errores = check_side_effects(node, contrato, _make_config(),
                                 "view_compleja", "test.py")
    assert errores == []


def test_delegator_con_chained_method_calls():
    """Chained method calls (.filter().first()) cuentan como delegator."""
    codigo = '''
def get_ticket(user, ticket_id):
    return Ticket.objects.para_usuario(user).filter(id=ticket_id).first()
'''
    node = ast.parse(codigo).body[0]
    contrato = _make_contrato(["db_read"])
    errores = check_side_effects(node, contrato, _make_config(),
                                 "get_ticket", "test.py")
    assert errores == [], (
        f"Chained method calls deberian contar como delegator. "
        f"Got: {[e.mensaje for e in errores]}"
    )

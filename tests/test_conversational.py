"""Tests para docpact.conversational (Mejora #9).

Cubre:
- preguntas_naturales: queries que un user no-dev puede hacer
- parsear_pregunta: extrae intencion de una pregunta en lenguaje natural
- responder_pregunta: pipeline completo pregunta -> respuesta
"""
from __future__ import annotations

import pytest

from docpact.conversational import (
    parsear_pregunta,
    responder_pregunta,
)


# ──────────────────── parsear_pregunta ────────────────────


def test_parsear_pregunta_tenant_safe():
    """Pregunta sobre si el codigo es seguro multi-tenant."""
    q = "este codigo viola el filtro de tenant?"
    intencion = parsear_pregunta(q)
    assert intencion["tipo"] == "tenant_safe"


def test_parsear_pregunta_state_transition():
    """Pregunta sobre transiciones de estado."""
    q = "puedo cambiar el estado de un ticket directamente?"
    intencion = parsear_pregunta(q)
    assert intencion["tipo"] == "state_transition"


def test_parsear_pregunta_no_import():
    """Pregunta sobre imports prohibidos."""
    q = "el agente importo algo que no debia?"
    intencion = parsear_pregunta(q)
    assert intencion["tipo"] == "no_import"


def test_parsear_pregunta_required_groups():
    """Pregunta sobre permisos o grupos."""
    q = "quien puede acceder a esto? solo admins?"
    intencion = parsear_pregunta(q)
    assert intencion["tipo"] == "required_groups"


def test_parsear_pregunta_general():
    """Pregunta general sin keyword especifica."""
    q = "esto funciona bien?"
    intencion = parsear_pregunta(q)
    assert intencion["tipo"] == "general"


# ──────────────────── responder_pregunta ────────────────────


def test_responder_pregunta_general_retorna_mensaje():
    """Pregunta general retorna una respuesta util."""
    respuesta = responder_pregunta("esto funciona bien?")
    assert isinstance(respuesta, str)
    assert len(respuesta) > 10


def test_responder_pregunta_tenant_safe_con_snippet():
    """Pregunta sobre tenant retorna snippet relevante."""
    respuesta = responder_pregunta("el codigo viola el filtro de tenant?")
    assert "tenant" in respuesta.lower() or "para_usuario" in respuesta.lower()


def test_responder_pregunta_retorna_sugerencia_accion():
    """Toda respuesta debe incluir una sugerencia de accion concreta."""
    respuesta = responder_pregunta("esto funciona bien?")
    # La respuesta debe sugerir un comando o accion
    assert any(word in respuesta.lower() for word in ["check", "mcp", "docpact", "comando", "run", "validar"])

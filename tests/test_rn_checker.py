"""Tests del verificador de RN (reglas de negocio)."""

from docpact.checker.rn_checker import (
    _extraer_ids_rn,
    extraer_comentarios_desde_fuente,
)


def test_extraer_ids_rn_simple():
    """Debe extraer RN-010 de un comentario."""
    comentarios = ["# RN-010: esta regla se implementa aquí"]
    ids = _extraer_ids_rn(comentarios)
    assert "RN-010" in ids


def test_extraer_ids_rn_multiple():
    """Debe extraer múltiples RNs del mismo comentario."""
    comentarios = ["# RN-002 y RN-003 implementadas aquí"]
    ids = _extraer_ids_rn(comentarios)
    assert "RN-002" in ids
    assert "RN-003" in ids


def test_extraer_ids_rn_sin_match():
    """Comentarios sin RN-XXX deben retornar lista vacía."""
    comentarios = ["# Esto es un comentario normal"]
    ids = _extraer_ids_rn(comentarios)
    assert ids == []


def test_extraer_ids_rn_en_codigo():
    """Debe extraer RN aún si está en medio de código."""
    comentarios = ["    # RN-010: verificar permisos"]
    ids = _extraer_ids_rn(comentarios)
    assert "RN-010" in ids


def test_extraer_comentarios_desde_fuente():
    """Debe extraer solo líneas con # de un rango de la fuente."""
    fuente = """
def foo():
    # RN-001: primera regla
    x = 1
    # RN-002: segunda regla
    return x
"""
    comentarios = extraer_comentarios_desde_fuente(fuente, 2, 6)
    assert len(comentarios) == 2
    assert any("RN-001" in c for c in comentarios)
    assert any("RN-002" in c for c in comentarios)


def test_extraer_comentarios_ignora_sin_hash():
    """Líneas sin # no deben aparecer en los comentarios extraídos."""
    fuente = """
def foo():
    x = 1
    return x
"""
    comentarios = extraer_comentarios_desde_fuente(fuente, 2, 4)
    assert comentarios == []


def test_extraer_ids_rn_con_prefijo_personalizado():
    """Debe soportar prefijos personalizados."""
    comentarios = ["# BR-010: business rule"]
    ids = _extraer_ids_rn(comentarios, prefijo="BR-")
    assert "BR-010" in ids

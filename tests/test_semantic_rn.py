"""Tests para el módulo semantic_rn (Fase A del T02).

CONTRATO:
input: ninguno
output: ninguno
side_effects: pytest discovers and runs these tests
rn: []
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from docpact.checker.semantic_rn import (
    validar_rn,
    validadores_disponibles,
)
from docpact.models.contrato import ErrorParser


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def proyecto_tmp(tmp_path: Path) -> Path:
    """Crea un proyecto mínimo con archivos de ejemplo."""
    modulo = tmp_path / "ticket_estados.py"
    modulo.write_text(
        '''"""Máquina de estados de tickets."""

TRANSICIONES_PERMITIDAS = {
    "suspendido": ["asignado", "atender", "remoto", "laboratorio"],
    "atender": ["asignado", "en_traslado", "programado", "remoto"],
    "programado": ["atender", "asignado"],
}
''',
        encoding="utf-8",
    )
    return tmp_path


# ─────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────


def test_validadores_disponibles_lista_los_5():
    nombres = validadores_disponibles()
    assert "state_transition" in nombres
    assert "no_import" in nombres
    assert "required_groups" in nombres
    assert "tenant_safe" in nombres
    assert "has_pattern" in nombres


def test_validar_rn_tipo_desconocido_retorna_error():
    errores = validar_rn("def f(): pass", "RN-X", {"type": "inventado"})
    assert len(errores) == 1
    assert "desconocido" in errores[0].mensaje


def test_validar_rn_sin_type_retorna_error():
    errores = validar_rn("def f(): pass", "RN-X", {})
    assert len(errores) == 1
    assert "'type'" in errores[0].mensaje


# ─────────────────────────────────────────────────────────────────────
# state_transition
# ─────────────────────────────────────────────────────────────────────


def test_state_transition_pasa_si_transicion_existe(proyecto_tmp):
    spec = {
        "type": "state_transition",
        "from_estado": "suspendido",
        "to_estado": "atender",
        "matriz_attr": "TRANSICIONES_PERMITIDAS",
        "modulo": "ticket_estados.py",
    }
    contexto = {"proyecto_root": str(proyecto_tmp)}
    errores = validar_rn("def f(): pass", "RN-005", spec, contexto)
    assert errores == []


def test_state_transition_falla_si_transicion_no_existe(proyecto_tmp):
    spec = {
        "type": "state_transition",
        "from_estado": "suspendido",
        "to_estado": "anulado",  # no está en la matriz
        "matriz_attr": "TRANSICIONES_PERMITIDAS",
        "modulo": "ticket_estados.py",
    }
    contexto = {"proyecto_root": str(proyecto_tmp)}
    errores = validar_rn("def f(): pass", "RN-X", spec, contexto)
    assert len(errores) == 1
    assert "anulado" in errores[0].mensaje


def test_state_transition_to_cualquiera_pasa_con_uno(proyecto_tmp):
    spec = {
        "type": "state_transition",
        "from_estado": "suspendido",
        "to_cualquiera": ["anulado", "atender"],  # atender existe
        "matriz_attr": "TRANSICIONES_PERMITIDAS",
        "modulo": "ticket_estados.py",
    }
    contexto = {"proyecto_root": str(proyecto_tmp)}
    errores = validar_rn("def f(): pass", "RN-005", spec, contexto)
    assert errores == []


def test_state_transition_modulo_inexistente_retorna_error(proyecto_tmp):
    spec = {
        "type": "state_transition",
        "from_estado": "suspendido",
        "to_estado": "atender",
        "modulo": "no_existe.py",
    }
    contexto = {"proyecto_root": str(proyecto_tmp)}
    errores = validar_rn("def f(): pass", "RN-005", spec, contexto)
    assert "no encontrado" in errores[0].mensaje


# ─────────────────────────────────────────────────────────────────────
# no_import
# ─────────────────────────────────────────────────────────────────────


def test_no_import_pasa_sin_imports_prohibidos():
    codigo = "from django.db import models\ndef f(): return models"
    spec = {"type": "no_import", "patterns": ["facturacion_erp"]}
    assert validar_rn(codigo, "RN-FAC-001", spec) == []


def test_no_import_falla_con_import_prohibido():
    codigo = "from facturacion_erp import cliente_sync\ndef f(): pass"
    spec = {"type": "no_import", "patterns": ["facturacion_erp"]}
    errores = validar_rn(codigo, "RN-FAC-001", spec)
    assert len(errores) == 1
    assert "facturacion_erp" in errores[0].mensaje


def test_no_import_con_wildcard():
    codigo = "from sii_chile.sii import validar\ndef f(): pass"
    spec = {"type": "no_import", "patterns": ["*sii*"]}
    errores = validar_rn(codigo, "RN-X", spec)
    assert len(errores) == 1


def test_no_import_en_archivo_no_aplica():
    codigo = "from facturacion_erp import x\ndef f(): pass"
    spec = {
        "type": "no_import",
        "patterns": ["facturacion_erp"],
        "en_archivo": "soporte/services/ticket.py",
    }
    contexto = {"archivo": "clientes/services/facturacion.py"}  # otro archivo
    assert validar_rn(codigo, "RN-X", spec, contexto) == []


# ─────────────────────────────────────────────────────────────────────
# required_groups
# ─────────────────────────────────────────────────────────────────────


def test_required_groups_pasa_si_hay_check_de_grupo():
    codigo = """
def puede_borrar(usuario):
    return usuario.groups.filter(name="administracion").exists()
"""
    spec = {"type": "required_groups", "allowed": ["administracion"]}
    assert validar_rn(codigo, "RN-CL-005", spec) == []


def test_required_groups_falla_sin_check():
    codigo = "def puede_borrar(usuario):\n    return True\n"
    spec = {"type": "required_groups", "allowed": ["administracion"]}
    errores = validar_rn(codigo, "RN-CL-005", spec)
    assert len(errores) == 1
    assert "validación de grupo" in errores[0].mensaje


def test_required_groups_acepta_is_superuser():
    codigo = "def f(u):\n    return getattr(u, 'is_superuser', False)\n"
    spec = {"type": "required_groups", "allowed": ["administracion"]}
    assert validar_rn(codigo, "RN-X", spec) == []


# ─────────────────────────────────────────────────────────────────────
# tenant_safe
# ─────────────────────────────────────────────────────────────────────


def test_tenant_safe_pasa_sin_escape():
    codigo = "qs = Ticket.objects.para_usuario(user)"
    spec = {"type": "tenant_safe"}
    assert validar_rn(codigo, "RN-003", spec) == []


def test_tenant_safe_falla_con_unfiltered_objects():
    codigo = "qs = Ticket.unfiltered_objects.all()"
    spec = {"type": "tenant_safe"}
    errores = validar_rn(codigo, "RN-003", spec)
    assert len(errores) == 1
    assert "unfiltered_objects" in errores[0].mensaje


def test_tenant_safe_forbid_personalizado():
    codigo = "qs = Ticket.objects.raw('SELECT *')"
    spec = {"type": "tenant_safe", "forbid": [".raw("]}
    errores = validar_rn(codigo, "RN-003", spec)
    assert len(errores) == 1


# ─────────────────────────────────────────────────────────────────────
# has_pattern
# ─────────────────────────────────────────────────────────────────────


def test_has_pattern_pasa_si_patron_existe():
    codigo = "INTERVALO_RE_RECORDATORIO = timedelta(minutes=3)\ndef f(): pass"
    spec = {"type": "has_pattern", "patron": "INTERVALO_RE_RECORDATORIO"}
    assert validar_rn(codigo, "RN-NOT-004", spec) == []


def test_has_pattern_falla_si_patron_no_existe():
    codigo = "x = 1\ndef f(): return x"
    spec = {"type": "has_pattern", "patron": "PATRON_INEXISTENTE"}
    errores = validar_rn(codigo, "RN-X", spec)
    assert len(errores) == 1
    assert "PATRON_INEXISTENTE" in errores[0].mensaje


def test_has_pattern_soporta_or():
    codigo = "def f(): return SUSPENDIDO"
    spec = {"type": "has_pattern", "patron": "PROGRAMADO|SUSPENDIDO"}
    assert validar_rn(codigo, "RN-X", spec) == []

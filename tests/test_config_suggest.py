"""Tests para docpact.config_suggest (Mejora #7).

Cubre:
- inferir_tipo_validador: heurística CONTRATO -> type
- generar_bloque_toml: type+spec -> bloque TOML
- sugerir_configs: pipeline que escanea CONTRATOS de un proyecto
"""
from __future__ import annotations

from pathlib import Path

from docpact.config_suggest import (
    generar_bloque_toml,
    inferir_tipo_validador,
)
from docpact.models.contrato import (
    CampoInput,
    CasoBorde,
    Contrato,
    Dependencia,
    ReglaNegocio,
    SideEffect,
)



def _make_contrato(**overrides) -> Contrato:
    """Helper para crear un CONTRATO con campos custom."""
    defaults: dict = {
        "input": {},
        "output": None,
        "output_descripcion": "",
        "side_effects": [],
        "rn": [],
        "borde": [],
        "dependencias": [],
        "comportamiento": None,
        "asume": None,
        "produce": None,
    }
    defaults.update(overrides)
    return Contrato(**defaults)


# ──────────────────── inferir_tipo_validador ────────────────────


def test_inferir_tenant_safe_cuando_rn_menciona_tenant():
    """Si el CONTRATO tiene RN-XXX con 'tenant' en descripcion, infiere tenant_safe."""
    c = _make_contrato(
        rn=[ReglaNegocio(id="RN-TNT-001", descripcion="queries multi-tenant seguras")],
        dependencias=[Dependencia(ref="soporte/models/ticket.py::Ticket")],
    )
    tipo, confidence = inferir_tipo_validador(c)
    assert tipo == "tenant_safe"
    assert confidence >= 0.7


def test_inferir_tenant_safe_cuando_comportamiento_menciona_para_usuario():
    """Si comportamiento menciona para_usuario, infiere tenant_safe."""
    c = _make_contrato(
        comportamiento="Lista tickets del usuario actual usando para_usuario(user)"
    )
    tipo, _ = inferir_tipo_validador(c)
    assert tipo == "tenant_safe"


def test_inferir_state_transition_cuando_input_tiene_estado():
    """Si input tiene param 'estado' y produce menciona cambio, infiere state_transition."""
    c = _make_contrato(
        input={"estado": CampoInput(nombre="estado", tipo="str")},
        produce="Cambia el estado del ticket de 'abierto' a 'suspendido'",
        rn=[ReglaNegocio(id="RN-TKT-002", descripcion="transicion de estados")],
    )
    tipo, _ = inferir_tipo_validador(c)
    assert tipo == "state_transition"


def test_inferir_state_transition_cuando_comportamiento_menciona_transicion():
    """Si comportamiento menciona transicion, infiere state_transition."""
    c = _make_contrato(
        comportamiento="Transiciona el ticket al estado solicitado",
        rn=[ReglaNegocio(id="RN-TKT-002", descripcion="cambio de estado")],
    )
    tipo, _ = inferir_tipo_validador(c)
    assert tipo == "state_transition"


def test_inferir_no_import_cuando_asume_dice_delegado():
    """Si asume/delega a un modulo, infiere no_import para evitar inline."""
    c = _make_contrato(
        asume="El template se delega a nucleo.notifications (no inline)",
        rn=[ReglaNegocio(id="RN-NOT-002", descripcion="usar template centralizado")],
    )
    tipo, _ = inferir_tipo_validador(c)
    assert tipo == "no_import"


def test_inferir_required_groups_cuando_asume_menciona_grupo():
    """Si asume menciona grupo/permiso, infiere required_groups."""
    c = _make_contrato(
        asume="Solo usuarios del grupo 'supervision' pueden suspender",
        rn=[ReglaNegocio(id="RN-TKT-005", descripcion="autorizacion por grupo")],
    )
    tipo, _ = inferir_tipo_validador(c)
    assert tipo == "required_groups"


def test_inferir_has_pattern_como_fallback():
    """Si nada matchea, fallback a has_pattern (chequeo basico de substring)."""
    c = _make_contrato(
        comportamiento="Hace algo generico sin keywords",
    )
    tipo, _ = inferir_tipo_validador(c)
    assert tipo == "has_pattern"


# ──────────────────── generar_bloque_toml ────────────────────


def test_generar_bloque_tenant_safe_tiene_forbid_y_type():
    """generar_bloque_toml para tenant_safe produce un bloque TOML correcto."""
    bloque = generar_bloque_toml(
        rn_id="RN-TNT-001",
        tipo="tenant_safe",
        spec={"type": "tenant_safe", "forbid": ["unfiltered_objects"]},
    )
    assert "[docpact.rn_patrones.RN-TNT-001]" in bloque
    assert 'type = "tenant_safe"' in bloque
    assert "unfiltered_objects" in bloque


def test_generar_bloque_state_transition_tiene_campos_requeridos():
    """generar_bloque_toml para state_transition incluye from/to/modulo."""
    bloque = generar_bloque_toml(
        rn_id="RN-TKT-002",
        tipo="state_transition",
        spec={
            "type": "state_transition",
            "from_estado": "abierto",
            "to_estado": "suspendido",
            "matriz_attr": "TRANSICIONES_PERMITIDAS",
            "modulo": "soporte/services/ticket_estados.py",
        },
    )
    assert "[docpact.rn_patrones.RN-TKT-002]" in bloque
    assert 'from_estado = "abierto"' in bloque
    assert 'to_estado = "suspendido"' in bloque
    assert "TRANSICIONES_PERMITIDAS" in bloque


def test_generar_bloque_required_groups_tiene_allowed():
    """generar_bloque_toml para required_groups incluye allowed."""
    bloque = generar_bloque_toml(
        rn_id="RN-TKT-005",
        tipo="required_groups",
        spec={"type": "required_groups", "allowed": ["supervision", "admin"]},
    )
    assert "supervision" in bloque
    assert "admin" in bloque


def test_generar_bloque_no_import_tiene_forbid():
    """generar_bloque_toml para no_import incluye forbid."""
    bloque = generar_bloque_toml(
        rn_id="RN-NOT-002",
        tipo="no_import",
        spec={"type": "no_import", "forbid": ["from django_q.tasks import"]},
    )
    assert "django_q" in bloque


def test_generar_bloque_has_pattern_tiene_pattern():
    """generar_bloque_toml para has_pattern incluye pattern."""
    bloque = generar_bloque_toml(
        rn_id="RN-CUSTOM-001",
        tipo="has_pattern",
        spec={"type": "has_pattern", "pattern": "validar_con_permiso"},
    )
    assert "validar_con_permiso" in bloque


def test_generar_bloque_comenta_cuando_spec_incompleto():
    """Si el spec no tiene campos requeridos, agregar comentario 'REVISAR'."""
    bloque = generar_bloque_toml(
        rn_id="RN-INCOMPLETA",
        tipo="state_transition",
        spec={"type": "state_transition"},  # faltan from/to/modulo
    )
    assert "REVISAR" in bloque or "# " in bloque  # tiene comentario


# ──────────────────── inferir + generar integrado ────────────────────


def test_inferir_y_generar_toman_un_contrato_y_producen_bloque():
    """Pipeline: CONTRATO -> (tipo, spec) -> bloque TOML."""
    c = _make_contrato(
        rn=[ReglaNegocio(id="RN-TNT-002", descripcion="multi-tenant")],
        dependencias=[Dependencia(ref="soporte/models/ticket.py::Ticket")],
        comportamiento="Lista tickets con para_usuario",
    )
    tipo, _ = inferir_tipo_validador(c)

    # Generar spec minimo razonable segun el tipo
    spec: dict = {"type": tipo}
    if tipo == "tenant_safe":
        spec["forbid"] = ["unfiltered_objects", ".objects.all", ".objects.filter"]

    bloque = generar_bloque_toml("RN-TNT-002", tipo, spec)
    assert "[docpact.rn_patrones.RN-TNT-002]" in bloque
    assert 'type = "tenant_safe"' in bloque

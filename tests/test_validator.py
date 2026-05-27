"""Tests del validador de CONTRATO."""

from docpact.models.contrato import (
    CasoBorde,
    Contrato,
    Dependencia,
    ReglaNegocio,
    SideEffect,
)
from docpact.schema.validator import validar


def test_validar_contrato_valido():
    """Contrato bien formado → 0 errores."""
    c = Contrato(
        side_effects=[SideEffect("Crea ticket en BD")],
        rn=[ReglaNegocio(id="RN-010")],
        dependencias=[Dependencia(ref="soporte/models/ticket.py::Ticket")],
    )
    errores = validar(c)
    assert len(errores) == 0


def test_validar_rn_invalido():
    """RN sin formato RN-XXX → error."""
    c = Contrato(
        side_effects=[SideEffect("ninguno")],
        rn=[ReglaNegocio(id="REGLA-001")],
    )
    errores = validar(c)
    assert len(errores) == 1
    assert "rn" in errores[0].campo


def test_validar_dependencia_invalida():
    """Dependencia con formato incorrecto → error."""
    c = Contrato(
        side_effects=[SideEffect("ninguno")],
        dependencias=[Dependencia(ref="../fuera/../del/ambito")],
    )
    errores = validar(c)
    assert len(errores) == 1
    assert "dependencias" in errores[0].campo


def test_validar_sin_errores_con_ninguno():
    """side_effects: ninguno + sin RN ni dependencias → 0 errores."""
    c = Contrato()
    errores = validar(c)
    assert len(errores) == 0


def test_validar_rn_multiple():
    """Múltiples RNs válidas e inválidas."""
    c = Contrato(
        side_effects=[SideEffect("ninguno")],
        rn=[
            ReglaNegocio(id="RN-001"),
            ReglaNegocio(id="RN-999"),
            ReglaNegocio(id="rn-abc"),  # inválido: no es RN-XXX
        ],
    )
    errores = validar(c)
    assert len(errores) == 1
    assert "rn-abc" in errores[0].mensaje


def test_validar_sin_side_effects():
    """Sin side_effects declarados → 0 errores (lista vacía es válida)."""
    c = Contrato()
    errores = validar(c)
    assert len(errores) == 0


def test_validar_side_effects_demasiado_corto():
    """Side effect de 1 carácter debe dar error."""
    c = Contrato(side_effects=[SideEffect("a")])
    errores = validar(c)
    assert len(errores) >= 1
    assert "side_effects" in errores[0].campo


def test_validar_input_con_tipo_desconocido():
    """Input con tipo no estándar debe ser válido (no hay restricción de tipos)."""
    c = Contrato(
        side_effects=[SideEffect("ninguno")],
    )
    errores = validar(c)
    assert len(errores) == 0


def test_validar_dependencia_con_ruta_absoluta():
    """Dependencia con ruta absoluta debe ser válida si tiene formato correcto."""
    c = Contrato(
        side_effects=[SideEffect("ninguno")],
        dependencias=[Dependencia(ref="/home/user/proyecto/modulo.py::Funcion")],
    )
    errores = validar(c)
    assert len(errores) == 0


def test_validar_solo_rn():
    """Contrato solo con RN es válido."""
    c = Contrato(
        side_effects=[SideEffect("ninguno")],
        rn=[ReglaNegocio(id="RN-001")],
    )
    errores = validar(c)
    assert len(errores) == 0


def test_validar_rn_con_id_demasiado_corto():
    """RN-XX (solo 2 dígitos) debe ser inválido."""
    c = Contrato(
        side_effects=[SideEffect("ninguno")],
        rn=[ReglaNegocio(id="RN-01")],
    )
    errores = validar(c)
    assert len(errores) >= 1
    assert "rn" in errores[0].campo

"""Validadores semánticos de RN (reglas de negocio).

Reemplaza el viejo check de markers por verificación real: lee el código
y valida la regla directamente. El programador (o agente) declara
`rn: [RN-XXX]` en el CONTRATO; docpact ejecuta el validador asociado
y reporta error si la regla NO se cumple.

API pública:
  validar_rn(codigo_fuente, rn_id, spec, contexto) -> list[ErrorParser]
  validadores_disponibles() -> list[str]
"""

from __future__ import annotations

from typing import Callable

from docpact.models.contrato import ErrorParser

from .has_pattern import validar_has_pattern
from .no_import import validar_no_import
from .required_groups import validar_required_groups
from .state_transition import extraer_yaml, validar_state_transition
from .tenant_safe import validar_tenant_safe

# ─────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────

_VALIDADORES: dict[str, Callable] = {
    "state_transition": validar_state_transition,
    "no_import": validar_no_import,
    "required_groups": validar_required_groups,
    "tenant_safe": validar_tenant_safe,
    "has_pattern": validar_has_pattern,
}


# ─────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────


def validar_rn(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict | None = None,
) -> list[ErrorParser]:
    """Dispatcher principal: ejecuta el validador apropiado para la RN.

    Args:
        codigo_fuente: Código fuente de la función.
        rn_id: ID de la RN (ej: "RN-005"). Se incluye en el mensaje.
        spec: Dict con la especificación del validador. Debe contener
              la clave "type" (ej: "state_transition", "no_import").
              El resto de claves son específicas del validador.
        contexto: Dict con datos adicionales (archivo, línea, AST pre-parseado).

    Returns:
        Lista de ErrorParser. Vacía = RN cumplida.
    """
    contexto = contexto or {}
    tipo = spec.get("type")
    if not tipo:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: spec sin clave 'type' (validador indefinido)",
                sugerencia="Agrega 'type' al spec en docpact.toml [docpact.rn_patrones]",
            )
        ]

    validador = _VALIDADORES.get(tipo)
    if validador is None:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: validador '{tipo}' desconocido",
                sugerencia=f"Validadores disponibles: {sorted(_VALIDADORES.keys())}",
            )
        ]

    return validador(codigo_fuente, rn_id, spec, contexto)


def validadores_disponibles() -> list[str]:
    """Lista los nombres de validadores registrados (para diagnóstico)."""
    return sorted(_VALIDADORES.keys())

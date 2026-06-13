"""Validadores semánticos de RN — shim de compatibilidad.

Este módulo re-exporta la API pública desde ``docpact.checker.semantic``.
Mantenido para compatibilidad con imports existentes::

    from docpact.checker.semantic_rn import validar_rn, validadores_disponibles
"""

from docpact.checker.semantic import (
    _VALIDADORES,
    validar_rn,
    validadores_disponibles,
)
from docpact.checker.semantic.state_transition import (
    extraer_yaml as _extraer_yaml,
)

__all__ = ["validar_rn", "validadores_disponibles", "_extraer_yaml"]

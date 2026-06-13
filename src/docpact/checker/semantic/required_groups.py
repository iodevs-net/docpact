"""Validador: required_groups — valida whitelist de grupos requeridos."""

from __future__ import annotations

import re

from docpact.models.contrato import ErrorParser


_GROUP_CHECK_PATTERNS = re.compile(
    r"groups\.filter|is_superuser|has_perm|grupo|group", re.IGNORECASE
)


def validar_required_groups(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict,
) -> list[ErrorParser]:
    """Valida que la función solo aplique si el usuario pertenece a grupos autorizados.

    Spec esperado:
        type = "required_groups"
        allowed = ["administracion", "supervision"]   # whitelist
        # o, en negativo:
        forbidden = ["cliente"]                        # blacklist

    Estrategia: busca checks tipo `groups.filter(name=...)` o
    `is_superuser` en el código. Si la función no chequea NADA, falla
    (asumimos que falta la validación).
    """
    allowed = spec.get("allowed", [])
    forbidden = spec.get("forbidden", [])

    if not allowed and not forbidden:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: required_groups sin 'allowed' o 'forbidden'",
            )
        ]

    if not has_group_check(codigo_fuente):
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: no se detectó validación de grupo en la función",
                sugerencia=(
                    "Agrega `usuario.groups.filter(name=...)` o "
                    "`getattr(usuario, 'is_superuser', False)` al inicio"
                ),
            )
        ]

    return []


def has_group_check(codigo_fuente: str) -> bool:
    """Retorna True si el código contiene alguna verificación de grupo."""
    return bool(_GROUP_CHECK_PATTERNS.search(codigo_fuente))

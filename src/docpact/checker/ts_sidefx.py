"""Verificador de side effects para TypeScript.

Busca llamadas a APIs HTTP, fetch, mutaciones y persistencia
en código fuente TypeScript usando regex sobre texto plano.
"""

from __future__ import annotations

import re

# Patrones de llamadas que constituyen side effects en TS
_PATRONES: list[re.Pattern[str]] = [
    re.compile(r"api\.(?:post|put|delete|get)\s*\("),
    re.compile(r"axios\.(?:post|get|put|delete)\s*\("),
    re.compile(r"client\.(?:post|put|delete)\s*\("),
    re.compile(r"\bfetch\s*\("),
    re.compile(r"\.(?:create|save|update|delete)\s*\("),
    re.compile(r"\bmutate\s*\("),
    # Inertia router (SPA navigation que muta estado en servidor)
    re.compile(r"router\.(?:get|post|put|delete|patch|reload)\s*\("),
    re.compile(r"router\.visit\s*\("),
    # window.open = navegación a URL de backend
    re.compile(r"window\.open\s*\("),
]


def _tiene_llamadas_sidefx(codigo: str) -> bool:
    """Retorna True si el código contiene al menos una llamada de side effect."""
    for pat in _PATRONES:
        if pat.search(codigo):
            return True
    return False


def _declaro_ninguno(declarados: list[str]) -> bool:
    """Retorna True si la lista equivale a 'ninguno'."""
    return not declarados or any(d.strip().lower() == "ninguno" for d in declarados)


def check_side_effects_ts(
    codigo: str,
    side_effects_declarados: list[str],
) -> list[str]:
    """Verifica side effects declarados vs. llamadas reales en código TS.

    Args:
        codigo: Código fuente TypeScript de la función.
        side_effects_declarados: Lista de side effects del CONTRATO.

    Returns:
        Lista de mensajes de error. Vacía si todo está consistente.
    """
    hay_llamadas = _tiene_llamadas_sidefx(codigo)

    # Caso 1: hay llamadas reales pero declaró "ninguno" o vacío
    if hay_llamadas and _declaro_ninguno(side_effects_declarados):
        return ["Se detectaron llamadas API pero side_effects: ninguno"]

    # Caso 2: declaró side effects pero no se encontraron llamadas
    if not hay_llamadas and not _declaro_ninguno(side_effects_declarados):
        return ["Declaro side effects pero no se detectaron llamadas"]

    # Caso match: ambos lados consistentes
    return []

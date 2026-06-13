"""Validador: has_pattern — validador genérico de patrón (compat con rn_patterns)."""

from __future__ import annotations

from docpact.models.contrato import ErrorParser


def validar_has_pattern(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict,
) -> list[ErrorParser]:
    """Validador genérico: el código de la función contiene un patrón dado.

    Spec esperado:
        type = "has_pattern"
        patron = "INTERVALO_RE_RECORDATORIO"  # string a buscar (soporta | para OR)
        line_offset = 0  # opcional, offset para mensajes

    Este validador es el sucesor directo de `verificar_rn_patrones` y
    mantiene retrocompatibilidad con configs `docpact.toml` existentes.
    """
    patron = spec.get("patron", "")
    if not patron:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: has_pattern sin 'patron'",
            )
        ]

    lineas = codigo_fuente.split("\n")
    line_offset = spec.get("line_offset", 0)

    for i, linea in enumerate(lineas, 1):
        for p in patron.split("|"):
            if p.strip() and p.strip() in linea:
                return []  # Encontrado — regla cumplida

    return [
        ErrorParser(
            "rn_semantica",
            f"RN {rn_id}: patrón '{patron}' no encontrado en el cuerpo de la función",
            linea=line_offset,
            sugerencia=f"Agrega una línea que contenga '{patron}'",
        )
    ]

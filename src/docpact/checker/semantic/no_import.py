"""Validador: no_import — detecta imports prohibidos por patrón."""

from __future__ import annotations

import ast
import re

from docpact.models.contrato import ErrorParser

from ._common import match_any


def validar_no_import(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict,
) -> list[ErrorParser]:
    """Detecta imports prohibidos por patrón.

    Spec esperado:
        type = "no_import"
        patterns = ["facturacion_erp", "*sii*", "stripe"]   # globs
        en_archivo = "soporte/services/facturacion.py"        # opcional, limita el check

    Si `en_archivo` está definido y la función NO está en ese archivo, pasa.
    Si no está definido, se chequea en el cuerpo de la función.
    """
    patterns = spec.get("patterns", [])
    en_archivo = spec.get("en_archivo")

    if not patterns:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: no_import sin 'patterns'",
            )
        ]

    # Si hay restricción de archivo, validar que la función esté en ese archivo
    if en_archivo:
        archivo_actual = contexto.get("archivo", "")
        if en_archivo not in archivo_actual:
            return []  # La función no es responsable de esta regla

    # Compilar patterns a regex (soporta * wildcard)
    regexes = [re.compile(p.replace(".", r"\.").replace("*", ".*")) for p in patterns]

    # Buscar imports
    try:
        tree = ast.parse(codigo_fuente)
    except SyntaxError:
        return []

    errores: list[ErrorParser] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if match_any(regexes, alias.name):
                    errores.append(
                        ErrorParser(
                            "rn_semantica",
                            f"RN {rn_id}: import prohibido '{alias.name}'",
                            linea=node.lineno,
                            sugerencia=f"Patrones prohibidos: {patterns}",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            modulo = node.module or ""
            if match_any(regexes, modulo):
                errores.append(
                    ErrorParser(
                        "rn_semantica",
                        f"RN {rn_id}: import prohibido 'from {modulo} import ...'",
                        linea=node.lineno,
                        sugerencia=f"Patrones prohibidos: {patterns}",
                    )
                )

    return errores

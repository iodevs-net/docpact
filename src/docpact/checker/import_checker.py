"""Verificador de imports locales que duplican dependencias del CONTRATO.

Detecta `from X import Y` inline dentro del cuerpo de una función cuyo
símbolo Y ya está declarado como dependencia del CONTRATO. Previene que
agentes automáticos eliminen el import pensando que el CONTRATO lo reemplaza.
"""

from __future__ import annotations

import ast
from typing import Optional

from docpact.models.contrato import ErrorParser


def check_inline_imports(
    codigo: str,
    dependencias: list[str],
    nombre_funcion: str,
    archivo: str,
    linea_base: int,
) -> list[ErrorParser]:
    """Busca imports inline que duplican dependencias declaradas en el CONTRATO.

    Args:
        codigo: Código fuente de la función (solo el cuerpo).
        dependencias: Lista de refs de dependencias del CONTRATO
                     (ej: "soporte/models/ticket.py::Ticket").
        nombre_funcion: Nombre de la función, para el reporte.
        archivo: Ruta del archivo, para el reporte.
        linea_base: Línea donde comienza la función, para ajustar números.

    Returns:
        Lista de ErrorParser con hallazgos WARNING.
    """
    errores: list[ErrorParser] = []

    if not codigo.strip() or not dependencias:
        return errores

    import textwrap

    try:
        codigo_dedent = textwrap.dedent(codigo)
        tree = ast.parse(codigo_dedent)
    except SyntaxError:
        return errores

    # Construir conjunto de símbolos de dependencias: "modulo/archivo.py::Simbolo" -> "Simbolo"
    simbolos_contrato: set[str] = set()
    for dep in dependencias:
        if "::" in dep:
            simbolo = dep.split("::", 1)[1].strip()
            if simbolo:
                simbolos_contrato.add(simbolo)

    if not simbolos_contrato:
        return errores

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        modulo = node.module or ""
        for alias in node.names:
            # Chequear tanto el nombre original importado como el alias local
            nombre_coincide = alias.name in simbolos_contrato
            alias_coincide = (
                alias.asname is not None and alias.asname in simbolos_contrato
            )

            if not nombre_coincide and not alias_coincide:
                continue

            linea_real = (node.lineno or 1) + linea_base - 1

            # Construir representación textual del import
            if alias.asname:
                import_repr = f"from {modulo} import {alias.name} as {alias.asname}"
            else:
                import_repr = f"from {modulo} import {alias.name}"

            errores.append(
                ErrorParser(
                    campo="dependencias",
                    mensaje=(
                        f"Import local '{import_repr}' "
                        f"duplica dependencia del CONTRATO. "
                        f"NO eliminar el import — el CONTRATO no lo reemplaza."
                    ),
                    linea=linea_real,
                    sugerencia=(
                        f"Mantener '{import_repr}' "
                        f"aunque {alias.name} esté en las dependencias del CONTRATO"
                    ),
                )
            )

    return errores

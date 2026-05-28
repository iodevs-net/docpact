"""Verificador de cross-reference RN.

Si la funcion A declara RN-XXX en su CONTRATO y llama a la funcion B
(del mismo proyecto), verifica que B tambien tenga RN-XXX marcada
en su codigo o CONTRATO.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple


class RNCrossError(NamedTuple):
    """Error de cross-reference RN no propagada."""

    archivo: str
    linea: int
    mensaje: str
    sugerencia: str = ""


# Patron para detectar llamadas a funciones: nombre_funcion(
_CALL_RE = re.compile(r"(?<!def )(?<!\.)([a-z_][a-zA-Z0-9_]+)\s*\(")


def _extraer_llamadas(codigo: str) -> set[str]:
    """Extrae nombres de funciones llamadas en el codigo."""
    llamadas: set[str] = set()
    for m in _CALL_RE.finditer(codigo):
        nombre = m.group(1)
        # Saltar palabras reservadas de Python
        if nombre in (
            "if", "for", "while", "with", "not", "and", "or", "in",
            "is", "assert", "raise", "return", "yield", "del",
            "elif", "except", "finally", "try", "lambda",
        ):
            continue
        # Saltar builtins de Python que parecen llamadas a funcion
        if nombre in (
            "list", "dict", "str", "int", "float", "bool", "set", "tuple",
            "len", "range", "type", "isinstance", "hasattr", "getattr",
            "setattr", "sum", "min", "max", "abs", "all", "any",
            "enumerate", "zip", "map", "filter", "reversed", "sorted",
            "open", "print", "input", "super", "object", "property",
            "staticmethod", "classmethod", "iter", "next", "repr",
            "ord", "chr", "hex", "oct", "bin", "format", "callable",
            "issubclass", "eval", "exec", "compile", "globals", "locals",
            "vars", "dir", "id", "hash", "pow", "round", "divmod",
        ):
            continue
        # Saltar metodos de objeto (ej: .split, .join)
        if codigo[max(0, m.start() - 1)] == ".":
            continue
        llamadas.add(nombre)
    return llamadas


def _tiene_rn_en_codigo(codigo: str, rn_id: str) -> bool:
    """Verifica si el codigo contiene # RN-XXX con borde de palabra."""
    return bool(re.search(rf"#\s*{re.escape(rn_id)}\b", codigo))


def verificar_cross_reference(
    archivo: str,
    codigo_funcion: str,
    rn_ids: list[str],
    todas_las_funciones: dict[str, dict[str, str]],
) -> list[RNCrossError]:
    """Verifica que las funciones llamadas tambien tengan las RNs."""
    errores: list[RNCrossError] = []
    llamadas = _extraer_llamadas(codigo_funcion)

    for rn_id in rn_ids:
        for llamada in llamadas:
            info = todas_las_funciones.get(llamada)
            if not info:
                continue
            # Verificar que la funcion destino tenga RN en su codigo
            codigo_destino = info.get("codigo", "")
            if not _tiene_rn_en_codigo(codigo_destino, rn_id):
                errores.append(
                    RNCrossError(
                        archivo=archivo,
                        linea=0,
                        mensaje=f"'{rn_id}' declarada pero '{llamada}' no la tiene marcada",
                        sugerencia=f"Agregar '# {rn_id}' en la funcion '{llamada}'",
                    )
                )

    return errores


def build_funcion_map(
    resultados_funciones: list,
    fuentes: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Construye mapa de todas las funciones del proyecto con su codigo."""
    mapa: dict[str, dict[str, str]] = {}
    for rf in resultados_funciones:
        nombre = getattr(rf, "nombre", "")
        archivo = getattr(rf, "archivo", "")
        if not nombre or not archivo:
            continue
        fuente = fuentes.get(archivo, "")
        if not fuente:
            continue
        mapa[nombre] = {"codigo": fuente, "archivo": archivo}
    return mapa

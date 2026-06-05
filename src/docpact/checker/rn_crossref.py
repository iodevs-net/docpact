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
# Agregamos \b para evitar coincidencias parciales con nombres de métodos de objeto (ej: self.get_client_ip)
_CALL_RE = re.compile(r"(?<!def )(?<!\.)\b([a-z_][a-zA-Z0-9_]+)\s*\(")


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


def _extraer_rn_ids_de_contrato(codigo: str) -> set[str]:
    """Extrae IDs RN-XXX del CONTRATO docstring de una función.

    Busca líneas con formato `rn: [RN-XXX, RN-YYY]` o `rn: [RN-XXX]`
    dentro del docstring de la función. KISS: solo busca el patrón
    `rn: [RN-...` en las primeras líneas (el docstring está al inicio).
    """
    patron = re.compile(r"rn:\s*\[([^\]]*)\]", re.MULTILINE)
    ids: set[str] = set()
    for match in patron.finditer(codigo):
        contenido = match.group(1)
        # Extraer todos los RN-XXX del contenido
        for rn_match in re.finditer(r"RN-[\w-]+", contenido):
            ids.add(rn_match.group())
    return ids


def verificar_cross_reference(
    archivo: str,
    codigo_funcion: str,
    rn_ids: list[str],
    todas_las_funciones: dict[str, list[dict[str, str]]],
) -> list[RNCrossError]:
    """Verifica que las funciones llamadas tambien tengan las RNs.

    Logica corregida: solo emite warning si la funcion destino
    TAMBIEN declara la RN en su CONTRATO. Si la funcion destino
    no declara esa RN, es responsabilidad exclusiva de la llamante
    (la regla NO es cross-reference, es local a la llamante).

    ANTES: emitia warning si la cadena de llamadas no tenia el
    marker, lo cual producia 100+ falsos positivos en iodesk
    (utilities como get_tickets_para_usuario, render_email_html
    recibian warnings de RNs que NO implementan).
    """
    errores: list[RNCrossError] = []
    llamadas = _extraer_llamadas(codigo_funcion)

    for rn_id in rn_ids:
        for llamada in llamadas:
            defs = todas_las_funciones.get(llamada)
            if not defs:
                continue
            # Intentar resolver al mismo archivo primero para evitar colisiones
            definicion = None
            for d in defs:
                if d.get("archivo") == archivo:
                    definicion = d
                    break

            if not definicion:
                definicion = defs[0]

            codigo_destino = definicion.get("codigo", "")

            # FIX: si la funcion destino NO declara esta RN en su CONTRATO,
            # no es problema de cross-reference. La llamante es responsable
            # unica de la regla. NO emitir warning.
            rn_en_contrato_destino = _extraer_rn_ids_de_contrato(codigo_destino)
            if rn_id not in rn_en_contrato_destino:
                continue

            # La funcion destino SI declara esta RN. Verificar que tenga
            # el marker en su cuerpo.
            if not _tiene_rn_en_codigo(codigo_destino, rn_id):
                errores.append(
                    RNCrossError(
                        archivo=archivo,
                        linea=0,
                        mensaje=(
                            f"'{rn_id}' declarada en CONTRATO de '{llamada}' "
                            f"pero no tiene marker en su cuerpo"
                        ),
                        sugerencia=(
                            f"Agregar '# {rn_id}' en la linea donde se "
                            f"implementa la regla en '{llamada}'"
                        ),
                    )
                )

    return errores


def build_funcion_map(
    resultados_funciones: list,
    fuentes: dict[str, str],
) -> dict[str, list[dict[str, str]]]:
    """Construye mapa de todas las funciones del proyecto con sus definiciones."""
    mapa: dict[str, list[dict[str, str]]] = {}
    for rf in resultados_funciones:
        nombre = getattr(rf, "nombre", "")
        archivo = getattr(rf, "archivo", "")
        if not nombre or not archivo:
            continue
        fuente = fuentes.get(archivo, "")
        if not fuente:
            continue
        if nombre not in mapa:
            mapa[nombre] = []
        mapa[nombre].append({"codigo": fuente, "archivo": archivo})
    return mapa


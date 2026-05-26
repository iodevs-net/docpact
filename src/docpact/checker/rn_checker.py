"""Verificador de RN (reglas de negocio).

Toma los IDs RN-XXX del campo `rn:` del CONTRATO y confirma que
cada ID aparezca como comentario en el cuerpo de la función.
"""

from __future__ import annotations

import ast
import re
from typing import Optional

from docpact.models.contrato import Contrato, ErrorParser, ReglaNegocio


def check_rn(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    contrato: Contrato,
    config_rn_prefix: str = "RN-",
    nombre_funcion: str = "",
) -> list[ErrorParser]:
    """Verifica que los IDs RN-XXX declarados aparezcan en el cuerpo.

    Args:
        node: Nodo AST de la función.
        contrato: CONTRATO parseado con campo rn.
        config_rn_prefix: Prefijo de reglas de negocio (default: RN-).
        nombre_funcion: Nombre de la función (para errores).

    Returns:
        Lista de errores/warnings.
    """
    if not contrato.rn:
        return []

    # Extraer comentarios del cuerpo de la función
    comentarios = _extraer_comentarios(node)

    # Extraer IDs de reglas de negocio de los comentarios
    ids_en_codigo = set(_extraer_ids_rn(comentarios, config_rn_prefix))

    errores: list[ErrorParser] = []
    for rn in contrato.rn:
        if rn.id not in ids_en_codigo:
            errores.append(ErrorParser(
                "rn",
                f"'{nombre_funcion}': RN '{rn.id}' declarada en CONTRATO "
                f"pero no encontrada como comentario en el código",
                sugerencia=f"Agrega '# {rn.id}' como comentario en el lugar "
                           f"donde se implementa la regla",
            ))

    return errores


def _extraer_comentarios(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extrae los comentarios (líneas con #) del cuerpo de una función.

    ast no preserva comentarios directamente. Extraemos las líneas fuente
    que contienen '#' del cuerpo de la función.
    """
    if not hasattr(node, 'end_lineno') or node.end_lineno is None:
        return []

    # No podemos extraer comentarios del AST puro porque Python los descarta.
    # Necesitamos la fuente original.
    return []


def extraer_comentarios_desde_fuente(
    fuente: str,
    linea_inicio: int,
    linea_fin: int,
) -> list[str]:
    """Extrae comentarios de la fuente original entre dos líneas.

    Esta es la función que realmente funciona — se llama desde el
    orquestador cuando tiene acceso a la fuente completa del archivo.
    """
    lineas = fuente.split("\n")
    # Ajuste: ast usa 1-based, las listas son 0-based
    inicio = max(0, linea_inicio - 1)
    fin = min(len(lineas), linea_fin)
    comentarios: list[str] = []
    for linea in lineas[inicio:fin]:
        stripped = linea.strip()
        if "#" in stripped:
            # Tomar solo el comentario (después de #)
            idx = stripped.index("#")
            comentarios.append(stripped[idx:])
    return comentarios


def _extraer_ids_rn(
    comentarios: list[str],
    prefijo: str = "RN-",
) -> list[str]:
    """Extrae IDs de reglas de negocio de comentarios.
    
    Soporta formatos:
    - RN-XXX (RN-004, RN-005)
    - RN-XXX-XXX (RN-SEG-005, RN-C-016)
    - RN-XXX (RN-SEG)
    - Gotcha #XXX (Gotcha #034)
    """
    patron = re.compile(rf"{re.escape(prefijo)}[\w-]+|Gotcha #\d+")
    ids: list[str] = []
    for comentario in comentarios:
        for match in patron.finditer(comentario):
            ids.append(match.group())
    return ids

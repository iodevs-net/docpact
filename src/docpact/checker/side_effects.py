"""AST walker para detección de side effects.

Recorre el AST de una función y encuentra llamadas que coincidan
con patrones de side effects configurados (db_write, email, etc.).
"""

from __future__ import annotations

import ast
from typing import Optional

from docpact.models.contrato import Contrato, ErrorParser, SideEffect
from docpact.config import DocpactConfig


def check_side_effects(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    contrato: Contrato,
    config: DocpactConfig,
    nombre_funcion: str,
    nombre_archivo: str,
) -> list[ErrorParser]:
    """Verifica que los side_effects declarados coincidan con los reales.

    Args:
        node: Nodo AST de la función.
        contrato: CONTRATO parseado.
        config: Configuración de docpact.
        nombre_funcion: Nombre de la función (para errores).
        nombre_archivo: Nombre del archivo (para errores).

    Returns:
        Lista de errores de verificación.
    """
    errores: list[ErrorParser] = []
    llamadas = _extraer_llamadas(node)
    efectos_encontrados = _clasificar_llamadas(llamadas, config)
    efectos_declarados = [s.descripcion.lower().strip() for s in contrato.side_effects]

    # Caso 1: declaró "ninguno" pero hay efectos reales
    if not efectos_declarados and efectos_encontrados:
        cats = ", ".join(efectos_encontrados)
        errores.append(ErrorParser(
            "side_effects",
            f"'{nombre_funcion}' declara side_effects: ninguno, "
            f"pero se detectaron: {cats}",
            sugerencia=f"Agrega 'side_effects: {cats}' al CONTRATO, "
                       f"o elimina las llamadas: {', '.join(efectos_encontrados)}",
        ))

    # Caso 2: declaró efectos pero NO se encontró NINGUNA categoría
    # (descripciones en español vs categorías técnicas son incomparables)
    # Solo advertir si hay 0 efectos encontrados siendo que se declararon
    if efectos_declarados and not efectos_encontrados:
        errores.append(ErrorParser(
            "side_effects",
            f"'{nombre_funcion}': declaró side_effects pero no se "
            f"detectaron llamadas con patrones conocidos",
            sugerencia="Si la función delega a otros servicios, está bien. "
                       "Agrega patrones personalizados en docpact.toml si quieres tracking fino.",
        ))

    return errores


def _extraer_llamadas(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extrae todas las llamadas a funciones del cuerpo de una función.

    Retorna strings como 'Clase.metodo', 'Modelo.objects.create',
    'registrar_evento_bitacora', etc.
    'registrar_evento_bitacora', etc.
    """
    llamadas: list[str] = []

    class CallVisitor(ast.NodeVisitor):
        def visit_Call(self, call_node: ast.Call) -> None:
            nombre = _ast_nombre_llamada(call_node.func)
            if nombre:
                llamadas.append(nombre)
            self.generic_visit(call_node)

    CallVisitor().visit(node)
    return llamadas

def _ast_nombre_llamada(func_node: ast.AST) -> Optional[str]:
    """Convierte un nodo AST de función a su nombre como string.

    ast.Attribute (encadenado): obj.method → str
    ast.Name (simple): nombre_funcion → str
    """
    if isinstance(func_node, ast.Attribute):
        # Llamada encadenada: obj.method
        base = _ast_nombre_llamada(func_node.value)
        if base:
            return f"{base}.{func_node.attr}"
        return func_node.attr
    elif isinstance(func_node, ast.Name):
        return func_node.id
    return None


def _clasificar_llamadas(
    llamadas: list[str],
    config: DocpactConfig,
) -> list[str]:
    """Clasifica una lista de llamadas en categorías de side effects.

    Returns:
        Lista de categorías encontradas (db_write, email, audit, etc.)
    """
    encontrados: list[str] = []
    for llamada in llamadas:
        for categoria, patrones in config.patrones_compilados.items():
            if any(p.search(llamada) for p in patrones):
                if categoria not in encontrados:
                    encontrados.append(categoria)
    return encontrados

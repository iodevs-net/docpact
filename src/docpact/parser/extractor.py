"""Extractor de docstrings del AST Python.

Usa el módulo `ast` de la stdlib para recorrer funciones, métodos y clases
públicas y extraer sus docstrings.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional


def extraer_docstrings(
    archivo: str | Path,
    *,
    incluir_privadas: bool = False,
) -> list[tuple[int, str, str, str]]:
    """Extrae docstrings de funciones y métodos públicos de un archivo Python.

    Args:
        archivo: Ruta al archivo .py.
        incluir_privadas: Si True, incluye funciones con prefijo _.

    Returns:
        Lista de tuplas (linea, nombre, tipo, docstring) donde tipo es
        "function", "method" o "class".

    Raises:
        FileNotFoundError: Si el archivo no existe.
        SyntaxError: Si el archivo tiene errores de sintaxis.
    """
    path = Path(archivo)
    if not path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {archivo}")

    with open(path, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source, filename=str(path))
    resultado: list[tuple[int, str, str, str]] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            _extraer_clase(node, path, incluir_privadas, resultado)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _extraer_funcion(node, path, "function", incluir_privadas, resultado)

    return resultado


def _extraer_clase(
    node: ast.ClassDef,
    path: Path,
    incluir_privadas: bool,
    resultado: list[tuple[int, str, str, str]],
) -> None:
    """Extrae docstrings de una clase y sus métodos."""
    # Docstring de la clase
    doc = ast.get_docstring(node, clean=False)
    if doc:
        resultado.append((node.lineno, node.name, "class", doc))

    # Métodos de la clase
    for item in ast.iter_child_nodes(node):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _extraer_funcion(item, path, "method", incluir_privadas, resultado)


def _extraer_funcion(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    path: Path,
    tipo: str,
    incluir_privadas: bool,
    resultado: list[tuple[int, str, str, str]],
) -> None:
    """Extrae docstring de una función individual."""
    if not incluir_privadas and node.name.startswith("_"):
        return

    doc = ast.get_docstring(node, clean=False)
    if doc:
        resultado.append((node.lineno, node.name, tipo, doc))

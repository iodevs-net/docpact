"""Helpers compartidos por los validadores semánticos."""

from __future__ import annotations

import ast


def extraer_dict_ast(tree: ast.AST, nombre: str) -> dict | None:
    """Extrae un dict literal asignado a `nombre` a nivel de modulo.

    Soporta tanto `=` (ast.Assign) como asignacion anotada `: T = ...`
    (ast.AnnAssign), p.ej. `M: dict[str, list[str]] = {...}`.
    """
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == nombre:
                    if isinstance(node.value, ast.Dict):
                        return dict_literal_a_python(node.value)
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == nombre
                and isinstance(node.value, ast.Dict)
            ):
                return dict_literal_a_python(node.value)
    return None


def dict_literal_a_python(node: ast.Dict) -> dict:
    """Convierte un ast.Dict con keys/values a dict Python."""
    resultado: dict = {}
    for key, value in zip(node.keys, node.values):
        k = extract_str_or_name(key)
        if k is None:
            continue
        resultado[k] = flatten_list(value)
    return resultado


def flatten_list(node: ast.AST) -> list[str]:
    """Extrae strings de una lista, incluyendo concatenaciones y listas literales."""
    resultado: list[str] = []
    for child in flatten_binop(node):
        s = extract_str_or_name(child)
        if s is not None:
            resultado.append(s)
    return resultado


def flatten_binop(node: ast.AST) -> list[ast.AST]:
    """Aplana un ast.BinOp(Add) en una lista de nodos hoja.

    Tambien expande ast.List en sus elementos individuales.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return flatten_binop(node.left) + flatten_binop(node.right)
    if isinstance(node, ast.List):
        result = []
        for elt in node.elts:
            result.extend(flatten_binop(elt))
        return result
    return [node]


def extract_str_or_name(node: ast.AST) -> str | None:
    """Extrae string de Constant, Name.id, o ultimo segmento de Attribute."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def match_any(regexes: list, texto: str) -> bool:
    """Retorna True si alguno de los regex coincide con el texto."""
    return any(r.search(texto) for r in regexes)

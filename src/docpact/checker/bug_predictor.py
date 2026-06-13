"""Predictor de bugs basado en AST.

Detecta patrones comunes de bugs en Python usando análisis de AST.
Inspirado en pylint, flake8, y SonarQube pero lightweight.

Patrones detectados:
- Mutable default arguments
- Bare/broad except
- open() sin context manager
- Variables sin usar
- Redefinición de argumentos
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass
class BugPredicho:
    """Un bug potencial detectado por análisis estático."""

    tipo: str
    severidad: str  # error, warning, info
    mensaje: str
    sugerencia: str
    archivo: str
    linea: int
    funcion: str


# ── Checkers individuales ──


def _check_mutable_defaults(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta argumentos mutables como defaults (def f(x=[]))."""
    bugs = []
    for default in node.args.defaults:
        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
            bugs.append(BugPredicho(
                tipo="mutable_default",
                severidad="warning",
                mensaje=f"Argumento default mutable en '{node.name}'",
                sugerencia="Usar None como default y crear la mutable dentro de la función",
                archivo="",
                linea=node.lineno,
                funcion=node.name,
            ))
    for default in node.args.kw_defaults:
        if default and isinstance(default, (ast.List, ast.Dict, ast.Set)):
            bugs.append(BugPredicho(
                tipo="mutable_default",
                severidad="warning",
                mensaje=f"Keyword argument default mutable en '{node.name}'",
                sugerencia="Usar None como default y crear la mutable dentro de la función",
                archivo="",
                linea=node.lineno,
                funcion=node.name,
            ))
    return bugs


def _check_bare_except(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta except sin tipo específico (except: pass)."""
    bugs = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Try):
            continue
        for handler in child.handlers:
            if handler.type is None:
                bugs.append(BugPredicho(
                    tipo="bare_except",
                    severidad="warning",
                    mensaje="Except sin tipo captura SystemExit y KeyboardInterrupt",
                    sugerencia="Usar 'except Exception:' o un tipo específico",
                    archivo="",
                    linea=handler.lineno,
                    funcion=node.name,
                ))
            elif isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
                # Verificar si tiene re-raise
                has_reraise = any(
                    isinstance(n, ast.Raise) and n.exc is None
                    for n in ast.walk(ast.Module(body=handler.body, type_ignores=[]))
                )
                if not has_reraise:
                    bugs.append(BugPredicho(
                        tipo="broad_except",
                        severidad="info",
                        mensaje="Captura 'Exception' demasiado general",
                        sugerencia="Capturar un tipo más específico de excepción",
                        archivo="",
                        linea=handler.lineno,
                        funcion=node.name,
                    ))
    return bugs


def _check_resource_leaks(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta open() sin context manager (with statement)."""
    bugs = []

    class LeakVisitor(ast.NodeVisitor):
        def __init__(self):
            self.in_with_depth = 0

        def visit_With(self, w: ast.With) -> None:
            self.in_with_depth += 1
            self.generic_visit(w)
            self.in_with_depth -= 1

        def visit_Call(self, c: ast.Call) -> None:
            if self.in_with_depth == 0 and _is_open_call(c):
                bugs.append(BugPredicho(
                    tipo="resource_leak",
                    severidad="warning",
                    mensaje="open() sin context manager — risk de resource leak",
                    sugerencia="Usar: with open(...) as f:",
                    archivo="",
                    linea=c.lineno,
                    funcion=node.name,
                ))
            self.generic_visit(c)

    LeakVisitor().visit(node)
    return bugs


def _check_unused_variables(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta variables asignadas pero nunca usadas."""
    defined: dict[str, ast.Name] = {}
    used: set[str] = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            if isinstance(child.ctx, ast.Load):
                used.add(child.id)
            elif isinstance(child.ctx, ast.Store):
                if child.id not in defined:
                    defined[child.id] = child

    bugs = []
    for name, name_node in defined.items():
        if name not in used and not name.startswith("_"):
            bugs.append(BugPredicho(
                tipo="unused_variable",
                severidad="info",
                mensaje=f"Variable '{name}' asignada pero nunca usada",
                sugerencia=f"Eliminar '{name}' o prefijar con _ si es intencional",
                archivo="",
                linea=name_node.lineno,
                funcion=node.name,
            ))
    return bugs


def _check_redefined_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta argumentos redefinidos en loops."""
    arg_names = {arg.arg for arg in node.args.args + node.args.kwonlyargs}
    bugs = []

    for child in ast.walk(node):
        if isinstance(child, ast.For) and isinstance(child.target, ast.Name):
            if child.target.id in arg_names:
                bugs.append(BugPredicho(
                    tipo="redefined_arg",
                    severidad="warning",
                    mensaje=f"Argumento '{child.target.id}' redefinido en loop",
                    sugerencia=f"Usar un nombre diferente para la variable del loop",
                    archivo="",
                    linea=child.lineno,
                    funcion=node.name,
                ))
    return bugs


def _is_open_call(call: ast.Call) -> bool:
    """Verifica si un Call es open() o io.open()."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "open":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "open":
        if isinstance(func.value, ast.Name) and func.value.id in ("io", "_io"):
            return True
    return False


# ── Dispatcher principal ──


def predecir_bugs(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Ejecuta todos los checks de predicción de bugs en una función.

    Returns:
        Lista de bugs potenciales detectados
    """
    bugs = []
    bugs.extend(_check_mutable_defaults(node))
    bugs.extend(_check_bare_except(node))
    bugs.extend(_check_resource_leaks(node))
    bugs.extend(_check_unused_variables(node))
    bugs.extend(_check_redefined_args(node))
    return bugs


def predecir_bugs_archivo(archivo_path: str) -> list[BugPredicho]:
    """Analiza un archivo completo y retorna todos los bugs potenciales."""
    import ast as ast_module

    try:
        with open(archivo_path, "r", encoding="utf-8") as f:
            contenido = f.read()
        tree = ast_module.parse(contenido)
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
        return []

    bugs = []
    for node in ast_module.walk(tree):
        if isinstance(node, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)):
            func_bugs = predecir_bugs(node)
            for b in func_bugs:
                b.archivo = archivo_path
            bugs.extend(func_bugs)

    return bugs


def escanear_proyecto(raiz: str) -> dict:
    """Escanea un proyecto completo buscando bugs potenciales."""
    from pathlib import Path

    bugs_totales = []
    archivos_escaneados = 0
    por_tipo = {}
    por_severidad = {"error": 0, "warning": 0, "info": 0}

    for archivo in Path(raiz).rglob("*.py"):
        if any(p.startswith(".") or p in ("__pycache__", "venv", ".venv", "node_modules", "tests")
               for p in archivo.parts):
            continue
        if archivo.name.startswith("test_") or archivo.name == "conftest.py":
            continue

        bugs = predecir_bugs_archivo(str(archivo))
        bugs_totales.extend(bugs)
        archivos_escaneados += 1

    for b in bugs_totales:
        por_tipo.setdefault(b.tipo, []).append(b)
        por_severidad[b.severidad] += 1

    return {
        "archivos_escaneados": archivos_escaneados,
        "total_bugs": len(bugs_totales),
        "por_severidad": por_severidad,
        "por_tipo": {k: len(v) for k, v in por_tipo.items()},
        "bugs": [
            {
                "tipo": b.tipo,
                "severidad": b.severidad,
                "mensaje": b.mensaje,
                "sugerencia": b.sugerencia,
                "archivo": b.archivo,
                "linea": b.linea,
                "funcion": b.funcion,
            }
            for b in bugs_totales[:50]  # Top 50
        ],
    }

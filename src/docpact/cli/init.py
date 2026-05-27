"""docpact init — Genera esqueletos de CONTRATO para funciones sin contrato.

Analiza la firma y el cuerpo de la función, detecta inputs, output y
side effects usando el AST walker, y genera un bloque CONTRATO listo
para insertar en el docstring.

Uso:
  docpact init archivo.py --function mi_funcion    # función específica
  docpact init archivo.py --batch                   # todas las funciones
  docpact init directorio/ --batch                  # todo un directorio
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from docpact.checker.side_effects import _extraer_llamadas, _clasificar_llamadas
from docpact.config import DocpactConfig
from docpact.parser.extractor import extraer_docstrings
from docpact.parser.lexer import tokenizar
from docpact.parser.parser import parsear


def generar_contrato(
    archivo: str | Path,
    nombre_funcion: str,
) -> str | None:
    """Genera un bloque CONTRATO para una función específica.

    Args:
        archivo: Ruta al archivo .py.
        nombre_funcion: Nombre de la función.

    Returns:
        El texto del bloque CONTRATO, o None si la función no existe
        o ya tiene CONTRATO.
    """
    path = Path(archivo)
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        fuente = f.read()
    tree = ast.parse(fuente, filename=str(path))

    # Buscar la función
    nodo = _buscar_funcion(tree, nombre_funcion)
    if nodo is None:
        return None

    # Verificar si ya tiene CONTRATO
    doc = ast.get_docstring(nodo, clean=False) or ""
    if tokenizar(doc):
        return None  # Ya tiene CONTRATO

    return _generar_bloque(nodo, nombre_funcion, fuente, path)


def _buscar_funcion(
    tree: ast.AST,
    nombre: str,
) -> Optional[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Busca una función por nombre en el AST."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == nombre:
                return node
        if isinstance(node, ast.ClassDef):
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == nombre:
                        return item
    return None


def _es_trivial(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """True si la función es trivial: sin params, sin retorno declarado,
    sin llamadas a side effects. Getters, setters, delegates simples."""
    params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
    if params:
        return False
    if node.returns:
        return False
    # Solo statements simples: return, assign, expr, pass
    for stmt in node.body:
        if isinstance(stmt, ast.Expr):
            continue  # docstring
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Return):
            if stmt.value is not None and not isinstance(stmt.value, (ast.Constant, ast.Attribute, ast.Name)):
                return False  # return con expresión compleja
            continue
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Attribute):
                continue  # self.x = y (setter simple)
            return False
        return False  # cualquier otro statement
    return True


def _generar_bloque(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    nombre: str,
    fuente: str,
    path: Path,
) -> str:
    """Genera el texto del bloque CONTRATO para una función.

    Produce CONTRATO completo (input, output, side_effects, rn, dependencias)
    o minimal (solo side_effects + rn) para funciones triviales."""
    config = DocpactConfig()
    lines: list[str] = []
    lines.append("    CONTRATO:")

    # Trivial: solo side_effects + rn, sin input/output
    if _es_trivial(node):
        lines.append("    side_effects: ninguno")
        lines.append('    rn: []')
        return "\n".join(lines)

    # Input: parámetros con sus type hints
    params = [a.arg for a in node.args.args if a.arg != "self"]
    if params:
        lines.append("    input:")
        for param in params:
            annotation = _type_hint_str(node, param)
            lines.append(f"      {param}: {annotation} — Descripción")
    else:
        lines.append("    input:")

    # Output: type hint del retorno
    return_hint = _return_hint_str(node)
    if return_hint:
        lines.append(f"    output: {return_hint} — Descripción del retorno")
    else:
        lines.append("    output:")

    # Side effects: detectar del AST walker
    llamadas = _extraer_llamadas(node)
    efectos = _clasificar_llamadas(llamadas, config)
    if efectos:
        line = ", ".join(efectos)
        lines.append(f"    side_effects: {line}")
    else:
        lines.append("    side_effects: ninguno")

    # RN: vacío (el agente debe completar con la RN correcta)
    lines.append('    rn: []  # completar con RN-XXX de docs/reglas-del-negocio/')

    # Dependencias: detectar imports locales del módulo
    deps = _detectar_dependencias(fuente, path)
    if deps:
        lines.append("    dependencias:")
        for d in deps:
            lines.append(f"      - {d}")

    return "\n".join(lines)


def _type_hint_str(node: ast.FunctionDef | ast.AsyncFunctionDef, param: str) -> str:
    """Obtiene el type hint de un parámetro como string."""
    for arg in node.args.args:
        if arg.arg == param and arg.annotation:
            return ast.unparse(arg.annotation)
    return ""


def _return_hint_str(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Obtiene el type hint de retorno como string."""
    if node.returns:
        return ast.unparse(node.returns)
    return ""


def _detectar_dependencias(fuente: str, path: Path) -> list[str]:
    """Detecta dependencias a módulos locales del proyecto.

    Busca imports relativos o de módulos del mismo proyecto.
    Retorna rutas relativas al proyecto, sin prefijo del directorio del proyecto.
    """
    tree = ast.parse(fuente)
    deps: list[str] = []
    project_root = _find_project_root(path)

    if not project_root:
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level and node.level > 0:
                # Import relativo: from .models import Ticket
                current = path.parent
                for _ in range(node.level - 1):
                    current = current.parent
                # Convertir a ruta relativa al proyecto
                try:
                    rel = current.relative_to(project_root)
                    module_rel = module.replace(".", "/")
                    names = [a.name for a in node.names if not a.name.startswith("_")]
                    if names:
                        deps.append(f"{rel}/{module_rel}.py::{names[0]}")
                except ValueError:
                    pass
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.replace(".", "/")
                module_path = project_root / name
                if module_path.exists() or (project_root / f"{name}.py").exists():
                    deps.append(f"{name}.py")

    return deps[:5]  # Máximo 5 dependencias


def _find_project_root(path: Path) -> Optional[Path]:
    """Encuentra la raíz del proyecto (directorio con .git o pyproject.toml)."""
    for parent in [path] + list(path.parents):
        if (parent / ".git").exists() or (parent / ".git").is_dir():
            return parent
        if (parent / "pyproject.toml").exists():
            return parent
    return None


def _insertar_contrato_en_docstring(
    fuente: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    nombre: str,
    bloque: str,
) -> tuple[bool, str]:
    """Inserta el bloque CONTRATO en el docstring de la función.

    Si no hay docstring: crea uno nuevo.
    Si hay docstring: inserta el CONTRATO antes del cierre (soporta multi-linea).

    Returns:
        (exito, fuente_modificada_o_mensaje)
    """
    lineas = fuente.split("\n")

    # Detectar si ya hay docstring (solo el primer statement del cuerpo)
    doc_expr = None
    if node.body and isinstance(node.body[0], ast.Expr):
        val = node.body[0].value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            doc_expr = (node.body[0], val)
        elif isinstance(val, ast.Str):
            doc_expr = (node.body[0], val)

    # Calcular indentación correcta basada en la posición del nodo
    base_indent = node.col_offset if node.col_offset is not None else 0
    indent = " " * (base_indent + 4)  # +4 para el cuerpo de la función

    if doc_expr:
        expr_node, _ = doc_expr
        start = expr_node.lineno  # 1-based
        end = expr_node.end_lineno or start  # 1-based

        # Si es docstring de una línea: convertir a multi-línea
        if start == end:
            idx = start - 1  # 0-based
            line = lineas[idx]
            # Extraer el contenido entre """..."""
            if '"""' in line:
                parts = line.split('"""', 2)
                if len(parts) >= 3:
                    content = parts[1]
                    # Reemplazar línea por versión multi-línea
                    lineas[idx] = parts[0] + '"""' + content
                    lineas.insert(idx + 1, '"""')
                    end = start + 1

        # El bloque CONTRATO va antes del cierre """ (última línea)
        insert_idx = end - 1  # 0-based

        # Formatear bloque con indentación correcta
        bloque_indentado = []
        for bloque_linea in bloque.split("\n"):
            bloque_indentado.append(indent + bloque_linea)

        lineas[insert_idx:insert_idx] = bloque_indentado
    else:
        # No hay docstring — crear uno completo
        doc_lines = [
            f'{indent}"""{nombre} — Descripción.',
            "",
        ]
        for bloque_linea in bloque.split("\n"):
            doc_lines.append(indent + bloque_linea)
        doc_lines.append(f'{indent}"""')

        # Insertar después de la firma de la función (antes del body)
        # Para funciones de una línea (def foo(): return x), hay que dividir la línea
        if node.body[0].lineno == node.lineno:
            # One-liner: separar def del body en dos líneas
            def_line = lineas[node.lineno - 1]
            # Extraer signature (todo hasta ":") y body (después de "return ")
            sig, _, body_part = def_line.partition(": ")
            lineas[node.lineno - 1] = sig + ":"
            # Insertar el body después del docstring
            body_indent = indent  # misma indent que el docstring
            doc_lines.append(f'{body_indent}{body_part}')
        insert_line = node.lineno  # después de la línea def (0-based)
        doc_lines.reverse()
        for dl in doc_lines:
            lineas.insert(insert_line, dl)

    return True, "\n".join(lineas)


def init_function(
    archivo: str | Path,
    nombre_funcion: str,
    safe: bool = True,
) -> tuple[bool, str]:
    """Genera e inserta un CONTRATO para una función específica.

    Args:
        archivo: Ruta al archivo .py.
        nombre_funcion: Nombre de la función.

    Returns:
        (exito, mensaje)
    """
    path = Path(archivo)
    if not path.exists():
        return False, f"Archivo no encontrado: {archivo}"

    with open(path, "r", encoding="utf-8") as f:
        fuente = f.read()

    tree = ast.parse(fuente, filename=str(path))
    nodo = _buscar_funcion(tree, nombre_funcion)

    if nodo is None:
        return False, f"Función '{nombre_funcion}' no encontrada en {archivo}"

    # Verificar si ya tiene CONTRATO
    doc = ast.get_docstring(nodo, clean=False) or ""
    if tokenizar(doc):
        return False, f"'{nombre_funcion}' ya tiene CONTRATO"

    # Modo safe: saltar funciones con docstring existente (sin CONTRATO)
    if safe and doc.strip():
        return False, f"'{nombre_funcion}' tiene docstring existente sin CONTRATO (usá --force para agregar)"

    bloque = _generar_bloque(nodo, nombre_funcion, fuente, path)
    exito, nueva_fuente = _insertar_contrato_en_docstring(fuente, nodo, nombre_funcion, bloque)
    if not exito:
        return False, f"'{nombre_funcion}': {nueva_fuente}"

    with open(path, "w", encoding="utf-8") as f:
        f.write(nueva_fuente)

    return True, f"CONTRATO generado para '{nombre_funcion}' en {archivo}"


def _listar_funciones_publicas(path: Path) -> list[str]:
    """Lista todas las funciones públicas (sin prefijo _) de un archivo.

    Incluye funciones sin docstring, que extraer_docstrings omite.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(path))
    except (SyntaxError, FileNotFoundError):
        return []

    funciones: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                funciones.append(node.name)
        elif isinstance(node, ast.ClassDef):
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not item.name.startswith("_"):
                        funciones.append(item.name)
    return funciones


def init_batch(
    path: str | Path,
    safe: bool = True,
) -> list[tuple[str, bool, str]]:
    """Genera CONTRATOS para todas las funciones públicas sin CONTRATO.

    Args:
        path: Ruta al archivo o directorio.

    Returns:
        Lista de (nombre_funcion, exito, mensaje)
    """
    ruta = Path(path)
    archivos = sorted(ruta.rglob("*.py")) if ruta.is_dir() else [ruta]

    resultados: list[tuple[str, bool, str]] = []
    for archivo in archivos:
        if _es_excluido(archivo):
            continue

        funciones = _listar_funciones_publicas(archivo)
        for nombre in funciones:
            exito, msg = init_function(archivo, nombre, safe=safe)
            resultados.append((nombre, exito, msg))

    return resultados


def _es_excluido(path: Path) -> bool:
    excluidos = {
        "__pycache__", ".venv", "venv", "node_modules",
        ".git", "migrations", ".pytest_cache",
    }
    for parte in path.parts:
        if parte in excluidos:
            return True
    return False
"""docpact fix — Auto-corrige warnings de firma en CONTRATOS.

Corrige automáticamente:
1. self:/cls: en CONTRATO input (no son parámetros reales)
2. *args, **kwargs: combinados → args:/kwargs: separados
3. args/kwargs faltantes en CONTRATO (los agrega si existen en la firma)
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from docpact.parser.extractor import extraer_docstrings
from docpact.parser.lexer import tokenizar
from docpact.parser.parser import parsear


def fix_file(archivo: str | Path) -> int:
    """Corrige automáticamente warnings de firma en un archivo.

    Returns:
        Cantidad de archivos modificados (0 o 1).
    """
    path = Path(archivo)
    if path.suffix in (".ts", ".tsx", ".jsx"):
        return 0

    with open(path, "r", encoding="utf-8") as f:
        fuente = f.read()

    try:
        tree = ast.parse(fuente, filename=str(path))
    except (SyntaxError, FileNotFoundError):
        return 0

    doc_funciones = extraer_docstrings(path)
    doc_map: dict[str, tuple[int, str, str]] = {
        f"{nombre}:{linea}": (linea, tipo, doc)
        for linea, nombre, tipo, doc in doc_funciones
    }

    cambios = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        nombre = node.name
        info = doc_map.get(f"{nombre}:{node.lineno}")
        if not info:
            continue

        _, _, doc = info

        # Obtener parámetros reales
        params_reales: set[str] = set()
        for arg in node.args.args:
            if arg.arg not in ("self", "cls"):
                params_reales.add(arg.arg)
        for arg in node.args.kwonlyargs:
            if arg.arg not in ("self", "cls"):
                params_reales.add(arg.arg)
        kwarg_name = node.args.kwarg.arg if node.args.kwarg else None
        vararg_name = node.args.vararg.arg if node.args.vararg else None
        if vararg_name:
            params_reales.add(vararg_name)
        if kwarg_name:
            params_reales.add(kwarg_name)

        tokens = tokenizar(doc)
        contrato, _ = parsear(tokens)
        if not contrato.input:
            continue

        params_contrato = set(contrato.input.keys())

        lineas = fuente.split("\n")

        # Buscar el bloque CONTRATO con regex — más confiable que tokens
        # porque los tokens no nos dan las líneas exactas para modificar
        _fix_contrato_en_fuente(lineas, node, doc, params_reales, params_contrato,
                                kwarg_name=kwarg_name)

        nueva = "\n".join(lineas)
        if nueva != fuente:
            with open(path, "w", encoding="utf-8") as f:
                f.write(nueva)
            fuente = nueva  # actualizar para la próxima iteración
            cambios += 1

    return cambios


def _fix_contrato_en_fuente(
    lineas: list[str],
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    doc: str,
    params_reales: set[str],
    params_contrato: set[str],
    kwarg_name: Optional[str] = None,
) -> None:
    """Modifica las líneas del docstring para corregir warnings de firma.

    Opera in-place sobre lineas[]. Busca el bloque CONTRATO
    dentro del docstring de node y aplica:
    1. Elimina líneas self:/cls:
    2. Divide *args, **kwargs: en args:/kwargs:
    3. Agrega args:/kwargs: si faltan y existen en la firma
    """
    # Calcular rango del docstring en lineas (1-based)
    doc_lines = doc.split("\n")
    # El docstring empieza en node.lineno (primera línea del def)
    start = node.lineno  # 1-based
    end = getattr(node, "end_lineno", None) or (start + len(doc_lines))

    # El docstring está dentro de las líneas del cuerpo.
    # Buscar "CONTRATO:" en la región endoscópica
    contrato_line = None
    input_line = None
    input_end = None
    for i in range(end - 1, start - 2, -1):
        if i < 0 or i >= len(lineas):
            continue
        stripped = lineas[i].strip()
        if stripped == "input:":
            input_line = i
        if stripped.startswith("CONTRATO:") and contrato_line is None:
            contrato_line = i

    if contrato_line is None or input_line is None:
        return

    # Encontrar el final del bloque input (siguiente sección o fin de docstring)
    input_end = None
    for i in range(input_line + 1, min(end, len(lineas))):
        stripped = lineas[i].strip()
        if stripped in ("output:", "side_effects:", "rn:", "borde:", "dependencias:"):
            input_end = i
            break
    if input_end is None:
        input_end = min(end, len(lineas))

    # Modificar líneas dentro del bloque input
    lineas_input = lineas[input_line:input_end]
    nuevas_input = []
    tiene_args = any(re.match(r"^\s*args\s*:", l) for l in lineas_input)
    tiene_kwargs = any(re.match(r"^\s*kwargs\s*:", l) for l in lineas_input)

    for line in lineas_input:
        stripped = line.strip()

        # Eliminar self:/cls:
        if re.match(r"^\s*self:", stripped) or re.match(r"^\s*cls:", stripped):
            continue

        # Dividir *args, **kwargs: combinados
        if re.match(r"^\s*\*args,\s*\*\*kwargs\s*:", stripped):
            indent = line[: len(line) - len(line.lstrip())]
            desc_match = re.search(r":\s*(.*)", stripped)
            desc = desc_match.group(1).strip() if desc_match else ""
            tipo_a, desc_a = ("tuple", desc) if "—" not in desc else desc.split("—", 1)
            nuevas_input.append(f"{indent}args: tuple — {desc_a.strip()}")
            nuevas_input.append(f"{indent}kwargs: dict — {desc_a.strip()}")
            tiene_args = True
            tiene_kwargs = True
            continue

        nuevas_input.append(line)

    # Agregar args:/kwargs: faltantes al final del bloque input
    needs_args = "args" in params_reales and not tiene_args
    needs_kwargs = "kwargs" in params_reales and not tiene_kwargs
    if needs_args or needs_kwargs:
        # Determinar indentación de la última línea del input
        ultima = lineas_input[-1] if lineas_input else "  "
        indent = ultima[: len(ultima) - len(ultima.lstrip())]
        if not indent:
            indent = "      "
        # Insertar antes del cierre (última línea de input)
        if needs_args:
            nuevas_input.insert(-1 if len(nuevas_input) > 1 else len(nuevas_input),
                                f"{indent}args: tuple — Argumentos posicionales adicionales")
        if needs_kwargs:
            nuevas_input.insert(-1 if len(nuevas_input) > 1 else len(nuevas_input),
                                f"{indent}kwargs: dict — Argumentos de palabra clave adicionales")

    lineas[input_line:input_end] = nuevas_input

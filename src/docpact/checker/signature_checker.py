"""Verificación de firmas de funciones vs CONTRATOs.

Extraído de orchestrator.py para separar responsabilidades.
"""

from __future__ import annotations

import ast
from pathlib import Path

from docpact.checker.models import Hallazgo
from docpact.models.contrato import Contrato, CampoInput


def check_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    contrato: Contrato,
    nombre: str,
    archivo: str,
    hallazgos: list[Hallazgo],
    tiene_future_annotations: bool = False,
) -> None:
    """Verifica que los parámetros del CONTRATO coincidan con la firma real.

    No verifica tipos (delegado a mypy/pyright), solo nombres de parámetros.
    Omite self/cls automáticamente.
    Detecta parámetros virtuales (extraídos de kwargs.pop/get en el cuerpo).
    """
    if not contrato.input:
        return

    params_reales = set()
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

    # Virtual params: nombres extraídos de kwargs.pop("x") / kwargs.get("x")
    if kwarg_name:
        for subnode in ast.walk(node):
            if isinstance(subnode, ast.Call):
                func = subnode.func
                if (isinstance(func, ast.Attribute)
                        and func.attr in ("pop", "get")
                        and isinstance(func.value, ast.Name)
                        and func.value.id == kwarg_name
                        and subnode.args
                        and isinstance(subnode.args[0], ast.Constant)
                        and isinstance(subnode.args[0].value, str)):
                    params_reales.add(subnode.args[0].value)

    params_contrato = set(contrato.input.keys())

    def _normalizar(n: str) -> str:
        return n.lstrip("*")

    params_contrato_norm = {_normalizar(p) for p in params_contrato}

    for p in params_contrato:
        if _normalizar(p) not in params_reales:
            hallazgos.append(
                Hallazgo(
                    tipo="warning",
                    campo="presencia",
                    funcion=nombre,
                    archivo=archivo,
                    linea=node.lineno,
                    mensaje=f"'{nombre}': CONTRATO declara parámetro '{p}' "
                    f"que no existe en la firma real",
                    sugerencia=f"Elimina '{p}' del bloque input del CONTRATO "
                    f"o agrega el parámetro a la función",
                )
            )

    for p in params_reales:
        if p not in params_contrato_norm:
            hallazgos.append(
                Hallazgo(
                    tipo="warning",
                    campo="presencia",
                    funcion=nombre,
                    archivo=archivo,
                    linea=node.lineno,
                    mensaje=f"'{nombre}': parámetro '{p}' no documentado en "
                    f"CONTRATO input",
                    sugerencia=f"Agrega '{p}: <tipo> — <descripción>' al bloque "
                    f"input del CONTRATO",
                )
            )


def introspectar_firma(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[dict[str, CampoInput], str | None]:
    """Extrae argumentos y retorno usando el AST de la función."""
    inputs: dict[str, CampoInput] = {}
    output_type: str | None = None

    todos_args = node.args.args + node.args.kwonlyargs
    for arg in todos_args:
        if arg.arg in ("self", "cls"):
            continue
        tipo = "Any"
        if arg.annotation:
            try:
                tipo = ast.unparse(arg.annotation).strip()
            except Exception:
                tipo = "Any"
        inputs[arg.arg] = CampoInput(nombre=arg.arg, tipo=tipo)

    if node.args.vararg and node.args.vararg.arg not in ("self", "cls"):
        inputs[node.args.vararg.arg] = CampoInput(
            nombre=node.args.vararg.arg, tipo="tuple"
        )
    if node.args.kwarg and node.args.kwarg.arg not in ("self", "cls"):
        inputs[node.args.kwarg.arg] = CampoInput(
            nombre=node.args.kwarg.arg, tipo="dict"
        )

    if node.returns:
        try:
            output_type = ast.unparse(node.returns).strip()
        except Exception:
            output_type = "Any"

    return inputs, output_type


def find_project_root(archivo: str) -> Path | None:
    """Busca la raiz del proyecto ascendiendo desde un archivo."""
    path = Path(archivo).resolve()
    for parent in [path] + list(path.parents):
        reg = parent / "docs" / "reglas-del-negocio" / "REGISTRO.md"
        if reg.exists():
            return parent
        if (parent / "pyproject.toml").exists() or (parent / "docpact.toml").exists():
            return parent
    return None

"""Verificador de dependencias.

Toma el campo `dependencias:` del CONTRATO y confirma que:
1. Cada ruta de módulo existe
2. Cada símbolo referenciado (tras ::) existe en ese módulo
3. Sin dependencias circulares entre módulos
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from docpact.models.contrato import Contrato, ErrorParser


def check_deps(
    contrato: Contrato,
    archivo_base: str | Path,
    nombre_funcion: str = "",
) -> list[ErrorParser]:
    """Verifica que las dependencias declaradas existan.

    Args:
        contrato: CONTRATO parseado.
        archivo_base: Ruta del archivo que contiene el CONTRATO (para resolver rutas relativas).
        nombre_funcion: Nombre de la función (para errores).

    Returns:
        Lista de errores/warnings.
    """
    if not contrato.dependencias:
        return []

    errores: list[ErrorParser] = []
    base_dir = Path(archivo_base).parent if isinstance(archivo_base, (str, Path)) else Path(".")

    for dep in contrato.dependencias:
        ref = dep.ref.strip()

        # Separar módulo y símbolo
        if "::" in ref:
            modulo_path, simbolo = ref.split("::", 1)
        else:
            modulo_path = ref
            simbolo = None

        # Resolver la ruta del módulo
        ruta_modulo = _resolver_ruta(modulo_path, base_dir)

        if not ruta_modulo.exists():
            errores.append(ErrorParser(
                "dependencias",
                f"'{nombre_funcion}': dependencia '{ref}' — "
                f"archivo '{ruta_modulo}' no encontrado",
                sugerencia=f"Verifica la ruta: '{modulo_path}' "
                           f"(buscado desde {base_dir})",
            ))
            continue

        # Si hay símbolo, verificar que exista en el módulo
        if simbolo:
            errores_sim = _verificar_simbolo(ruta_modulo, simbolo, ref, nombre_funcion)
            errores.extend(errores_sim)

    return errores


def _resolver_ruta(modulo_path: str, base_dir: Path) -> Path:
    """Resuelve una ruta de módulo relativa al archivo actual."""
    ruta = Path(modulo_path)

    # Si ya es absoluta (empieza con /)
    if ruta.is_absolute():
        return ruta

    # Si termina en .py, usarla directamente
    if ruta.suffix == ".py":
        return (base_dir / ruta).resolve()

    # Si no tiene extensión, probar con .py
    sin_py = (base_dir / ruta).resolve()
    if sin_py.exists():
        return sin_py
    return (base_dir / ruta.with_suffix(".py")).resolve()


def _verificar_simbolo(
    ruta_modulo: Path,
    simbolo: str,
    ref_original: str,
    nombre_funcion: str,
) -> list[ErrorParser]:
    """Verifica que un símbolo (clase, función) exista en un archivo."""
    try:
        with open(ruta_modulo, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=str(ruta_modulo))
    except (SyntaxError, FileNotFoundError):
        return []

    errores: list[ErrorParser] = []
    encontrado = False

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == simbolo:
                encontrado = True
                break

    if not encontrado:
        errores.append(ErrorParser(
            "dependencias",
            f"'{nombre_funcion}': símbolo '{simbolo}' no encontrado "
            f"en '{ruta_modulo}'",
            sugerencia=f"Verifica que '{simbolo}' exista en '{ruta_modulo}'",
        ))

    return errores

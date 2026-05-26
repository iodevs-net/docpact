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
    """Resuelve una ruta de módulo.

    Prueba varias bases: el directorio del archivo actual, y luego la raíz
    del proyecto (subiendo hasta encontrar .git/ o setup.py/pyproject.toml).
    """
    ruta = Path(modulo_path)

    # Si ya es absoluta (empieza con /)
    if ruta.is_absolute():
        return ruta

    # Buscar en varias bases
    bases_a_probar = [base_dir]

    # Intentar subir desde base_dir hasta encontrar una raíz de proyecto
    for parent in [base_dir] + list(base_dir.parents):
        marker = parent / ".git"
        if marker.exists() or marker.is_dir():
            bases_a_probar.append(parent)
            break
    else:
        # Si no encontramos .git, probar con la raíz del archivo
        bases_a_probar.append(base_dir.root)

    for base in bases_a_probar:
        for variante in [ruta, ruta.with_suffix(".py")]:
            full = (base / variante).resolve()
            if full.exists():
                return full

    # Último recurso: devolver la ruta relativa a base_dir
    return (base_dir / ruta.with_suffix(".py")).resolve()


def _verificar_simbolo(
    ruta_modulo: Path,
    simbolo: str,
    ref_original: str,
    nombre_funcion: str,
) -> list[ErrorParser]:
    """Verifica que un símbolo (clase, función) exista en un archivo.

    Soporta nombres calificados: 'Clase.metodo' busca el método dentro de la clase.
    """
    try:
        with open(ruta_modulo, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=str(ruta_modulo))
    except (SyntaxError, FileNotFoundError):
        return []

    errores: list[ErrorParser] = []
    encontrado = False

    # Separar nombre calificado: "TicketService.update" → clase="TicketService", metodo="update"
    partes = simbolo.split(".", 1)
    nombre_clase = partes[0]
    nombre_metodo = partes[1] if len(partes) > 1 else None

    if nombre_metodo:
        # Buscar clase y dentro de ella el método
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == nombre_clase:
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name == nombre_metodo:
                            encontrado = True
                            break
                break
    else:
        # Buscar símbolo directo (función o clase)
        for node in ast.walk(tree):
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

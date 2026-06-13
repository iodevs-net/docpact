"""Utilidades de archivos para el orquestador.

Funciones de escaneo y detección de cambios git.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from docpact.config import DocpactConfig


def get_changed_files(ruta_base: Path) -> list[Path]:
    """Obtiene archivos modificados via git diff.

    Orden: staged first (pre-commit), luego unstaged (local dev).
    Retorna vacía si no hay cambios o no es repo git.

    Returns:
        Lista de Paths absolutos de archivos modificados.
    """
    import subprocess

    try:
        # Staged changes (pre-commit hook context)
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=ruta_base,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [ruta_base / p for p in result.stdout.strip().splitlines()]
        # Unstaged changes (local dev context)
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=ruta_base,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [ruta_base / p for p in result.stdout.strip().splitlines()]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return []


def escanear_eficiente(
    ruta: Path,
    config: DocpactConfig,
    extensiones: tuple[str, ...],
) -> list[Path]:
    """Escanea un directorio recursivamente, excluyendo paths según config.

    Usa os.walk para eficiencia, filtrando dirs in-place para evitar
    descend into directorios excluidos.

    Args:
        ruta: Directorio raíz a escanear.
        config: Configuración con reglas de exclusión.
        extensiones: Extensiones de archivo a incluir (ej: (".py", ".ts")).

    Returns:
        Lista de Paths absolutos de archivos encontrados.
    """
    import os

    archivos: list[Path] = []

    ruta_res = ruta.resolve()
    # Comprobar la carpeta raíz de forma relativa
    if config.debe_excluir(Path(ruta_res.name)):
        return archivos

    ruta_str = str(ruta_res)
    for root, dirs, files in os.walk(ruta_str):
        root_path = Path(root).resolve()
        try:
            rel_root = root_path.relative_to(ruta_res)
        except ValueError:
            rel_root = Path("")

        # Modificar dirs in-place usando rutas relativas
        dirs_to_keep = []
        for d in dirs:
            rel_dir_path = rel_root / d
            if not config.debe_excluir(rel_dir_path):
                dirs_to_keep.append(d)
        dirs[:] = dirs_to_keep

        for f in files:
            file_path = root_path / f
            rel_file_path = rel_root / f
            if file_path.suffix in extensiones:
                if not config.debe_excluir(rel_file_path):
                    archivos.append(file_path)
    return archivos

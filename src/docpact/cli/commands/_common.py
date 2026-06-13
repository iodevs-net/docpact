"""Shared helpers for docpact CLI commands."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("docpact.cli")


def _es_excluido(path: Path) -> bool:
    """Verifica si un path debe ser excluido."""
    excluidos = {
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".git",
        "migrations",
        ".pytest_cache",
    }
    for parte in path.parts:
        if parte in excluidos:
            return True
    return False


def _print_contrato_texto(r: dict) -> None:
    """Imprime un CONTRATO en formato texto legible."""
    loc = f"{r['archivo']}::{r['funcion']}:{r['linea']}"
    print(f"── {loc}")
    c = r["contrato"]
    if c["input"]:
        print(f"  input: {len(c['input'])} parámetros")
    if c["output"]:
        desc = f" — {c['output_descripcion']}" if c["output_descripcion"] else ""
        print(f"  output: {c['output']}{desc}")
    se = c["side_effects"]
    print(f"  side_effects: {', '.join(se) if se else 'ninguno'}")
    if c["rn"]:
        rn_ids = [r.get("id", "") for r in c["rn"]]
        print(f"  rn: {', '.join(rn_ids)}")
        _cargadas = set()
        try:
            from docpact.checker.rn_registry import cargar_registro

            _path = Path(r["archivo"]).resolve()
            _root = None
            for _p in [_path] + list(_path.parents):
                if (_p / "docs" / "reglas-del-negocio" / "REGISTRO.md").exists():
                    _root = _p
                    break
            if _root:
                _reg = cargar_registro(_root)
                for rn_id in rn_ids:
                    if rn_id in _reg and rn_id not in _cargadas:
                        print(f"     📋 {rn_id}: {_reg[rn_id]}")
                        _cargadas.add(rn_id)
        except Exception:
            pass
    if c.get("errores"):
        for e in c["errores"]:
            msg = f"  ⚠️  [{e['campo']}] {e['mensaje']}"
            if e.get("sugerencia"):
                msg += f"\n     💡 {e['sugerencia']}"
            print(msg)
    print()


# ── Argument helpers (DRY registrars) ──


def add_path_arg(parser: argparse.ArgumentParser, help_text: str = "Archivo o directorio a analizar") -> None:
    """Agrega argumento positional 'path'."""
    parser.add_argument("path", type=str, help=help_text)


def add_project_root_arg(parser: argparse.ArgumentParser, required: bool = True, default: str | None = None) -> None:
    """Agrega argumento --project-root."""
    parser.add_argument(
        "--project-root",
        type=str,
        default=default,
        required=required,
        help="Raíz del proyecto (default: directorio actual)",
    )


def add_json_flag(parser: argparse.ArgumentParser) -> None:
    """Agrega flag --json para output estructurado."""
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output estructurado en JSON",
    )


def add_strict_flag(parser: argparse.ArgumentParser) -> None:
    """Agrega flag --strict."""
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Falla si hay funciones públicas sin CONTRATO",
    )


def add_config_arg(parser: argparse.ArgumentParser) -> None:
    """Agrega argumento --config para docpact.toml."""
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Ruta al archivo de configuración docpact.toml",
    )


def add_diff_flag(parser: argparse.ArgumentParser) -> None:
    """Agrega flag --diff para verificación diferencial."""
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Solo verificar archivos modificados vs HEAD (git diff)",
    )


def add_fix_flag(parser: argparse.ArgumentParser, help_text: str = "Auto-genera CONTRATOs para funciones sin ninguno (--strict implícito)") -> None:
    """Agrega flag --fix."""
    parser.add_argument("--fix", action="store_true", help=help_text)


def add_min_score_arg(parser: argparse.ArgumentParser) -> None:
    """Agrega argumento --min-score (DEPRECADO)."""
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="DEPRECADO: usar --max-rns-fake y --max-rns-huerfanas. Falla si el score es menor",
    )


def add_max_rns_args(parser: argparse.ArgumentParser) -> None:
    """Agrega argumentos --max-rns-fake y --max-rns-huerfanas."""
    parser.add_argument(
        "--max-rns-fake",
        type=int,
        default=0,
        help="Máximo de RNs fake permitidas. Falla si se supera. Default: 0",
    )
    parser.add_argument(
        "--max-rns-huerfanas",
        type=int,
        default=None,
        help="Máximo de RNs huerfanas permitidas. Falla si se supera. Default: no falla",
    )


def add_show_legacy_score_flag(parser: argparse.ArgumentParser) -> None:
    """Agrega flag --show-legacy-score."""
    parser.add_argument(
        "--show-legacy-score",
        action="store_true",
        help="Muestra el score AI-Native deprecado (0-100)",
    )


def add_format_arg(parser: argparse.ArgumentParser, default: str = "text") -> None:
    """Agrega argumento --format con choices text/json."""
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default=default,
        help="Formato de salida",
    )


def add_staged_flag(parser: argparse.ArgumentParser) -> None:
    """Agrega flag --staged para pre-commit."""
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Usar archivos staged de git (default si no se pasan archivos)",
    )


def add_include_private_flag(parser: argparse.ArgumentParser) -> None:
    """Agrega flag --include-private."""
    parser.add_argument(
        "--include-private",
        action="store_true",
        help="Incluir funciones privadas (prefijo _)",
    )


def add_force_flag(parser: argparse.ArgumentParser, help_text: str = "Forzar operación") -> None:
    """Agrega flag --force."""
    parser.add_argument("--force", action="store_true", help=help_text)


def add_show_flag(parser: argparse.ArgumentParser) -> None:
    """Agrega flag --show para mostrar contenido."""
    parser.add_argument(
        "--show",
        action="store_true",
        help="Mostrar contenido generado",
    )
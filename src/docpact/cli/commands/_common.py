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

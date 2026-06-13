"""Reporting commands: report and briefing."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def cmd_report(args: argparse.Namespace) -> int:
    """Genera reporte de delta REGISTRO.md vs código real."""
    from docpact.reporter import (
        generar_reporte,
        generar_tabla,
        generar_json,
        validar_ci,
    )

    project_root = Path(os.path.abspath(args.project_root))
    registro = args.registro

    resultados = generar_reporte(project_root, registro)

    if not resultados:
        print("No se encontraron RNs en REGISTRO.md")
        return 0

    if args.json:
        print(generar_json(resultados))
    else:
        print(generar_tabla(resultados))

    if args.ci:
        pass_ci, errores_ci = validar_ci(resultados)
        if not pass_ci:
            print("\n❌ CI FAILED:")
            for err in errores_ci:
                print(f"  {err}")
            return 1
        print("\n✅ CI PASSED")

    return 0


def cmd_briefing(args: argparse.Namespace) -> int:
    """Comando briefing: genera o actualiza el briefing de reglas de negocio."""
    from docpact.briefing import generar_briefing, leer_briefing

    root = Path(args.path)
    if not root.exists():
        print(f"No encontrado: {root}", file=sys.stderr)
        return 2

    briefing_path, fue_regenerado = generar_briefing(
        root, force=getattr(args, "force", False)
    )

    if getattr(args, "json", False):
        data = {
            "path": str(briefing_path),
            "updated": fue_regenerado,
            "exists": briefing_path.exists(),
        }
        if fue_regenerado:
            data["content"] = leer_briefing(root)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif getattr(args, "show", False):
        contenido = leer_briefing(root)
        if contenido:
            print(contenido)
        else:
            print("Briefing no generado", file=sys.stderr)
            return 1
    else:
        if fue_regenerado:
            print(f"Briefing generado: {briefing_path}")
        else:
            print(f"Briefing ya actualizado: {briefing_path}")

    return 0

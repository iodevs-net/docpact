"""Reporting commands: report and briefing."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ._common import add_force_flag, add_json_flag, add_project_root_arg, add_show_flag


def cmd_report(args: argparse.Namespace) -> int:
    """Genera reporte de delta REGISTRO.md vs código real."""
    from docpact.reporter import (
        generar_reporte,
        generar_tabla,
        generar_json,
        validar_ci,
    )

    project_root = Path(os.path.abspath(args.project_root or "."))
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


def register(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register report and briefing subcommands."""
    # ── report ──
    report_parser = subparsers.add_parser(
        "report",
        help=(
            "Reporte delta: muestra reglas declaradas en REGISTRO.md vs evidencia en código. "
            "Útil para identificar RNs sin implementación o código sin CONTRATO"
        ),
    )
    add_project_root_arg(report_parser, required=False)
    report_parser.add_argument(
        "--registro",
        type=str,
        default=None,
        help="Path al REGISTRO.md (default: docs/reglas-del-negocio/REGISTRO.md)",
    )
    add_json_flag(report_parser)
    report_parser.add_argument(
        "--ci",
        action="store_true",
        help="Modo CI: falla si RNs con marcador no tienen test",
    )
    report_parser.set_defaults(func=cmd_report)

    # ── briefing ──
    briefing_parser = subparsers.add_parser(
        "briefing",
        help=(
            "Generate or update a business rules briefing for AI agents. "
            "Creates .docpact/briefing.md with project context. "
            "Auto-updates when code changes."
        ),
    )
    briefing_parser.add_argument(
        "path",
        type=str,
        nargs="?",
        default=".",
        help="Project root (default: current directory)",
    )
    add_force_flag(briefing_parser, help_text="Force regeneration even if briefing is up-to-date")
    add_json_flag(briefing_parser)
    add_show_flag(briefing_parser)
    briefing_parser.set_defaults(func=cmd_briefing)

    return report_parser

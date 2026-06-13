"""Runtime commands: guard, run, doctor.

Handles sandbox execution, contract validation, and ecosystem diagnostics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_guard(args: argparse.Namespace) -> int:
    """Comando guard: valida un cambio contra los CONTRATOs."""
    from docpact.guard import validar_cambio

    archivo = args.archivo
    diff = args.diff

    if not Path(archivo).exists():
        print(f"Archivo no encontrado: {archivo}", file=sys.stderr)
        return 2

    resultado = validar_cambio(archivo, diff)

    if resultado.allowed:
        print(f"Cambio seguro: {resultado.message}")
        return 0
    else:
        print(resultado.message)
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    """Comando run: verificación dinámica en sandbox."""
    from docpact.runner import main as runner_main

    argv = [args.path, "--tests", args.tests]
    if getattr(args, "max_iterations", None):
        argv += ["--max-iterations", str(args.max_iterations)]
    if getattr(args, "build", False):
        argv += ["--build"]
    return runner_main(argv)


def cmd_doctor(args: argparse.Namespace) -> int:
    """Comando doctor: autodiagnóstico del ecosistema."""
    from docpact.checker.doctor import ejecutar

    resultado = ejecutar(args.path, min_score=args.min_score)

    if args.json:
        data = {
            "checks": [
                {
                    "nombre": c.nombre,
                    "estado": c.estado,
                    "mensaje": c.mensaje,
                    "fix": c.fix,
                }
                for c in resultado.checks
            ],
            "score": resultado.score,
            "ok": resultado.ok,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        for c in resultado.checks:
            icono = "✅" if c.estado else "❌"
            print(f"{icono} {c.nombre}: {c.mensaje}")
            if not c.estado and c.fix:
                print(f"   Fix: {c.fix}")
        print(f"\n{'✅' if resultado.ok else '❌'} Doctor: {resultado.resumen()}")

    return 0 if resultado.ok else 1


def register(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register guard, run, and doctor subcommands."""
    # ── guard ──
    guard_parser = subparsers.add_parser(
        "guard",
        help="Valida un cambio contra los CONTRATOs antes de aplicarlo",
    )
    guard_parser.add_argument(
        "archivo",
        type=str,
        help="Path del archivo a modificar",
    )
    guard_parser.add_argument(
        "diff",
        type=str,
        help="El diff o código nuevo a aplicar",
    )
    guard_parser.set_defaults(func=cmd_guard)

    # ── run ──
    run_parser = subparsers.add_parser(
        "run",
        help=(
            "Dynamic verification in a sandbox. "
            "Executes code and tests in isolation to verify side effects at runtime"
        ),
    )
    run_parser.add_argument(
        "path",
        type=str,
        nargs="?",
        help="Archivo o directorio a verificar dinámicamente",
    )
    run_parser.add_argument("--tests", required=True, help="Directorio con tests")
    run_parser.add_argument("--max-iterations", type=int, default=10)
    run_parser.add_argument(
        "--build", action="store_true", help="Construir imagen sandbox"
    )
    run_parser.set_defaults(func=cmd_run)

    # ── doctor ──
    doctor_parser = subparsers.add_parser(
        "doctor",
        help=(
            "Self-diagnosis of the docpact ecosystem. "
            "Checks Python version, installed packages, config files, and project health"
        ),
    )
    doctor_parser.add_argument(
        "path", type=str, nargs="?", default=".", help="Raíz del proyecto"
    )
    doctor_parser.add_argument(
        "--min-score", type=int, default=90, help="Score mínimo requerido (defecto: 90)"
    )
    doctor_parser.add_argument(
        "--json", action="store_true", help="Salida en formato JSON"
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    return guard_parser

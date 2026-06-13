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

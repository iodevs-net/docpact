"""CLI de docpact — punto de entrada principal.

Setup mínimo de argparse + dispatch a comandos.
Cada comando se registra via su módulo en cli/commands/.
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger("docpact.cli")


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada principal del CLI."""
    parser = argparse.ArgumentParser(
        prog="docpact",
        description="Type checker for business rules — verifies code implements the rules declared in CONTRATOs",
        epilog="Quick start: docpact check . && docpact verify-rn --project-root . && docpact traceability --project-root .",
    )
    parser.add_argument(
        "--version", action="version", version=f"docpact {_get_version()}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Comando")

    # Registrar todos los comandos desde sus módulos
    from docpact.cli.commands.extract import register as reg_extract
    from docpact.cli.commands.check import register as reg_check
    from docpact.cli.commands.test import register as reg_test
    from docpact.cli.commands.mcp import register as reg_mcp
    from docpact.cli.commands.generate import register as reg_generate
    from docpact.cli.commands.report import register as reg_report
    from docpact.cli.commands.runtime import register as reg_runtime

    reg_extract(subparsers)
    reg_check(subparsers)
    reg_test(subparsers)
    reg_mcp(subparsers)
    reg_generate(subparsers)
    reg_report(subparsers)
    reg_runtime(subparsers)

    args = parser.parse_args(argv)

    # Dispatch via func default set by register()
    handler = getattr(args, "func", None)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 0


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("docpact")
    except Exception:
        return "0.1.0-dev"


if __name__ == "__main__":
    sys.exit(main())

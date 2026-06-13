"""CLI de docpact — punto de entrada principal.

Contiene solo el setup de argparse y el dispatch a comandos.
Los handlers de comandos están en cli/commands.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from docpact.checker.rn_verifier import verify_all_rns

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

    # ├─ extract
    extract_parser = subparsers.add_parser(
        "extract",
        help=(
            "Extract CONTRATOs from Python/TypeScript/JSX files as JSON or text. "
            "Use to inspect what docpact sees before running check"
        ),
    )
    extract_parser.add_argument(
        "path", type=str, help="Archivo o directorio a analizar"
    )
    extract_parser.add_argument(
        "--include-private",
        action="store_true",
        help="Incluir funciones privadas (prefijo _)",
    )
    extract_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Formato de salida"
    )

    # ├─ check
    check_parser = subparsers.add_parser(
        "check",
        help=(
            "Verifica CONTRATOS: side_effects, dependencias y RNs fake. "
            "Ejecutar después de escribir o modificar código. "
            "Para arreglar errores: agregar CONTRATO faltante o corregir side_effects en el docstring"
        ),
    )
    check_parser.add_argument("path", type=str, help="Archivo o directorio a verificar")
    check_parser.add_argument(
        "--strict",
        action="store_true",
        help="Falla si hay funciones públicas sin CONTRATO",
    )
    check_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Ruta al archivo de configuración docpact.toml",
    )
    check_parser.add_argument(
        "--diff",
        action="store_true",
        help="Solo verificar archivos modificados vs HEAD (git diff)",
    )
    check_parser.add_argument(
        "--report", action="store_true", help="Reporte detallado con sugerencias"
    )
    check_parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-genera CONTRATOs para funciones sin ninguno (--strict implícito)",
    )
    check_parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="DEPRECADO: usar --max-rns-fake y --max-rns-huerfanas. Falla si el score (vanity metric) es menor",
    )
    check_parser.add_argument(
        "--max-rns-fake",
        type=int,
        default=0,
        help="Máximo de RNs fake permitidas (mentiras del agente en CONTRATOS). Falla si se supera. Default: 0",
    )
    check_parser.add_argument(
        "--max-rns-huerfanas",
        type=int,
        default=None,
        help="Máximo de RNs huerfanas permitidas (en REGISTRO sin CONTRATO). Falla si se supera. Default: no falla",
    )
    check_parser.add_argument(
        "--show-legacy-score",
        action="store_true",
        help="Muestra el score AI-Native deprecado (0-100). Por default se ocultan las métricas vanidosas",
    )
    check_parser.add_argument(
        "--no-run-tests",
        action="store_true",
        help="Desactiva la ejecución de tests dinámicos de Reglas de Negocio con pytest",
    )
    check_parser.add_argument(
        "--no-runtime",
        action="store_true",
        help="Desactiva el wrapper runtime de side_effects en pytest (evita ruido en tracebacks)",
    )

    # ├─ lint
    lint_parser = subparsers.add_parser(
        "lint",
        help=(
            "Static-only CONTRATO analysis (no pytest). "
            "Checks docstring syntax, side_effects declarations, and RN fake detection. "
            "Faster than 'check' — ideal for pre-commit hooks"
        ),
    )
    lint_parser.add_argument("path", type=str, help="Archivo o directorio a verificar")
    lint_parser.add_argument(
        "--strict",
        action="store_true",
        help="Falla si hay funciones públicas sin CONTRATO",
    )
    lint_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Ruta al archivo de configuración docpact.toml",
    )
    lint_parser.add_argument(
        "--diff",
        action="store_true",
        help="Solo verificar archivos modificados vs HEAD (git diff)",
    )
    lint_parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="DEPRECADO: usar --max-rns-fake y --max-rns-huerfanas. Falla si el score (vanity metric) es menor",
    )
    lint_parser.add_argument(
        "--max-rns-fake",
        type=int,
        default=0,
        help="Máximo de RNs fake permitidas. Falla si se supera. Default: 0",
    )
    lint_parser.add_argument(
        "--max-rns-huerfanas",
        type=int,
        default=None,
        help="Máximo de RNs huerfanas permitidas. Falla si se supera. Default: no falla",
    )
    lint_parser.add_argument(
        "--show-legacy-score",
        action="store_true",
        help="Muestra el score AI-Native deprecado (0-100). Por default se ocultan las métricas vanidosas",
    )
    lint_parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-genera CONTRATOs para funciones sin ninguno (--strict implícito)",
    )

    # ├─ test
    test_parser = subparsers.add_parser(
        "test",
        help=(
            "Execute RN business rule tests with pytest. "
            "Runs tests/rn/ directory to verify that declared rules actually work at runtime"
        ),
    )
    test_parser.add_argument("path", type=str, help="Archivo o directorio a verificar")
    test_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Ruta al archivo de configuración docpact.toml",
    )

    # ├─ index
    index_parser = subparsers.add_parser(
        "index", help="Genera índice pre-calculado para el MCP server"
    )
    index_parser.add_argument(
        "path",
        type=str,
        nargs="?",
        default=".",
        help="Raíz del proyecto (default: directorio actual)",
    )
    index_parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerar índice aunque ya exista",
    )

    # ├─ validate
    validate_parser = subparsers.add_parser(
        "validate",
        help=(
            "Hook pre-commit: valida CONTRATOS en archivos staged (<1s). "
            "Solo revisa archivos que se están commiteando. "
            "Falla si CONTRATOs declarados contradicen la implementación"
        ),
    )
    validate_parser.add_argument(
        "files", nargs="*", help="Archivos a validar (git staged files si se omite)"
    )
    validate_parser.add_argument(
        "--staged",
        action="store_true",
        help="Usar archivos staged de git (default si no se pasan archivos)",
    )

    # ├─ mcp
    mcp_parser = subparsers.add_parser(
        "mcp",
        help=(
            "Start MCP server for agent integration (JSON-RPC over stdio). "
            "Provides docpact tools to AI agents via Model Context Protocol"
        ),
    )
    mcp_parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Raíz del proyecto (default: directorio actual)",
    )

    # ├─ mcp-doctor
    mcp_doctor_parser = subparsers.add_parser(
        "mcp-doctor",
        help="Diagnostica por qué las tools MCP no cargan en el host (stdio, wrapper, etc.)",
    )
    mcp_doctor_parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Raíz del proyecto (default: directorio actual)",
    )
    mcp_doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Output estructurado en JSON (para tooling y agentes)",
    )

    # ├─ test-quality
    quality_parser = subparsers.add_parser(
        "test-quality",
        help="Detecta tests placeholder (cuerpo vacio, assert True, etc.)",
    )
    quality_parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Raíz del proyecto (default: directorio actual)",
    )
    quality_parser.add_argument(
        "--json",
        action="store_true",
        help="Output estructurado en JSON",
    )

    # ├─ install-mcp
    install_parser = subparsers.add_parser(
        "install-mcp",
        help="Configura docpact como MCP server en el host del agent (OMP/Claude Code)",
    )
    install_parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Raíz del proyecto (default: directorio actual)",
    )
    install_parser.add_argument(
        "--wrapper",
        type=str,
        default=None,
        help="Path al wrapper script (default: scripts/docpact-mcp-wrapper.sh en project-root)",
    )
    install_parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Forzar host ('omp', 'omp_project', 'claude_code', 'project'). Default: autodetectar",
    )
    install_parser.add_argument(
        "--json",
        action="store_true",
        help="Output estructurado en JSON",
    )

    # ├─ config-suggest
    suggest_parser = subparsers.add_parser(
        "config-suggest",
        help=(
            "Suggest docpact.toml patterns for RNs without validators. "
            "Use when 'verify-rn' reports NO_PATTERN for a business rule"
        ),
    )
    suggest_parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Raíz del proyecto a analizar (default: directorio actual)",
    )
    suggest_parser.add_argument(
        "--apply",
        action="store_true",
        help="Escribir las sugerencias a docpact.toml (default: dry-run)",
    )
    suggest_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.5,
        help="Confidence mínima para incluir una sugerencia (0-1, default: 0.5)",
    )
    suggest_parser.add_argument(
        "--json",
        action="store_true",
        help="Output estructurado en JSON",
    )

    # ├─ report
    report_parser = subparsers.add_parser(
        "report",
        help=(
            "Reporte delta: muestra reglas declaradas en REGISTRO.md vs evidencia en código. "
            "Útil para identificar RNs sin implementación o código sin CONTRATO"
        ),
    )
    report_parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Raíz del proyecto (default: directorio actual)",
    )
    report_parser.add_argument(
        "--registro",
        type=str,
        default=None,
        help="Path al REGISTRO.md (default: docs/reglas-del-negocio/REGISTRO.md)",
    )
    report_parser.add_argument(
        "--json",
        action="store_true",
        help="Output estructurado en JSON (para agentes)",
    )
    report_parser.add_argument(
        "--ci",
        action="store_true",
        help="Modo CI: falla si RNs con marcador no tienen test",
    )

    # ├─ traceability
    traceability_parser = subparsers.add_parser(
        "traceability",
        help=(
            "Matriz de trazabilidad: cruza RNs declaradas con tests existentes. "
            "Muestra %% de cobertura por módulo. "
            "Un 100%% significa que toda regla declarada tiene al menos un test"
        ),
    )
    traceability_parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Raíz del proyecto (default: directorio actual)",
    )
    traceability_parser.add_argument(
        "--json",
        action="store_true",
        help="Output estructurado en JSON",
    )

    # ├─ llm-judge
    llm_judge_parser = subparsers.add_parser(
        "llm-judge",
        help="Evalua si un test verifica la regla usando un LLM (OpenAI-compatible)",
    )
    llm_judge_parser.add_argument(
        "test_file", type=str, help="Path al archivo de test (.py)"
    )
    llm_judge_parser.add_argument(
        "--rn-descripcion",
        type=str,
        required=True,
        help="Descripcion de la regla de negocio que el test deberia verificar",
    )
    llm_judge_parser.add_argument(
        "--json",
        action="store_true",
        help="Output estructurado en JSON",
    )

    # ├─ init
    init_parser = subparsers.add_parser(
        "init",
        help=(
            "Generate CONTRATO skeletons for functions missing them. "
            "Use --batch to scaffold an entire directory, or --function for one"
        ),
    )
    init_parser.add_argument("path", type=str, help="Archivo o directorio")
    init_parser.add_argument(
        "--function", type=str, default=None, help="Nombre específico de función"
    )
    init_parser.add_argument(
        "--batch", action="store_true", help="Procesar todo el directorio"
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Forzar generación incluso si la función tiene docstring sin CONTRATO",
    )

    # ├─ run
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

    # ├─ doctor
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

    # ├─ fix
    fix_parser = subparsers.add_parser(
        "fix",
        help=(
            "Auto-fix CONTRATO signature warnings. "
            "Updates docstrings to match actual function signatures (argument names, types)"
        ),
    )
    fix_parser.add_argument("path", type=str, help="Archivo o directorio a corregir")
    fix_parser.add_argument(
        "--diff",
        action="store_true",
        help="Solo afectar archivos modificados vs HEAD (git diff)",
    )

    # ├─ verify-rn
    verify_rn_parser = subparsers.add_parser(
        "verify-rn",
        help=(
            "Verifica que patrones de RNs (Reglas de Negocio) existan en código fuente. "
            "Chequea existencia de patrones y orden de validación. "
            "Ejecutar antes de cada commit para asegurar que reglas declaradas estén implementadas"
        ),
    )
    verify_rn_parser.add_argument(
        "--project-root",
        type=str,
        required=True,
        help="Raíz del proyecto a analizar",
    )
    verify_rn_parser.add_argument(
        "--json",
        action="store_true",
        help="Output estructurado en JSON",
    )

    # briefing
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
    briefing_parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if briefing is up-to-date",
    )
    briefing_parser.add_argument(
        "--json",
        action="store_true",
        help="Structured JSON output",
    )
    briefing_parser.add_argument(
        "--show",
        action="store_true",
        help="Print briefing to stdout instead of saving",
    )

    # guard
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

    args = parser.parse_args(argv)

    # Dispatch to command handlers
    from docpact.cli.commands import (
        cmd_extract,
        cmd_check,
        cmd_lint,
        cmd_test,
        cmd_init,
        cmd_run,
        cmd_index,
        cmd_validate,
        cmd_mcp,
        cmd_mcp_doctor,
        cmd_test_quality,
        cmd_install_mcp,
        cmd_config_suggest,
        cmd_report,
        cmd_doctor,
        cmd_fix,
        cmd_llm_judge,
        cmd_traceability,
        cmd_verify_rns,
        cmd_briefing,
        cmd_guard,
    )

    dispatch = {
        "extract": cmd_extract,
        "check": cmd_check,
        "lint": cmd_lint,
        "test": cmd_test,
        "init": cmd_init,
        "run": cmd_run,
        "index": cmd_index,
        "validate": cmd_validate,
        "mcp": cmd_mcp,
        "mcp-doctor": cmd_mcp_doctor,
        "test-quality": cmd_test_quality,
        "install-mcp": cmd_install_mcp,
        "config-suggest": cmd_config_suggest,
        "report": cmd_report,
        "doctor": cmd_doctor,
        "fix": cmd_fix,
        "llm-judge": cmd_llm_judge,
        "traceability": cmd_traceability,
        "verify-rn": cmd_verify_rns,
        "briefing": cmd_briefing,
        "guard": cmd_guard,
    }

    handler = dispatch.get(args.command)
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

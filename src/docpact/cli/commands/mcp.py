"""MCP integration commands: mcp, mcp-doctor, install-mcp."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def cmd_mcp(args: argparse.Namespace) -> int:
    """Comando mcp: inicia el MCP server para agentes."""
    from docpact.mcp_server import main as mcp_main

    if args.project_root:
        os.environ["DOCPACT_PROJECT_ROOT"] = os.path.abspath(args.project_root)

    return mcp_main()


def cmd_mcp_doctor(args: argparse.Namespace) -> int:
    """Diagnostica el entorno MCP."""
    from docpact.mcp_server import diagnostico

    if args.project_root:
        os.environ["DOCPACT_PROJECT_ROOT"] = os.path.abspath(args.project_root)

    diag = diagnostico()
    problemas = []
    if not diag["docpact_in_PATH"]:
        problemas.append("docpact no esta en PATH — el host MCP no lo va a encontrar")
    if not diag["index_exists"]:
        problemas.append("index no existe — corre `docpact index` antes de usar MCP")

    if getattr(args, "json", False):
        out = dict(diag)
        out["problemas"] = problemas
        out["ok"] = not problemas
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print("docpact MCP doctor\n")
        print(f"  Python:          {diag['python_version']}")
        print(f"  docpact path:    {diag['docpact_module_path']}")
        print(f"  docpact in PATH: {diag['docpact_in_PATH'] or 'NOT FOUND'}")
        print(f"  CWD:             {diag['cwd']}")
        print(f"  Project root:    {diag['project_root_env'] or '(CWD)'}")
        print(f"  Index:           {diag['index_path']}")
        print(f"  Index exists:    {'YES' if diag['index_exists'] else 'NO'}\n")
        if problemas:
            print("PROBLEMAS DETECTADOS:")
            for p in problemas:
                print(f"  - {p}")
            return 1
        print("OK — entorno listo para MCP")
    return 0 if not problemas else 1


def cmd_install_mcp(args: argparse.Namespace) -> int:
    """Configura docpact como MCP server."""
    from docpact.installer import detectar_host, install_mcp as _install

    project_root = Path(args.project_root).resolve()
    wrapper = (
        Path(args.wrapper).resolve()
        if args.wrapper
        else project_root / "scripts" / "docpact-mcp-wrapper.sh"
    )
    host = args.host or detectar_host()

    if not wrapper.exists():
        msg = f"wrapper no existe: {wrapper}"
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(f"❌ {msg}")
            print(f"   Creá el wrapper primero o pasá --wrapper /path/to/wrapper.sh")
        return 1

    result = _install(project_root=project_root, wrapper=wrapper, host=host)

    if getattr(args, "json", False):
        result_json = {
            "ok": result["error"] is None,
            "host": result["host"],
            "config_path": str(result["config_path"])
            if result["config_path"]
            else None,
            "wrapper_verified": result["wrapper_verified"],
            "error": result["error"],
        }
        print(json.dumps(result_json, indent=2))
    else:
        if result["error"]:
            print(f"❌ {result['error']}")
            return 1
        print(f"✅ MCP docpact instalado para host '{result['host']}'")
        print(f"   config: {result['config_path']}")
        print(f"   wrapper: {'verificado' if result['wrapper_verified'] else 'FALLA'}")
        if host in ("omp", "omp_project"):
            print(f"   → Reiniciá OMP para que cargue la nueva config")
        else:
            print(f"   → Reiniciá Claude Code para que cargue la nueva config")

    return 0 if result["error"] is None else 1


def register(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register mcp, mcp-doctor, and install-mcp subcommands."""
    # ── mcp ──
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
    mcp_parser.set_defaults(func=cmd_mcp)

    # ── mcp-doctor ──
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
    mcp_doctor_parser.set_defaults(func=cmd_mcp_doctor)

    # ── install-mcp ──
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
    install_parser.set_defaults(func=cmd_install_mcp)

    return mcp_parser

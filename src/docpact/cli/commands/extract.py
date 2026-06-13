"""Extraction & indexing commands for docpact CLI.

Handles: extract, index, traceability.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ._common import _es_excluido, _print_contrato_texto, add_format_arg, add_include_private_flag, add_json_flag, add_path_arg


def cmd_extract(args: argparse.Namespace) -> int:
    """Comando extract: extrae CONTRATOS de archivos."""
    from docpact.parser.extractor import extraer_docstrings
    from docpact.parser.lexer import tokenizar
    from docpact.parser.parser import parsear
    from docpact.parser.ts_parser import extraer_contratos_ts

    path = Path(args.path)
    if path.is_dir():
        archivos = (
            list(path.rglob("*.py"))
            + list(path.rglob("*.ts"))
            + list(path.rglob("*.tsx"))
            + list(path.rglob("*.jsx"))
        )
    elif path.is_file():
        archivos = [path]
    else:
        print(f"❌ No encontrado: {path}", file=sys.stderr)
        return 2

    resultados = []
    for archivo in archivos:
        if _es_excluido(archivo):
            continue

        ext = archivo.suffix
        if ext in (".ts", ".tsx", ".jsx"):
            try:
                ts_resultados = extraer_contratos_ts(str(archivo))
            except (FileNotFoundError, UnicodeDecodeError) as e:
                print(f"⚠️  {archivo}: {e}", file=sys.stderr)
                continue
            for r in ts_resultados:
                resultados.append(
                    {
                        "archivo": str(archivo),
                        "funcion": r.get("nombre_funcion", "<desconocida>"),
                        "tipo": "function",
                        "linea": r.get("linea", 0),
                        "contrato": {
                            "input": r.get("input", {}),
                            "output": r.get("output"),
                            "output_descripcion": None,
                            "side_effects": r.get("side_effects", []),
                            "rn": r.get("rn", []),
                            "borde": r.get("borde", []),
                            "dependencias": r.get("dependencias", []),
                        },
                        "errores": [],
                    }
                )
            continue

        try:
            docstrings = extraer_docstrings(
                archivo, incluir_privadas=args.include_private
            )
        except (SyntaxError, FileNotFoundError) as e:
            print(f"⚠️  {archivo}: {e}", file=sys.stderr)
            continue

        for linea, nombre, tipo, doc in docstrings:
            tokens = tokenizar(doc)
            contrato, errores = parsear(tokens)
            if (
                contrato.side_effects
                or contrato.rn
                or contrato.input
                or contrato.output
            ):
                resultados.append(
                    {
                        "archivo": str(archivo),
                        "funcion": nombre,
                        "tipo": tipo,
                        "linea": linea,
                        "contrato": {
                            "input": {
                                k: {"tipo": v.tipo, "descripcion": v.descripcion}
                                for k, v in contrato.input.items()
                            },
                            "output": contrato.output,
                            "output_descripcion": contrato.output_descripcion,
                            "side_effects": [
                                s.descripcion for s in contrato.side_effects
                            ],
                            "rn": [
                                {"id": r.id, "descripcion": r.descripcion}
                                for r in contrato.rn
                            ],
                            "borde": [
                                {
                                    "condicion": b.condicion,
                                    "comportamiento": b.comportamiento,
                                }
                                for b in contrato.borde
                            ],
                            "dependencias": [d.ref for d in contrato.dependencias],
                        },
                        "errores": [
                            {
                                "campo": e.campo,
                                "mensaje": e.mensaje,
                                "sugerencia": e.sugerencia,
                            }
                            for e in errores
                        ],
                    }
                )

    if args.format == "json":
        print(json.dumps(resultados, indent=2, ensure_ascii=False))
    else:
        if not resultados:
            print("📭 No se encontraron CONTRATOS.")
            return 0
        print(f"📄 {len(resultados)} CONTRATOS encontrados:\n")
        for r in resultados:
            _print_contrato_texto(r)

    return 0


def cmd_index(args: argparse.Namespace) -> int:
    """Comando index: genera índice pre-calculado para el MCP server."""
    from docpact.index import generar_index, guardar_index

    project_root = os.path.abspath(args.path)
    index_path = Path(project_root) / ".docpact" / "index.json"

    if index_path.exists() and not args.force:
        print(f"ℹ️  Índice ya existe: {index_path}")
        print("   Usa --force para regenerar")
        return 0

    print(f"🔍 Escaneando {project_root}...")
    index = generar_index(project_root)
    path = guardar_index(index, project_root)

    stats = index["stats"]
    print(f"✅ Índice generado: {path}")
    print(f"   Funciones: {stats['total_funciones']}")
    print(f"   Con RNs: {stats['funciones_con_rn']}")
    print(f"   RNs: {stats['total_rns']}")
    print(f"   RNs con test: {stats['rns_con_test']}")
    print(f"   Tamaño: {os.path.getsize(path) / 1024:.1f} KB")
    return 0


def cmd_traceability(args: argparse.Namespace) -> int:
    """Comando traceability: genera matriz de trazabilidad RN."""
    from docpact.checker.rn_traceability import build_traceability, print_traceability

    root = Path(args.project_root).resolve()
    matrix = build_traceability(root)

    if getattr(args, "json", False):
        print(
            json.dumps(
                matrix,
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print_traceability(matrix)

    problematic = sum(
        1 for entry in matrix.values() if entry["status"] in ("ORPHAN", "DECLARED_ONLY")
    )
    return 1 if problematic else 0


def register(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register extract, index, and traceability subcommands."""
    # ── extract ──
    extract_parser = subparsers.add_parser(
        "extract",
        help=(
            "Extract CONTRATOs from Python/TypeScript/JSX files as JSON or text. "
            "Use to inspect what docpact sees before running check"
        ),
    )
    add_path_arg(extract_parser)
    add_include_private_flag(extract_parser)
    add_format_arg(extract_parser)
    extract_parser.set_defaults(func=cmd_extract)

    # ── index ──
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
    index_parser.set_defaults(func=cmd_index)

    # ── traceability ──
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
    add_json_flag(traceability_parser)
    traceability_parser.set_defaults(func=cmd_traceability)

    return extract_parser

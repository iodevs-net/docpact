"""CLI de docpact — punto de entrada principal.

Comandos:
  extract   Extrae CONTRATOS de archivos Python/TypeScript
  check     Verifica CONTRATOS (Fase 2)
  init      Genera esqueletos de CONTRATO (Fase 4)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada principal del CLI."""
    parser = argparse.ArgumentParser(
        prog="docpact",
        description="Verificador de CONTRATOS en código — sincroniza docstrings con implementación real",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"docpact {_get_version()}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Comando")

    # ├─ extract
    extract_parser = subparsers.add_parser(
        "extract", help="Extrae CONTRATOS de archivos Python/TypeScript/JSX"
    )
    extract_parser.add_argument(
        "path", type=str, help="Archivo o directorio a analizar"
    )
    extract_parser.add_argument(
        "--include-private", action="store_true",
        help="Incluir funciones privadas (prefijo _)"
    )
    extract_parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Formato de salida"
    )

    # ├─ check  (Fase 2 — placeholder)
    check_parser = subparsers.add_parser(
        "check", help="Verifica CONTRATOS contra implementación"
    )
    check_parser.add_argument(
        "path", type=str, help="Archivo o directorio a verificar"
    )
    check_parser.add_argument(
        "--strict", action="store_true",
        help="Falla si hay funciones públicas sin CONTRATO"
    )
    check_parser.add_argument(
        "--config", type=str, default=None,
        help="Ruta al archivo de configuración docpact.toml"
    )
    check_parser.add_argument(
        "--report", action="store_true",
        help="Reporte detallado con sugerencias"
    )

    # ├─ mcp
    mcp_parser = subparsers.add_parser(
        "mcp", help="Inicia el MCP server para agentes (JSON-RPC sobre stdio)"
    )

    # ├─ init  (Fase 4 — placeholder)
    init_parser = subparsers.add_parser(
        "init", help="Genera esqueletos de CONTRATO para funciones sin contrato"
    )
    init_parser.add_argument(
        "path", type=str, help="Archivo o directorio"
    )
    init_parser.add_argument(
        "--function", type=str, default=None,
        help="Nombre específico de función"
    )
    init_parser.add_argument(
        "--batch", action="store_true",
        help="Procesar todo el directorio"
    )

    # ├─ run
    run_parser = subparsers.add_parser(
        "run", help="Verificación dinámica en sandbox"
    )
    run_parser.add_argument(
        "path", type=str, nargs="?",
        help="Archivo o directorio a verificar dinámicamente"
    )
    run_parser.add_argument(
        "--tests", required=True,
        help="Directorio con tests"
    )
    run_parser.add_argument(
        "--max-iterations", type=int, default=10
    )
    run_parser.add_argument(
        "--build", action="store_true",
        help="Construir imagen sandbox"
    )

    args = parser.parse_args(argv)

    if args.command == "extract":
        return _cmd_extract(args)
    elif args.command == "check":
        return _cmd_check(args)
    elif args.command == "init":
        return _cmd_init(args)
    elif args.command == "run":
        return _cmd_run(args)
    elif args.command == "mcp":
        return _cmd_mcp(args)
    else:
        parser.print_help()
        return 0


def _get_version() -> str:
    try:
        from docpact import __version__
        return __version__
    except ImportError:
        return "0.1.0-dev"


def _cmd_extract(args: argparse.Namespace) -> int:
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
                resultados.append({
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
                })
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
            if contrato.side_effects or contrato.rn or contrato.input or contrato.output:
                resultados.append({
                    "archivo": str(archivo),
                    "funcion": nombre,
                    "tipo": tipo,
                    "linea": linea,
                    "contrato": {
                        "input": {k: {"tipo": v.tipo, "descripcion": v.descripcion}
                                  for k, v in contrato.input.items()},
                        "output": contrato.output,
                        "output_descripcion": contrato.output_descripcion,
                        "side_effects": [s.descripcion for s in contrato.side_effects],
                        "rn": [{"id": r.id, "descripcion": r.descripcion} for r in contrato.rn],
                        "borde": [{"condicion": b.condicion, "comportamiento": b.comportamiento}
                                  for b in contrato.borde],
                        "dependencias": [d.ref for d in contrato.dependencias],
                    },
                    "errores": [{"campo": e.campo, "mensaje": e.mensaje, "sugerencia": e.sugerencia}
                                for e in errores],
                })

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
        print(f"  rn: {', '.join(r['id'] for r in c['rn'])}")
    if c.get("errores"):
        for e in c["errores"]:
            msg = f"  ⚠️  [{e['campo']}] {e['mensaje']}"
            if e.get("sugerencia"):
                msg += f"\n     💡 {e['sugerencia']}"
            print(msg)
    print()


def _cmd_check(args: argparse.Namespace) -> int:
    """Comando check: verifica CONTRATOS contra implementación real."""
    from docpact.config import DocpactConfig
    from docpact.checker.orchestrator import check_proyecto

    # Cargar configuración
    config_path = args.config
    if not config_path:
        # Buscar docpact.toml en el path analizado
        config_candidates = [
            Path(args.path) / "docpact.toml",
            Path(args.path) / ".docpact.toml",
            Path.cwd() / "docpact.toml",
        ]
        for cp in config_candidates:
            if cp.exists():
                config_path = str(cp)
                break

    config = DocpactConfig.desde_toml(config_path) if config_path else DocpactConfig()
    if args.strict:
        # Sobrescribir strict desde flag CLI
        config.strict = True

    resultado = check_proyecto(args.path, config)

    # Salida
    tf = resultado.total_funciones
    tc = resultado.funciones_con_contrato
    te = resultado.total_errores
    tw = resultado.total_warnings
    score = resultado.calcular_score()
    nivel = resultado.nivel

    print(f"\n📊 {tf} funciones públicas encontradas")
    print(f"✅ {tc} contratos válidos")
    if tw:
        print(f"⚠️  {tw} warnings")
    else:
        print(f"⚠️  0 warnings")
    if te:
        print(f"❌ {te} errores")
    else:
        print(f"✅ 0 errores")
    print(f"\nScore: {score}/100 — {nivel}")

    # Mostrar hallazgos detallados
    if args.report or te > 0 or tw > 0:
        for archivo_result in resultado.archivos:
            for func in archivo_result.funciones:
                if func.hallazgos:
                    for h in func.hallazgos:
                        icono = "❌" if h.tipo == "error" else "⚠️"
                        loc = f"{archivo_result.archivo}::{h.funcion}:{h.linea}"
                        print(f"\n{icono} {loc}")
                        print(f"   {h.mensaje}")
                        if h.sugerencia:
                            print(f"   💡 {h.sugerencia}")
                    if not func.errores and not func.warnings:
                        print(f"  ✅ {func.nombre} — OK")

    if te > 0:
        return 1
    if config.strict and tf - tc > 0:
        # strict mode: funciones sin CONTRATO también fallan
        return 1
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    """Comando mcp: inicia el MCP server para agentes."""
    from docpact.mcp_server import main as mcp_main
    return mcp_main()



def _cmd_run(args: argparse.Namespace) -> int:
    """Comando run: verificación dinámica en sandbox."""
    from docpact.runner import main as runner_main
    argv = [args.path, "--tests", args.tests]
    if getattr(args, "max_iterations", None):
        argv += ["--max-iterations", str(args.max_iterations)]
    if getattr(args, "build", False):
        argv += ["--build"]
    return runner_main(argv)

def _cmd_init(args: argparse.Namespace) -> int:
    """Comando init: genera esqueletos de CONTRATO para funciones sin contrato."""
    from docpact.cli.init import init_function, init_batch

    safe = not args.force
    path = args.path
    if args.function:
        exito, msg = init_function(path, args.function, safe=safe)
        print(f"{'✅' if exito else '⚠️'} {msg}")
        return 0 if exito else 1
    elif args.batch:
        resultados = init_batch(path, safe=safe)
        exito = sum(1 for _, ok, _ in resultados if ok)
        total = len(resultados)
        print(f"📝 {exito}/{total} CONTRATOS generados")
        for nombre, ok, msg in resultados:
            print(f"  {'✅' if ok else '⚠️'} {msg}")
        return 0
    else:
        print("Usa --function <nombre> o --batch")
        return 1


def _es_excluido(path: Path) -> bool:
    """Verifica si un path debe ser excluido."""
    excluidos = {
        "__pycache__", ".venv", "venv", "node_modules",
        ".git", "migrations", ".pytest_cache",
    }
    for parte in path.parts:
        if parte in excluidos:
            return True
    return False


if __name__ == "__main__":
    sys.exit(main())

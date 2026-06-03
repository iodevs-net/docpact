"""CLI de docpact — punto de entrada principal.

Comandos:
  extract   Extrae CONTRATOS de archivos Python/TypeScript
  lint      Análisis estático puro (sin pytest, < 1s)
  test      Ejecuta tests de Reglas de Negocio con pytest
  check     lint + test combinados (comportamiento legacy)
  init      Genera esqueletos de CONTRATO
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
        "--version", action="version", version=f"docpact {_get_version()}"
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
        "--include-private",
        action="store_true",
        help="Incluir funciones privadas (prefijo _)",
    )
    extract_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Formato de salida"
    )

    # ├─ check  (Fase 2 — placeholder)
    check_parser = subparsers.add_parser(
        "check", help="Verifica CONTRATOS contra implementación"
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

    # ├─ lint (análisis estático puro — sin pytest)
    lint_parser = subparsers.add_parser(
        "lint", help="Análisis estático puro de CONTRATOS (sin pytest, ideal para pre-commit)"
    )
    lint_parser.add_argument("path", type=str, help="Archivo o directorio a verificar")
    lint_parser.add_argument(
        "--strict", action="store_true",
        help="Falla si hay funciones públicas sin CONTRATO",
    )
    lint_parser.add_argument(
        "--config", type=str, default=None,
        help="Ruta al archivo de configuración docpact.toml",
    )
    lint_parser.add_argument(
        "--diff", action="store_true",
        help="Solo verificar archivos modificados vs HEAD (git diff)",
    )
    lint_parser.add_argument(
        "--min-score", type=int, default=0,
        help="DEPRECADO: usar --max-rns-fake y --max-rns-huerfanas. Falla si el score (vanity metric) es menor",
    )
    lint_parser.add_argument(
        "--max-rns-fake", type=int, default=0,
        help="Máximo de RNs fake permitidas. Falla si se supera. Default: 0",
    )
    lint_parser.add_argument(
        "--max-rns-huerfanas", type=int, default=None,
        help="Máximo de RNs huerfanas permitidas. Falla si se supera. Default: no falla",
    )
    lint_parser.add_argument(
        "--show-legacy-score", action="store_true",
        help="Muestra el score AI-Native deprecado (0-100). Por default se ocultan las métricas vanidosas",
    )
    lint_parser.add_argument(
        "--fix", action="store_true",
        help="Auto-genera CONTRATOs para funciones sin ninguno (--strict implícito)",
    )

    # ├─ test (ejecución dinámica de tests RN)
    test_parser = subparsers.add_parser(
        "test", help="Ejecuta tests de Reglas de Negocio con pytest"
    )
    test_parser.add_argument("path", type=str, help="Archivo o directorio a verificar")
    test_parser.add_argument(
        "--config", type=str, default=None,
        help="Ruta al archivo de configuración docpact.toml",
    )

    # ├─ index — genera índice pre-calculado para MCP
    index_parser = subparsers.add_parser(
        "index", help="Genera índice pre-calculado para el MCP server"
    )
    index_parser.add_argument(
        "path", type=str, nargs="?", default=".",
        help="Raíz del proyecto (default: directorio actual)",
    )
    index_parser.add_argument(
        "--force", action="store_true",
        help="Regenerar índice aunque ya exista",
    )

    # ├─ mcp
    mcp_parser = subparsers.add_parser(
        "mcp", help="Inicia el MCP server para agentes (JSON-RPC sobre stdio)"
    )
    mcp_parser.add_argument(
        "--project-root", type=str, default=".",
        help="Raíz del proyecto (default: directorio actual)",
    )

    # ├─ init  (Fase 4 — placeholder)
    init_parser = subparsers.add_parser(
        "init", help="Genera esqueletos de CONTRATO para funciones sin contrato"
    )
    init_parser.add_argument("path", type=str, help="Archivo o directorio")
    init_parser.add_argument(
        "--function", type=str, default=None, help="Nombre específico de función"
    )
    init_parser.add_argument(
        "--batch", action="store_true", help="Procesar todo el directorio"
    )
    init_parser.add_argument(
        "--force", action="store_true",
        help="Forzar generación incluso si la función tiene docstring sin CONTRATO",
    )

    # ├─ run
    run_parser = subparsers.add_parser("run", help="Verificación dinámica en sandbox")
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
        "doctor", help="Autodiagnóstico del ecosistema"
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
        "fix", help="Auto-corrige warnings de firma en CONTRATOS"
    )
    fix_parser.add_argument(
        "path", type=str, help="Archivo o directorio a corregir"
    )
    fix_parser.add_argument(
        "--diff", action="store_true",
        help="Solo afectar archivos modificados vs HEAD (git diff)",
    )

    args = parser.parse_args(argv)

    if args.command == "extract":
        return _cmd_extract(args)
    elif args.command == "check":
        return _cmd_check(args)
    elif args.command == "lint":
        return _cmd_lint(args)
    elif args.command == "test":
        return _cmd_test(args)
    elif args.command == "init":
        return _cmd_init(args)
    elif args.command == "run":
        return _cmd_run(args)
    elif args.command == "index":
        return _cmd_index(args)
    elif args.command == "mcp":
        return _cmd_mcp(args)
    elif args.command == "doctor":
        return _cmd_doctor(args)
    elif args.command == "fix":
        return _cmd_fix(args)
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
        # Mostrar descripciones desde REGISTRO.md
        _cargadas = set()
        try:
            from docpact.checker.rn_registry import cargar_registro
            from pathlib import Path

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
    if args.strict or args.fix:
        # --fix implica --strict
        config.strict = True
    if args.no_run_tests:
        config.run_tests = False
    if getattr(args, "no_runtime", False):
        config.run_runtime = False
        import os as _os
        _os.environ["DOCPACT_NO_RUNTIME"] = "1"

    resultado = check_proyecto(args.path, config, diff_only=args.diff)

    # Salida
    tf = resultado.total_funciones
    tc = resultado.funciones_con_contrato
    te = resultado.total_errores
    tw = resultado.total_warnings
    score = resultado.calcular_score()
    nivel = resultado.nivel
    # metricas_honestas puede no existir en versiones viejas del checker;
    # fallback defensivo para que el CLI no rompa al actualizar
    _honestas = getattr(resultado, "metricas_honestas", None)
    if callable(_honestas):
        metricas = _honestas()
    else:
        metricas = {
            "rns_fake": len(getattr(resultado, "rns_fake", [])),
            "rns_huerfanas": len(getattr(resultado, "rns_huerfanas", [])),
            "rns_placeholders": len(getattr(resultado, "rns_placeholders", [])),
            "funciones_sin_contrato": tf - tc,
            "funciones_totales": tf,
            "score_legacy": score,
        }

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

    # ── Métricas honestas: lo que SÍ predice calidad ──
    rns_fake = metricas["rns_fake"]
    rns_huerfanas = metricas["rns_huerfanas"]
    rns_placeholders = metricas["rns_placeholders"]
    sin_contrato = metricas["funciones_sin_contrato"]

    print(f"\n🩺 Métricas honestas (lo que SÍ predice calidad):")
    if rns_fake == 0 and rns_huerfanas == 0:
        print(f"   ✅ Cero mentiras y cero olvidos vs REGISTRO.md")
    else:
        if rns_fake > 0:
            print(f"   🚨 RNs fake (en CONTRATO pero NO en REGISTRO): {rns_fake}")
            for fake in resultado.rns_fake[:5]:
                arch_short = fake.archivo.rsplit("/", 1)[-1] if "/" in fake.archivo else fake.archivo
                print(f"      └─ {fake.rn_id} en {arch_short}:{fake.linea} ({fake.funcion})")
            if len(resultado.rns_fake) > 5:
                print(f"      └─ ... y {len(resultado.rns_fake) - 5} más (usar --fix o revisar manualmente)")
        if rns_huerfanas > 0:
            print(f"   📋 RNs huerfanas (en REGISTRO pero NO en CONTRATO): {rns_huerfanas}")
            for h in resultado.rns_huerfanas[:5]:
                print(f"      └─ {h.rn_id}: {h.descripcion[:80]}")
            if len(resultado.rns_huerfanas) > 5:
                print(f"      └─ ... y {len(resultado.rns_huerfanas) - 5} más")
    if rns_placeholders > 0:
        print(f"   🚫 Placeholders excluidos (RN-XXX, RN-NO-APLICA, etc): {rns_placeholders}")
    if sin_contrato > 0:
        print(f"   ❌ Funciones públicas sin CONTRATO: {sin_contrato}")

    # ── Score legacy: deprecado, solo si el usuario lo pide ──
    if args.show_legacy_score:
        print(f"\n   [score legacy DEPRECADO: {score}/100 — {nivel}]")

    # ── Falla por métricas honestas (gating) ──
    if rns_fake > args.max_rns_fake:
        print(f"\n❌ {rns_fake} RNs fake superan el máximo permitido ({args.max_rns_fake})")
        return 1
    if args.max_rns_huerfanas is not None and rns_huerfanas > args.max_rns_huerfanas:
        print(f"\n❌ {rns_huerfanas} RNs huerfanas superan el máximo permitido ({args.max_rns_huerfanas})")
        return 1

    # ── Falla por score legacy (compat) ──
    if args.min_score and score < args.min_score:
        print(f"\n❌ Score legacy {score} menor al mínimo requerido ({args.min_score})")
        print(f"   ADVERTENCIA: --min-score usa el score DEPRECADO. Migrar a --max-rns-fake.")
        return 1

    # Auto-generar CONTRATOs si --fix está activo
    if args.fix:
        from docpact.cli.init import init_function
        from pathlib import Path as _Path

        _generados = 0
        _omitidos = 0
        for archivo_result in resultado.archivos:
            for func in archivo_result.funciones:
                if not func.tiene_contrato:
                    try:
                        exito, msg = init_function(
                            _Path(archivo_result.archivo), func.nombre, safe=True
                        )
                        if exito:
                            print(
                                f"  ✅ Auto-generado: {func.nombre} ({archivo_result.archivo})"
                            )
                            _generados += 1
                        else:
                            _omitidos += 1
                    except (SyntaxError, Exception) as e:
                        print(
                            f"  ⚠️ Error en {func.nombre} ({archivo_result.archivo}): {e}"
                        )
                        _omitidos += 1
        if _generados > 0:
            print(f"\n🔧 {_generados} CONTRATOS generados automáticamente")
        if _omitidos > 0:
            print(
                f"⏭️  {_omitidos} funciones omitidas (tienen docstring sin CONTRATO, usa --force en init)"
            )

    # Cargar registro RN para enriquecer reporte
    _rn_registro: dict[str, str] = {}
    try:
        from docpact.checker.rn_registry import cargar_registro

        _rn_registro = cargar_registro(args.path)
    except Exception:
        pass

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
                        # Enriquecer RN con descripcion desde REGISTRO.md
                        for rn_id, rn_desc in _rn_registro.items():
                            if rn_id in h.mensaje:
                                print(f"   📋 {rn_id}: {rn_desc}")
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


def _cmd_lint(args: argparse.Namespace) -> int:
    """Comando lint: análisis estático puro de CONTRATOS (sin pytest).

    Ideal para pre-commit hooks. Ejecuta todo excepto tests dinámicos.
    """
    from docpact.config import DocpactConfig
    from docpact.checker.orchestrator import check_proyecto

    config_path = args.config
    if not config_path:
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
    config.run_tests = False  # Lint = estático puro, sin pytest

    if args.strict or getattr(args, "fix", False):
        config.strict = True

    resultado = check_proyecto(args.path, config, diff_only=getattr(args, "diff", False))

    tf = resultado.total_funciones
    tc = resultado.funciones_con_contrato
    te = resultado.total_errores
    tw = resultado.total_warnings
    score = resultado.calcular_score()
    nivel = resultado.nivel
    # metricas_honestas puede no existir en versiones viejas del checker;
    # fallback defensivo para que el CLI no rompa al actualizar
    _honestas = getattr(resultado, "metricas_honestas", None)
    if callable(_honestas):
        metricas = _honestas()
    else:
        metricas = {
            "rns_fake": len(getattr(resultado, "rns_fake", [])),
            "rns_huerfanas": len(getattr(resultado, "rns_huerfanas", [])),
            "rns_placeholders": len(getattr(resultado, "rns_placeholders", [])),
            "funciones_sin_contrato": tf - tc,
            "funciones_totales": tf,
            "score_legacy": score,
        }

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

    # ── Métricas honestas: lo que SÍ predice calidad ──
    rns_fake = metricas["rns_fake"]
    rns_huerfanas = metricas["rns_huerfanas"]
    rns_placeholders = metricas["rns_placeholders"]
    sin_contrato = metricas["funciones_sin_contrato"]

    print(f"\n🩺 Métricas honestas (lo que SÍ predice calidad):")
    if rns_fake == 0 and rns_huerfanas == 0:
        print(f"   ✅ Cero mentiras y cero olvidos vs REGISTRO.md")
    else:
        if rns_fake > 0:
            print(f"   🚨 RNs fake (en CONTRATO pero NO en REGISTRO): {rns_fake}")
        if rns_huerfanas > 0:
            print(f"   📋 RNs huerfanas (en REGISTRO pero NO en CONTRATO): {rns_huerfanas}")
    if rns_placeholders > 0:
        print(f"   🚫 Placeholders excluidos (RN-XXX, RN-NO-APLICA, etc): {rns_placeholders}")
    if sin_contrato > 0:
        print(f"   ❌ Funciones públicas sin CONTRATO: {sin_contrato}")

    # ── Score legacy: deprecado, solo si el usuario lo pide ──
    if getattr(args, "show_legacy_score", False):
        print(f"\n   [score legacy DEPRECADO: {score}/100 — {nivel}]")

    # ── Falla por métricas honestas (gating) ──
    max_fake = getattr(args, "max_rns_fake", 0)
    if rns_fake > max_fake:
        print(f"\n❌ {rns_fake} RNs fake superan el máximo permitido ({max_fake})")
        return 1
    max_huerfanas = getattr(args, "max_rns_huerfanas", None)
    if max_huerfanas is not None and rns_huerfanas > max_huerfanas:
        print(f"\n❌ {rns_huerfanas} RNs huerfanas superan el máximo permitido ({max_huerfanas})")
        return 1

    # ── Falla por score legacy (compat) ──
    min_score = getattr(args, "min_score", 0)
    if min_score and score < min_score:
        print(f"\n❌ Score legacy {score} menor al mínimo requerido ({min_score})")
        print(f"   ADVERTENCIA: --min-score usa el score DEPRECADO. Migrar a --max-rns-fake.")
        return 1

    # Auto-fix si --fix
    if getattr(args, "fix", False):
        from docpact.cli.init import init_function
        _generados = 0
        for archivo_result in resultado.archivos:
            for func in archivo_result.funciones:
                if not func.tiene_contrato:
                    try:
                        exito, _ = init_function(
                            Path(archivo_result.archivo), func.nombre, safe=True
                        )
                        if exito:
                            print(f"  ✅ Auto-generado: {func.nombre} ({archivo_result.archivo})")
                            _generados += 1
                    except Exception:
                        pass
        if _generados > 0:
            print(f"\n🔧 {_generados} CONTRATOS generados automáticamente")

    # Mostrar errores
    if te > 0 or tw > 0:
        for archivo_result in resultado.archivos:
            for func in archivo_result.funciones:
                for h in func.hallazgos:
                    icono = "❌" if h.tipo == "error" else "⚠️"
                    loc = f"{archivo_result.archivo}::{h.funcion}:{h.linea}"
                    print(f"\n{icono} {loc}")
                    print(f"   {h.mensaje}")
                    if h.sugerencia:
                        print(f"   💡 {h.sugerencia}")

    if te > 0:
        return 1
    if config.strict and tf - tc > 0:
        return 1
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
    """Comando test: ejecuta tests de Reglas de Negocio con pytest.

    Solo busca funciones con CONTRATO que declaren rn: [RN-XXX] y ejecuta
    los tests correspondientes en tests/rn/test_rn_XXX.py.
    """
    from docpact.config import DocpactConfig
    from docpact.checker.orchestrator import check_proyecto

    config_path = args.config
    if not config_path:
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
    config.run_tests = True

    resultado = check_proyecto(args.path, config)

    # Solo mostrar resultados relevantes a tests RN
    test_errores = 0
    for archivo_result in resultado.archivos:
        for func in archivo_result.funciones:
            for h in func.hallazgos:
                if h.campo in ("rn", "rn_tests"):
                    test_errores += 1
                    icono = "❌" if h.tipo == "error" else "⚠️"
                    loc = f"{archivo_result.archivo}::{h.funcion}:{h.linea}"
                    print(f"{icono} {loc}")
                    print(f"   {h.mensaje}")
                    if h.sugerencia:
                        print(f"   💡 {h.sugerencia}")

    if test_errores == 0:
        print("✅ Todos los tests de Reglas de Negocio pasaron.")
        return 0
    else:
        print(f"\n❌ {test_errores} errores en tests de Reglas de Negocio.")
        return 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Comando doctor: autodiagnóstico del ecosistema."""
    from docpact.checker.doctor import ejecutar

    resultado = ejecutar(args.path, min_score=args.min_score)

    if args.json:
        import json

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


def _cmd_fix(args: argparse.Namespace) -> int:
    """Comando fix: auto-corrige warnings de firma en CONTRATOS."""
    from docpact.cli.fix import fix_file
    from pathlib import Path

    path = Path(args.path)
    if path.is_file():
        archivos = [path]
    elif path.is_dir():
        import os
        archivos = []
        for root, _dirs, files in os.walk(str(path)):
            for f in files:
                if f.endswith(".py"):
                    archivos.append(Path(root) / f)
    else:
        print(f"❌ No encontrado: {path}", file=sys.stderr)
        return 2

    total = 0
    for archivo in archivos:
        if _es_excluido(archivo):
            continue
        try:
            r = fix_file(archivo)
            if r:
                print(f"  ✅ {archivo.relative_to(path) if path.is_dir() else archivo.name}")
                total += r
        except Exception as e:
            print(f"  ⚠️ {archivo}: {e}", file=sys.stderr)

    if total:
        print(f"\n🔧 {total} archivos corregidos")
    else:
        print("✅ No se encontraron correcciones necesarias")
    return 0


def _cmd_index(args: argparse.Namespace) -> int:
    """Comando index: genera índice pre-calculado para el MCP server."""
    from docpact.index import generar_index, guardar_index
    import os

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
    print(f"   Tamaño: {os.path.getsize(path)/1024:.1f} KB")
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    """Comando mcp: inicia el MCP server para agentes."""
    from docpact.mcp_server import main as mcp_main
    import os

    # Si se pasa --project-root, inyectar como variable de entorno
    if args.project_root:
        os.environ["DOCPACT_PROJECT_ROOT"] = os.path.abspath(args.project_root)

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


if __name__ == "__main__":
    sys.exit(main())

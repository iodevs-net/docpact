"""Command handlers for docpact CLI.

Extracted from main.py to reduce file size and improve maintainability.
Each function handles one CLI subcommand.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("docpact.cli")


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
        _cargadas = set()
        try:
            from docpact.checker.rn_registry import cargar_registro

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


def cmd_check(args: argparse.Namespace) -> int:
    """Comando check: verifica CONTRATOS contra implementación real."""
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
    if args.strict or args.fix:
        config.strict = True
    if args.no_run_tests:
        config.run_tests = False
    if getattr(args, "no_runtime", False):
        config.run_runtime = False
        os.environ["DOCPACT_NO_RUNTIME"] = "1"

    resultado = check_proyecto(args.path, config, diff_only=args.diff)

    from docpact.mcp_server import diagnostico as _diag

    _d = _diag()
    if not _d["index_exists"]:
        logger.warning(
            "docpact MCP no esta listo: index no existe — corre `docpact index`"
        )
    elif not _d["docpact_in_PATH"]:
        logger.warning("docpact MCP no esta listo: binario no esta en PATH")

    tf = resultado.total_funciones
    tc = resultado.funciones_con_contrato
    te = resultado.total_errores
    tw = resultado.total_warnings
    score = resultado.calcular_score()
    nivel = resultado.nivel

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
    print(f"⚠️  {tw} warnings" if tw else "⚠️  0 warnings")
    print(f"❌ {te} errores" if te else "✅ 0 errores")

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
                arch_short = (
                    fake.archivo.rsplit("/", 1)[-1]
                    if "/" in fake.archivo
                    else fake.archivo
                )
                print(
                    f"      └─ {fake.rn_id} en {arch_short}:{fake.linea} ({fake.funcion})"
                )
            if len(resultado.rns_fake) > 5:
                print(
                    f"      └─ ... y {len(resultado.rns_fake) - 5} más (usar --fix o revisar manualmente)"
                )
        if rns_huerfanas > 0:
            print(
                f"   📋 RNs huerfanas (en REGISTRO pero NO en CONTRATO): {rns_huerfanas}"
            )
            for h in resultado.rns_huerfanas[:5]:
                print(f"      └─ {h.rn_id}: {h.descripcion[:80]}")
            if len(resultado.rns_huerfanas) > 5:
                print(f"      └─ ... y {len(resultado.rns_huerfanas) - 5} más")
    if rns_placeholders > 0:
        print(
            f"   🚫 Placeholders excluidos (RN-XXX, RN-NO-APLICA, etc): {rns_placeholders}"
        )
    if sin_contrato > 0:
        print(f"   ❌ Funciones públicas sin CONTRATO: {sin_contrato}")

    if args.show_legacy_score:
        print(f"\n   [score legacy DEPRECADO: {score}/100 — {nivel}]")

    if rns_fake > args.max_rns_fake:
        print(
            f"\n❌ {rns_fake} RNs fake superan el máximo permitido ({args.max_rns_fake})"
        )
        return 1
    if args.max_rns_huerfanas is not None and rns_huerfanas > args.max_rns_huerfanas:
        print(
            f"\n❌ {rns_huerfanas} RNs huerfanas superan el máximo permitido ({args.max_rns_huerfanas})"
        )
        return 1

    if args.min_score and score < args.min_score:
        print(f"\n❌ Score legacy {score} menor al mínimo requerido ({args.min_score})")
        print(
            f"   ADVERTENCIA: --min-score usa el score DEPRECADO. Migrar a --max-rns-fake."
        )
        return 1

    if args.fix:
        from docpact.cli.init import init_function

        _generados = 0
        _omitidos = 0
        for archivo_result in resultado.archivos:
            for func in archivo_result.funciones:
                if not func.tiene_contrato:
                    try:
                        exito, msg = init_function(
                            Path(archivo_result.archivo), func.nombre, safe=True
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

    _rn_registro: dict[str, str] = {}
    try:
        from docpact.checker.rn_registry import cargar_registro

        _rn_registro = cargar_registro(args.path)
    except Exception:
        pass

    if args.report or te > 0 or tw > 0:
        for archivo_result in resultado.archivos:
            for func in archivo_result.funciones:
                if func.hallazgos:
                    for h in func.hallazgos:
                        icono = "❌" if h.tipo == "error" else "⚠️"
                        loc = f"{archivo_result.archivo}::{h.funcion}:{h.linea}"
                        print(f"\n{icono} {loc}")
                        print(f"   {h.mensaje}")
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
        return 1
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    """Comando lint: análisis estático puro de CONTRATOS (sin pytest)."""
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
    config.run_tests = False

    if args.strict or getattr(args, "fix", False):
        config.strict = True

    resultado = check_proyecto(
        args.path, config, diff_only=getattr(args, "diff", False)
    )

    tf = resultado.total_funciones
    tc = resultado.funciones_con_contrato
    te = resultado.total_errores
    tw = resultado.total_warnings
    score = resultado.calcular_score()
    nivel = resultado.nivel

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
    print(f"⚠️  {tw} warnings" if tw else "⚠️  0 warnings")
    print(f"❌ {te} errores" if te else "✅ 0 errores")

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
            print(
                f"   📋 RNs huerfanas (en REGISTRO pero NO en CONTRATO): {rns_huerfanas}"
            )
    if rns_placeholders > 0:
        print(
            f"   🚫 Placeholders excluidos (RN-XXX, RN-NO-APLICA, etc): {rns_placeholders}"
        )
    if sin_contrato > 0:
        print(f"   ❌ Funciones públicas sin CONTRATO: {sin_contrato}")

    if getattr(args, "show_legacy_score", False):
        print(f"\n   [score legacy DEPRECADO: {score}/100 — {nivel}]")

    max_fake = getattr(args, "max_rns_fake", 0)
    if rns_fake > max_fake:
        print(f"\n❌ {rns_fake} RNs fake superan el máximo permitido ({max_fake})")
        return 1
    max_huerfanas = getattr(args, "max_rns_huerfanas", None)
    if max_huerfanas is not None and rns_huerfanas > max_huerfanas:
        print(
            f"\n❌ {rns_huerfanas} RNs huerfanas superan el máximo permitido ({max_huerfanas})"
        )
        return 1

    min_score = getattr(args, "min_score", 0)
    if min_score and score < min_score:
        print(f"\n❌ Score legacy {score} menor al mínimo requerido ({min_score})")
        print(
            f"   ADVERTENCIA: --min-score usa el score DEPRECADO. Migrar a --max-rns-fake."
        )
        return 1

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
                            print(
                                f"  ✅ Auto-generado: {func.nombre} ({archivo_result.archivo})"
                            )
                            _generados += 1
                    except Exception:
                        pass
        if _generados > 0:
            print(f"\n🔧 {_generados} CONTRATOS generados automáticamente")

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


def cmd_test(args: argparse.Namespace) -> int:
    """Comando test: ejecuta tests de Reglas de Negocio con pytest."""
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


def cmd_fix(args: argparse.Namespace) -> int:
    """Comando fix: auto-corrige warnings de firma en CONTRATOS."""
    from docpact.cli.fix import fix_file

    path = Path(args.path)
    if path.is_file():
        archivos = [path]
    elif path.is_dir():
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
                print(
                    f"  ✅ {archivo.relative_to(path) if path.is_dir() else archivo.name}"
                )
                total += r
        except Exception as e:
            print(f"  ⚠️ {archivo}: {e}", file=sys.stderr)

    if total:
        print(f"\n🔧 {total} archivos corregidos")
    else:
        print("✅ No se encontraron correcciones necesarias")
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


def cmd_validate(args: argparse.Namespace) -> int:
    """Comando validate: validación rápida para pre-commit hook."""
    import subprocess
    import re
    import ast

    files = args.files
    if not files and args.staged:
        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            files = [f for f in result.stdout.strip().split("\n") if f.endswith(".py")]
        except Exception:
            print("⚠️  No se pudieron obtener archivos staged", file=sys.stderr)
            return 1

    if not files:
        print("✅ No hay archivos Python para validar")
        return 0

    from docpact.index import cargar_index
    from docpact.config import DocpactConfig
    from docpact.checker.marker_honesty import (
        check_marker_honesty,
        check_marcador_concentrado,
    )

    project_root = os.path.abspath(".")
    index = cargar_index(project_root)
    if index is None:
        print("⚠️  Índice no encontrado. Ejecuta: docpact index")
        return 0

    config = DocpactConfig.desde_toml(os.path.join(project_root, "docpact.toml"))

    errores = []
    warnings = []

    for filepath in files:
        if not os.path.exists(filepath):
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        rns_declaradas = re.findall(r"RN-[\w-]+", content)

        for rn_id in set(rns_declaradas):
            if rn_id.upper().startswith("RN-XXX") or "NO-APLICA" in rn_id.upper():
                continue

            rn_info = index["rns"].get(rn_id)
            if not rn_info:
                errores.append(
                    {
                        "archivo": filepath,
                        "rn": rn_id,
                        "mensaje": f"RN '{rn_id}' no existe en REGISTRO.md",
                    }
                )

        if not config.marker_honesty_enabled:
            continue

        try:
            tree = ast.parse(content, filename=filepath)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            docstring = ast.get_docstring(node, clean=False) or ""
            contrato_rns = re.findall(r"RN-[\w-]+", docstring)
            if not contrato_rns:
                continue

            honesty_errors = check_marker_honesty(
                node,
                contrato_rns,
                content,
                node.name,
                enabled=True,
            )
            for e in honesty_errors:
                msg = f"{filepath}:{e.linea}: {e.mensaje}"
                warnings.append({"archivo": filepath, "mensaje": msg})

            concentrado = check_marcador_concentrado(
                contrato_rns,
                node.name,
                enabled=True,
            )
            if concentrado is not None:
                msg = f"{filepath}: {concentrado.mensaje}"
                warnings.append({"archivo": filepath, "mensaje": msg})

    warnings = [w for w in warnings if not config.debe_suprimir(w["mensaje"])]

    if errores:
        print(f"❌ {len(errores)} errores críticos:")
        for e in errores:
            print(f"   {e['archivo']}: {e['mensaje']}")
        print("\n💡 Corrige estos errores antes de commitar.")
        print("   Para ver warnings: docpact check .")
        return 1

    if warnings:
        print(f"⚠️  {len(warnings)} advertencias de marker honesty:")
        for w in warnings[:10]:
            print(f"   {w['mensaje']}")
        if len(warnings) > 10:
            print(f"   ... y {len(warnings) - 10} más")
        print("\n💡 Markers # RN-XXX en líneas de delegación suelen ser falsos.")
        print("   Mueve el marker a la función que realmente implementa la regla")
        print("   o agrega la lógica de la regla en la línea marcada.")
        print("   Para ver todos: docpact check .")
        return 1

    print(f"✅ {len(files)} archivos validados OK")
    return 0


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


def cmd_config_suggest(args: argparse.Namespace) -> int:
    """Sugiere config TOML para RNs sin validador."""
    from docpact.api import extract_contratos
    from docpact.config_suggest import (
        contrato_desde_dict,
        sugerir_spec_para_contrato,
    )

    root = Path(args.project_root).resolve()
    if not root.exists():
        print(f"❌ project root no existe: {root}")
        return 1

    contratos = extract_contratos(root)
    sugerencias: list[dict] = []
    for c in contratos:
        contrato = contrato_desde_dict(c.get("contrato", {}))
        if not contrato.rn:
            continue
        sug = sugerir_spec_para_contrato(contrato)
        if sug["confidence"] >= args.min_confidence:
            sugerencias.append(sug)

    if getattr(args, "json", False):
        print(
            json.dumps(
                {"ok": True, "count": len(sugerencias), "sugerencias": sugerencias},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        if not sugerencias:
            print("OK — no se encontraron sugerencias aplicables")
            return 0
        print(f"📋 {len(sugerencias)} sugerencias de config:\n")
        for s in sugerencias:
            rn_id = s["bloque_toml"].split("\n")[0].split(".")[-1].rstrip("]")
            print(f"  {rn_id} → {s['tipo']} (confidence: {s['confidence']:.2f})")
        print("\n--- Bloques TOML sugeridos ---")
        for s in sugerencias:
            print(s["bloque_toml"])
        if not args.apply:
            print("💡 Pasá --apply para escribir a docpact.toml")

    if args.apply:
        from docpact.config import DocpactConfig

        config_path = root / "docpact.toml"
        bloques = "\n".join(s["bloque_toml"] for s in sugerencias)
        if config_path.exists():
            contenido = config_path.read_text()
            if "[docpact.rn_patrones]" not in contenido:
                contenido += "\n\n[docpact.rn_patrones]\n" + bloques
            else:
                contenido += "\n" + bloques
        else:
            contenido = "[docpact.rn_patrones]\n" + bloques
        config_path.write_text(contenido)
        print(f"\n✅ {len(sugerencias)} bloques escritos a {config_path}")

    return 0


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


def cmd_llm_judge(args: argparse.Namespace) -> int:
    """Evalua si un test verifica la regla usando un LLM."""
    from docpact.llm_judge import evaluar_test_con_llm

    test_path = Path(args.test_file)
    if not test_path.exists():
        print(f"❌ test file no existe: {test_path}")
        return 1

    test_code = test_path.read_text()
    score = evaluar_test_con_llm(
        rn_descripcion=args.rn_descripcion,
        test_code=test_code,
    )

    if score is None:
        print(
            "❌ no se pudo obtener evaluacion del LLM (api key, error HTTP, o respuesta no parseable)"
        )
        return 1

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "verifica": score.verifica,
                    "confidence": score.confidence,
                    "razon": score.razon,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        verdict = "✅ VERIFICA" if score.verifica else "❌ NO VERIFICA"
        print(f"{verdict} (confidence: {score.confidence:.2f})")
        print(f"Razon: {score.razon}")

    return 0 if score.verifica else 1


def cmd_test_quality(args: argparse.Namespace) -> int:
    """Detecta tests placeholder en tests/rn/."""
    from docpact.checker.rn_test_checker import check_rn_test_quality

    root = Path(args.project_root).resolve()
    issues = check_rn_test_quality(root)
    if getattr(args, "json", False):
        out = [{"tipo": i.tipo, "mensaje": i.mensaje, "linea": i.linea} for i in issues]
        print(
            json.dumps(
                {"ok": not issues, "count": len(issues), "issues": out},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        if not issues:
            print("OK — todos los tests en tests/rn/ son reales")
        else:
            print(f"Encontrados {len(issues)} tests placeholder:\n")
            for i in issues:
                print(f"  {i.mensaje}")
    return 1 if issues else 0


def cmd_run(args: argparse.Namespace) -> int:
    """Comando run: verificación dinámica en sandbox."""
    from docpact.runner import main as runner_main

    argv = [args.path, "--tests", args.tests]
    if getattr(args, "max_iterations", None):
        argv += ["--max-iterations", str(args.max_iterations)]
    if getattr(args, "build", False):
        argv += ["--build"]
    return runner_main(argv)


def cmd_init(args: argparse.Namespace) -> int:
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


def cmd_verify_rns(args: argparse.Namespace) -> int:
    """Comando verify-rn: verifica que patrones RN existan en código fuente."""
    from docpact.checker.rn_verifier import verify_all_rns

    project_root = Path(args.project_root).resolve()
    results = verify_all_rns(project_root)

    if getattr(args, "json", False):
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        _print_rn_results(results)

    failed = sum(1 for r in results if r["status"] == "FAIL")
    return 1 if failed else 0


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


def _print_rn_results(results: list) -> None:
    """Imprime resultados de verify-rn en formato legible."""
    for r in results:
        icono = "✅" if r["status"] == "PASS" else "❌" if r["status"] == "FAIL" else "ℹ️"
        print(f"{icono} {r['rn_id']}: {r['mensaje']}")

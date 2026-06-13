"""Verification commands: check, lint, validate, verify-rn."""

from __future__ import annotations

import argparse
import ast
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from ._common import (
    _es_excluido,
    _print_contrato_texto,
    add_config_arg,
    add_diff_flag,
    add_fix_flag,
    add_json_flag,
    add_max_rns_args,
    add_min_score_arg,
    add_path_arg,
    add_project_root_arg,
    add_show_legacy_score_flag,
    add_staged_flag,
    add_strict_flag,
)

logger = logging.getLogger("docpact.cli")


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


def _print_rn_results(results: list) -> None:
    """Imprime resultados de verify-rn en formato legible."""
    for r in results:
        icono = "✅" if r["status"] == "PASS" else "❌" if r["status"] == "FAIL" else "⚠️"
        desc = r.get("description", r.get("mensaje", ""))
        print(f"{icono} {r['rn_id']}: {desc}")


def register(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register check, lint, validate, and verify-rn subcommands."""
    # ── check ──
    check_parser = subparsers.add_parser(
        "check",
        help=(
            "Verifica CONTRATOS: side_effects, dependencias y RNs fake. "
            "Ejecutar después de escribir o modificar código. "
            "Para arreglar errores: agregar CONTRATO faltante o corregir side_effects en el docstring"
        ),
    )
    add_path_arg(check_parser, help_text="Archivo o directorio a verificar")
    add_strict_flag(check_parser)
    add_config_arg(check_parser)
    add_diff_flag(check_parser)
    check_parser.add_argument(
        "--report", action="store_true", help="Reporte detallado con sugerencias"
    )
    add_fix_flag(check_parser)
    add_min_score_arg(check_parser)
    add_max_rns_args(check_parser)
    add_show_legacy_score_flag(check_parser)
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
    check_parser.set_defaults(func=cmd_check)

    # ── lint ──
    lint_parser = subparsers.add_parser(
        "lint",
        help=(
            "Static-only CONTRATO analysis (no pytest). "
            "Checks docstring syntax, side_effects declarations, and RN fake detection. "
            "Faster than 'check' — ideal for pre-commit hooks"
        ),
    )
    add_path_arg(lint_parser, help_text="Archivo o directorio a verificar")
    add_strict_flag(lint_parser)
    add_config_arg(lint_parser)
    add_diff_flag(lint_parser)
    add_min_score_arg(lint_parser)
    add_max_rns_args(lint_parser)
    add_show_legacy_score_flag(lint_parser)
    add_fix_flag(lint_parser)
    lint_parser.set_defaults(func=cmd_lint)

    # ── validate ──
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
    add_staged_flag(validate_parser)
    validate_parser.set_defaults(func=cmd_validate)

    # ── verify-rn ──
    verify_rn_parser = subparsers.add_parser(
        "verify-rn",
        help=(
            "Verifica que patrones de RNs (Reglas de Negocio) existan en código fuente. "
            "Chequea existencia de patrones y orden de validación. "
            "Ejecutar antes de cada commit para asegurar que reglas declaradas estén implementadas"
        ),
    )
    add_project_root_arg(verify_rn_parser)
    add_json_flag(verify_rn_parser)
    verify_rn_parser.set_defaults(func=cmd_verify_rns)

    return check_parser

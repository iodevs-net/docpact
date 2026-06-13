"""Testing commands: test, test-quality, llm-judge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


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

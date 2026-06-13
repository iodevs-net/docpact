"""Code generation commands: fix, init, config-suggest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from docpact.cli.commands._common import _es_excluido


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

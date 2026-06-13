"""Briefing de reglas de negocio para agentes AI.

Genera un resumen ejecutivo del estado de las reglas de negocio
del proyecto, diseñado para que un agente lo lea ANTES de empezar
a codear y entienda qué debe respetar.

El briefing se almacena en .docpact/briefing.md y se auto-actualiza
cuando el código cambia.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from docpact.config import DocpactConfig


BRIEFING_DIR = ".docpact"
BRIEFING_FILE = "briefing.md"
BRIEFING_META = "briefing.meta.json"


def _calcular_fingerprint(project_root: Path) -> str:
    """Calcula un fingerprint del estado actual del proyecto.

    Basado en: archivos Python modificados + docpact.toml + REGISTRO.md
    """
    parts: list[str] = []

    # Archivos Python
    for py_file in sorted(project_root.rglob("*.py")):
        if any(ex in py_file.parts for ex in ("__pycache__", ".venv", "venv", ".git", "node_modules")):
            continue
        try:
            stat = py_file.stat()
            parts.append(f"{py_file.relative_to(project_root)}:{stat.st_mtime_ns}")
        except (OSError, ValueError):
            continue

    # Config
    toml_path = project_root / "docpact.toml"
    if toml_path.exists():
        try:
            parts.append(f"docpact.toml:{toml_path.stat().st_mtime_ns}")
        except OSError:
            pass

    # REGISTRO
    registro_path = project_root / "docs" / "reglas-del-negocio" / "REGISTRO.md"
    if registro_path.exists():
        try:
            parts.append(f"REGISTRO.md:{registro_path.stat().st_mtime_ns}")
        except OSError:
            pass

    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _extraer_resumen(project_root: Path, config: DocpactConfig) -> dict[str, Any]:
    """Extrae un resumen del estado actual del proyecto."""
    from docpact.checker.orchestrator import check_proyecto
    from docpact.parser.extractor import extraer_docstrings
    from docpact.parser.lexer import tokenizar
    from docpact.parser.parser import parsear
    from docpact.parser.ts_parser import extraer_contratos_ts

    resultado = check_proyecto(str(project_root), config)

    # Estadísticas básicas
    total_funciones = resultado.total_funciones
    con_contrato = resultado.funciones_con_contrato
    sin_contrato = total_funciones - con_contrato
    errores = resultado.total_errores
    warnings = resultado.total_warnings

    # RNs declaradas
    rns_declaradas: set[str] = set()
    rns_fake = resultado.rns_fake
    rns_huerfanas = resultado.rns_huerfanas

    for archivo in resultado.archivos:
        for func in archivo.funciones:
            if func.contrato and func.contrato.rn:
                for rn in func.contrato.rn:
                    rns_declaradas.add(rn.id)

    # Funciones con side effects críticos
    side_effects_criticos: list[dict] = []
    for archivo in resultado.archivos:
        for func in archivo.funciones:
            if func.contrato and func.contrato.side_effects:
                for se in func.contrato.side_effects:
                    if any(p in se.descripcion.lower() for p in ("db", "disk", "email", "write", "delete", "create")):
                        side_effects_criticos.append({
                            "funcion": func.nombre,
                            "archivo": str(archivo.archivo),
                            "efecto": se.descripcion,
                        })

    # Funciones frágiles (sin contrato o con errores)
    fragiles: list[dict] = []
    for archivo in resultado.archivos:
        for func in archivo.funciones:
            if not func.tiene_contrato or func.errores:
                fragiles.append({
                    "funcion": func.nombre,
                    "archivo": str(archivo.archivo),
                    "razon": "sin contrato" if not func.tiene_contrato else f"{len(func.errores)} errores",
                })

    return {
        "total_funciones": total_funciones,
        "con_contrato": con_contrato,
        "sin_contrato": sin_contrato,
        "errores": errores,
        "warnings": warnings,
        "rns_declaradas": sorted(rns_declaradas),
        "rns_fake": len(rns_fake),
        "rns_huerfanas": len(rns_huerfanas),
        "side_effects_criticos": side_effects_criticos,
        "fragiles": fragiles,
    }


def _generar_markdown(resumen: dict[str, Any], project_root: Path) -> str:
    """Genera el briefing en formato Markdown."""
    lines: list[str] = []
    lines.append("# Briefing de Reglas de Negocio")
    lines.append("")
    lines.append(f"_Generado automáticamente por docpact. No editar manualmente._")
    lines.append("")

    # Resumen ejecutivo
    lines.append("## Resumen Ejecutivo")
    lines.append("")
    lines.append(f"- **Funciones públicas**: {resumen['total_funciones']}")
    lines.append(f"- **Con CONTRATO completo**: {resumen['con_contrato']}")
    lines.append(f"- **Sin CONTRATO**: {resumen['sin_contrato']}")
    lines.append(f"- **Errores**: {resumen['errores']}")
    lines.append(f"- **Warnings**: {resumen['warnings']}")
    lines.append("")

    # RNs
    lines.append("## Reglas de Negocio Declaradas")
    lines.append("")
    if resumen["rns_declaradas"]:
        for rn in resumen["rns_declaradas"]:
            lines.append(f"- {rn}")
    else:
        lines.append("_No hay RNs declaradas en CONTRATOs._")
    lines.append("")

    if resumen["rns_fake"] > 0:
        lines.append(f"⚠️ **{resumen['rns_fake']} RNs fake** (declaradas en CONTRATO pero no existen en REGISTRO)")
        lines.append("")

    if resumen["rns_huerfanas"] > 0:
        lines.append(f"⚠️ **{resumen['rns_huerfanas']} RNs huérfanas** (en REGISTRO pero sin CONTRATO asociado)")
        lines.append("")

    # Side effects críticos
    lines.append("## Side Effects Críticos")
    lines.append("")
    lines.append("_Estas funciones tienen efectos sobre DB, disco, email u otros sistemas externos._")
    lines.append("")
    if resumen["side_effects_criticos"]:
        for se in resumen["side_effects_criticos"]:
            lines.append(f"- **{se['funcion']}** (`{se['archivo']}`): {se['efecto']}")
    else:
        lines.append("_No se detectaron side effects críticos._")
    lines.append("")

    # Áreas frágiles
    lines.append("## Áreas de Riesgo")
    lines.append("")
    lines.append("_Funciones sin CONTRATO o con errores detectados._")
    lines.append("")
    if resumen["fragiles"]:
        for f in resumen["fragiles"][:20]:  # Limitar a 20
            lines.append(f"- **{f['funcion']}** (`{f['archivo']}`): {f['razon']}")
        if len(resumen["fragiles"]) > 20:
            lines.append(f"- _... y {len(resumen['fragiles']) - 20} más_")
    else:
        lines.append("_Todas las funciones tienen CONTRATO válido._")
    lines.append("")

    # Instrucciones para agentes
    lines.append("## Instrucciones para Agentes")
    lines.append("")
    lines.append("Al modificar código en este proyecto, respetá estas reglas:")
    lines.append("")
    lines.append("1. **No modifiques side effects** declarados en CONTRATOs sin actualizar el docstring")
    lines.append("2. **Las RNs declaradas** deben mantenerse en el código tras tus cambios")
    lines.append("3. **Funciones sin CONTRATO** son candidatas a romperse — verificá antes de modificar")
    lines.append("4. **Ejecutá `docpact check .** después de tus cambios para validar")
    lines.append("")

    return "\n".join(lines)


def generar_briefing(
    project_root: str | Path,
    force: bool = False,
) -> tuple[Path, bool]:
    """Genera o actualiza el briefing del proyecto.

    Args:
        project_root: Raíz del proyecto
        force: Forzar regeneración aunque no haya cambios

    Returns:
        Tupla (path_al_briefing, fue_regenerado)
    """
    root = Path(project_root).resolve()
    briefing_dir = root / BRIEFING_DIR
    briefing_path = briefing_dir / BRIEFING_FILE
    meta_path = briefing_dir / BRIEFING_META

    # Calcular fingerprint actual
    fingerprint_actual = _calcular_fingerprint(root)

    # Verificar si existe y está actualizado
    if not force and briefing_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("fingerprint") == fingerprint_actual:
                return briefing_path, False
        except (json.JSONDecodeError, OSError):
            pass

    # Generar briefing
    config = DocpactConfig()
    resumen = _extraer_resumen(root, config)
    markdown = _generar_markdown(resumen, root)

    # Guardar
    briefing_dir.mkdir(parents=True, exist_ok=True)
    briefing_path.write_text(markdown, encoding="utf-8")

    # Guardar metadata
    meta = {
        "fingerprint": fingerprint_actual,
        "generated_at": time.time(),
        "project_root": str(root),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return briefing_path, True


def leer_briefing(project_root: str | Path) -> str | None:
    """Lee el briefing existente sin regenerarlo.

    Returns:
        Contenido del briefing o None si no existe.
    """
    root = Path(project_root).resolve()
    briefing_path = root / BRIEFING_DIR / BRIEFING_FILE

    if briefing_path.exists():
        return briefing_path.read_text(encoding="utf-8")
    return None


def briefing_necesita_update(project_root: str | Path) -> bool:
    """Verifica si el briefing necesita actualización.

    Returns:
        True si el briefing no existe o está desactualizado.
    """
    root = Path(project_root).resolve()
    briefing_path = root / BRIEFING_DIR / BRIEFING_FILE
    meta_path = root / BRIEFING_DIR / BRIEFING_META

    if not briefing_path.exists():
        return True

    if not meta_path.exists():
        return True

    try:
        fingerprint_actual = _calcular_fingerprint(root)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("fingerprint") != fingerprint_actual
    except (json.JSONDecodeError, OSError):
        return True

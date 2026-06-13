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
from collections import defaultdict
from pathlib import Path
from typing import Any

from docpact.config import DocpactConfig


BRIEFING_DIR = ".docpact"
BRIEFING_FILE = "briefing.md"
BRIEFING_META = "briefing.meta.json"

# Exclusiones para filtrar tests y código no-productivo
_TEST_DIRS = {"tests", "test", "test_*", "tests_*"}
_TEST_PATTERNS = {"test_", "conftest", "fixtures", "factories"}


def _es_codigo_produccion(path_str: str) -> bool:
    """Determina si un archivo es código de producción (no test)."""
    path_lower = path_str.lower()
    for patron in _TEST_PATTERNS:
        if patron in path_lower:
            return False
    for dir_test in _TEST_DIRS:
        if f"/{dir_test}/" in path_lower or f"\\{dir_test}\\" in path_lower:
            return False
    return True


def _calcular_fingerprint(project_root: Path) -> str:
    """Calcula un fingerprint del estado actual del proyecto."""
    parts: list[str] = []

    for py_file in sorted(project_root.rglob("*.py")):
        if any(ex in py_file.parts for ex in ("__pycache__", ".venv", "venv", ".git", "node_modules")):
            continue
        try:
            stat = py_file.stat()
            parts.append(f"{py_file.relative_to(project_root)}:{stat.st_mtime_ns}")
        except (OSError, ValueError):
            continue

    for name in ("docpact.toml",):
        toml_path = project_root / name
        if toml_path.exists():
            try:
                parts.append(f"{name}:{toml_path.stat().st_mtime_ns}")
            except OSError:
                pass

    registro_path = project_root / "docs" / "reglas-del-negocio" / "REGISTRO.md"
    if registro_path.exists():
        try:
            parts.append(f"REGISTRO.md:{registro_path.stat().st_mtime_ns}")
        except OSError:
            pass

    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _extraer_rns_desde_codigo(resultado: Any) -> dict[str, list[str]]:
    """Extrae RNs y sus ubicaciones desde el resultado del checker."""
    rns: dict[str, list[str]] = defaultdict(list)
    for archivo in resultado.archivos:
        for func in archivo.funciones:
            if func.contrato and func.contrato.rn:
                for rn in func.contrato.rn:
                    archivo_corto = str(archivo.archivo).split("/")[-1]
                    rns[rn.id].append(f"{func.nombre} ({archivo_corto})")
    return dict(rns)


def _agrupar_side_effects(resultado: Any) -> dict[str, list[dict]]:
    """Agrupa side effects por dominio, excluyendo tests."""
    por_dominio: dict[str, list[dict]] = defaultdict(list)

    for archivo in resultado.archivos:
        if not _es_codigo_produccion(str(archivo.archivo)):
            continue
        for func in archivo.funciones:
            if func.contrato and func.contrato.side_effects:
                for se in func.contrato.side_effects:
                    dominio = str(archivo.archivo).split("/")[-2] if "/" in str(archivo.archivo) else "root"
                    por_dominio[dominio].append({
                        "funcion": func.nombre,
                        "archivo": str(archivo.archivo).split("/")[-1],
                        "efecto": se.descripcion,
                    })

    return dict(por_dominio)


def _contar_fragiles_por_modulo(resultado: Any) -> dict[str, int]:
    """Cuenta funciones sin contrato por módulo, excluyendo tests."""
    conteo: dict[str, int] = defaultdict(int)

    for archivo in resultado.archivos:
        if not _es_codigo_produccion(str(archivo.archivo)):
            continue
        for func in archivo.funciones:
            if not func.tiene_contrato or func.errores:
                modulo = str(archivo.archivo).split("/")[-2] if "/" in str(archivo.archivo) else "root"
                conteo[modulo] += 1

    return dict(sorted(conteo.items(), key=lambda x: x[1], reverse=True))


def _extraer_resumen(project_root: Path, config: DocpactConfig) -> dict[str, Any]:
    """Extrae un resumen conciso del estado del proyecto."""
    from docpact.checker.orchestrator import check_proyecto

    resultado = check_proyecto(str(project_root), config)

    # RNs declaradas con ubicaciones
    rns_con_ubicacion = _extraer_rns_desde_codigo(resultado)

    # Side effects agrupados por dominio (solo producción)
    side_effects = _agrupar_side_effects(resultado)

    # Funciones frágiles por módulo (solo producción)
    fragiles = _contar_fragiles_por_modulo(resultado)

    # Conteos
    total_produccion = sum(
        1 for a in resultado.archivos
        if _es_codigo_produccion(str(a.archivo))
        for f in a.funciones
    )
    con_contrato_produccion = sum(
        1 for a in resultado.archivos
        if _es_codigo_produccion(str(a.archivo))
        for f in a.funciones if f.tiene_contrato
    )

    return {
        "total_produccion": total_produccion,
        "con_contrato_produccion": con_contrato_produccion,
        "sin_contrato_produccion": total_produccion - con_contrato_produccion,
        "total_tests": resultado.total_funciones - total_produccion,
        "errores": resultado.total_errores,
        "warnings": resultado.total_warnings,
        "rns_declaradas": len(rns_con_ubicacion),
        "rns_con_ubicacion": rns_con_ubicacion,
        "rns_fake": len(resultado.rns_fake),
        "rns_huerfanas": len(resultado.rns_huerfanas),
        "side_effects_por_dominio": side_effects,
        "fragiles_por_modulo": fragiles,
    }


def _generar_markdown(resumen: dict[str, Any]) -> str:
    """Genera el briefing en formato Markdown conciso."""
    lines: list[str] = []

    # Header
    lines.append("# Briefing de Reglas de Negocio")
    lines.append("")
    lines.append("_Generado automaticamente por docpact. No editar manualmente._")
    lines.append("")

    # Resumen ejecutivo
    lines.append("## Estado del Proyecto")
    lines.append("")
    tp = resumen["total_produccion"]
    cp = resumen["con_contrato_produccion"]
    sp = resumen["sin_contrato_produccion"]
    pct = (cp / tp * 100) if tp > 0 else 0
    lines.append(f"- **{tp}** funciones en produccion ({cp} con contrato, {sp} sin)")
    lines.append(f"- **{pct:.0f}%** de cobertura de contratos")
    lines.append(f"- **{resumen['errores']}** errores, **{resumen['warnings']}** warnings")
    lines.append(f"- **{resumen['total_tests']}** funciones de test")
    lines.append("")

    # RNs
    lines.append("## Reglas de Negocio Activas")
    lines.append("")
    if resumen["rns_con_ubicacion"]:
        for rn_id, ubicaciones in sorted(resumen["rns_con_ubicacion"].items()):
            lines.append(f"**{rn_id}**")
            for u in ubicaciones[:3]:  # Max 3 por RN
                lines.append(f"  - {u}")
            if len(ubicaciones) > 3:
                lines.append(f"  - _... y {len(ubicaciones) - 3} mas_")
    else:
        lines.append("_No hay RNs declaradas en CONTRATOs._")
    lines.append("")

    if resumen["rns_fake"] > 0:
        lines.append(f"ALERTA: **{resumen['rns_fake']} RNs fake** (en CONTRATO pero no en REGISTRO)")
    if resumen["rns_huerfanas"] > 0:
        lines.append(f"ALERTA: **{resumen['rns_huerfanas']} RNs huerfanas** (en REGISTRO sin CONTRATO)")
    if resumen["rns_fake"] > 0 or resumen["rns_huerfanas"] > 0:
        lines.append("")

    # Side effects por dominio
    lines.append("## Efectos Colaterales por Dominio")
    lines.append("")
    lines.append("_Solo codigo de produccion. Estas funciones tienen efectos externos._")
    lines.append("")
    if resumen["side_effects_por_dominio"]:
        for dominio, efectos in sorted(resumen["side_effects_por_dominio"].items()):
            # Deduplicar por función
            vistos = set()
            efectos_unicos = []
            for e in efectos:
                if e["funcion"] not in vistos:
                    vistos.add(e["funcion"])
                    efectos_unicos.append(e)

            lines.append(f"### {dominio}")
            for e in efectos_unicos[:5]:  # Max 5 por dominio
                lines.append(f"- `{e['funcion']}`: {e['efecto']}")
            if len(efectos_unicos) > 5:
                lines.append(f"- _... y {len(efectos_unicos) - 5} mas_")
            lines.append("")
    else:
        lines.append("_No se detectaron efectos colaterales en produccion._")
        lines.append("")

    # Areas fragiles
    lines.append("## Zonas de Riesgo")
    lines.append("")
    lines.append("_Modulos con funciones sin contrato o con errores._")
    lines.append("")
    if resumen["fragiles_por_modulo"]:
        for modulo, cantidad in list(resumen["fragiles_por_modulo"].items())[:10]:
            lines.append(f"- **{modulo}**: {cantidad} funciones afectadas")
        if len(resumen["fragiles_por_modulo"]) > 10:
            lines.append(f"- _... y {len(resumen['fragiles_por_modulo']) - 10} modulos mas_")
    else:
        lines.append("_Todas las funciones tienen contrato valido._")
    lines.append("")

    # Instrucciones
    lines.append("## Reglas para Agentes")
    lines.append("")
    lines.append("1. **Lee las RNs antes de modificar** — cada RN tiene ubicacion arriba")
    lines.append("2. **No modifiques side effects** sin actualizar el docstring del CONTRATO")
    lines.append("3. **Evita modificar zonas de riesgo** sin entender el contexto completo")
    lines.append("4. **Valida con `docpact check .** despues de tus cambios")
    lines.append("")

    return "\n".join(lines)


def generar_briefing(
    project_root: str | Path,
    force: bool = False,
) -> tuple[Path, bool]:
    """Genera o actualiza el briefing del proyecto.

    Returns:
        Tupla (path_al_briefing, fue_regenerado)
    """
    root = Path(project_root).resolve()
    briefing_dir = root / BRIEFING_DIR
    briefing_path = briefing_dir / BRIEFING_FILE
    meta_path = briefing_dir / BRIEFING_META

    fingerprint_actual = _calcular_fingerprint(root)

    # Verificar cache
    if not force and briefing_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("fingerprint") == fingerprint_actual:
                return briefing_path, False
        except (json.JSONDecodeError, OSError):
            pass

    # Generar
    config = DocpactConfig()
    resumen = _extraer_resumen(root, config)
    markdown = _generar_markdown(resumen)

    # Guardar
    briefing_dir.mkdir(parents=True, exist_ok=True)
    briefing_path.write_text(markdown, encoding="utf-8")
    meta_path.write_text(json.dumps({
        "fingerprint": fingerprint_actual,
        "generated_at": time.time(),
        "project_root": str(root),
    }, indent=2), encoding="utf-8")

    return briefing_path, True


def leer_briefing(project_root: str | Path) -> str | None:
    """Lee el briefing existente sin regenerarlo."""
    briefing_path = Path(project_root).resolve() / BRIEFING_DIR / BRIEFING_FILE
    if briefing_path.exists():
        return briefing_path.read_text(encoding="utf-8")
    return None


def briefing_necesita_update(project_root: str | Path) -> bool:
    """Verifica si el briefing necesita actualizacion."""
    root = Path(project_root).resolve()
    briefing_path = root / BRIEFING_DIR / BRIEFING_FILE
    meta_path = root / BRIEFING_DIR / BRIEFING_META

    if not briefing_path.exists() or not meta_path.exists():
        return True

    try:
        fingerprint_actual = _calcular_fingerprint(root)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("fingerprint") != fingerprint_actual
    except (json.JSONDecodeError, OSError):
        return True

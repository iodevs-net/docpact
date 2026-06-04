"""docpact.config_suggest — sugiere config TOML para RNs sin validador.

Cierra el gap de los 144 warnings tipicos ("RN sin validador semantico
configurado en docpact.toml"). Analiza el CONTRATO de la funcion que
implementa la RN y propone el bloque [docpact.rn_patrones.RN-XXX] con
un type y spec razonables.

Heuristica (v1):
- tenant_safe    → rn menciona "tenant" o comportamiento usa "para_usuario"
- state_transition → input tiene "estado" o comportamiento menciona "transicion"
- no_import       → asume dice "delegado" o "no inline"
- required_groups → asume menciona "grupo" o "permiso"
- has_pattern     → fallback (chequeo basico de substring)

El output es una SUGERENCIA. El usuario debe revisarla antes de aplicar.
"""
from __future__ import annotations

import re
from typing import Any

from docpact.models.contrato import Contrato


# ──────────────────── inferir_tipo_validador ────────────────────


_PATTERNS = {
    "tenant_safe": [
        re.compile(r"\btenant\b", re.IGNORECASE),
        re.compile(r"para_usuario", re.IGNORECASE),
    ],
    "state_transition": [
        re.compile(r"\btransici[oó]n\b", re.IGNORECASE),
        re.compile(r"\bestado\b", re.IGNORECASE),
    ],
    "no_import": [
        re.compile(r"delegad[oa]", re.IGNORECASE),
        re.compile(r"no\s+inline", re.IGNORECASE),
        re.compile(r"\bcentralizad[oa]\b", re.IGNORECASE),
    ],
    "required_groups": [
        re.compile(r"\bgrupo\b", re.IGNORECASE),
        re.compile(r"\bpermiso\b", re.IGNORECASE),
        re.compile(r"solo\s+\w+\s+pueden", re.IGNORECASE),
    ],
}


def _campo_texto(c: Contrato) -> str:
    """Concatena los campos textuales del CONTRATO para buscar keywords."""
    partes: list[str] = []
    if c.comportamiento:
        partes.append(c.comportamiento)
    if c.asume:
        partes.append(c.asume)
    if c.produce:
        partes.append(c.produce)
    for rn in c.rn:
        partes.append(rn.id)
        partes.append(rn.descripcion)
    for d in c.dependencias:
        partes.append(d.ref)
    for k, v in c.input.items():
        partes.append(k)
        partes.append(v.tipo)
    return " ".join(partes)


def inferir_tipo_validador(c: Contrato) -> tuple[str, float]:
    """Infiere el tipo de validador semantico apropiado para un CONTRATO.

    Returns:
        (tipo, confidence) donde tipo es uno de los 5 validadores
        y confidence esta en [0, 1].
    """
    texto = _campo_texto(c)

    # Scoring: cada match suma puntos, mayor score gana
    scores: dict[str, int] = {tipo: 0 for tipo in _PATTERNS}
    for tipo, patterns in _PATTERNS.items():
        for p in patterns:
            if p.search(texto):
                scores[tipo] += 1

    # Tie-break por orden de prioridad (los mas especificos primero)
    prioridad = ["tenant_safe", "state_transition", "no_import", "required_groups"]
    mejor_tipo = "has_pattern"
    mejor_score = 0
    for tipo in prioridad:
        if scores[tipo] > mejor_score:
            mejor_score = scores[tipo]
            mejor_tipo = tipo

    # Confidence: cuantos patterns matchearon del tipo ganador
    if mejor_tipo == "has_pattern":
        return "has_pattern", 0.3
    max_patterns = len(_PATTERNS[mejor_tipo])
    confidence = min(0.95, 0.5 + (mejor_score / max_patterns) * 0.45)
    return mejor_tipo, confidence


# ──────────────────── generar_bloque_toml ────────────────────


_TOML_REQUIRED_FIELDS = {
    "tenant_safe": ["forbid"],
    "state_transition": ["from_estado", "to_estado", "matriz_attr", "modulo"],
    "no_import": ["forbid"],
    "required_groups": ["allowed"],  # o "forbidden"
    "has_pattern": ["pattern"],
}


def _render_value(v: Any) -> str:
    """Renderiza un valor Python como literal TOML."""
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        items = ", ".join(_render_value(x) for x in v)
        return f"[{items}]"
    return f'"{v}"'


def generar_bloque_toml(rn_id: str, tipo: str, spec: dict) -> str:
    """Genera el bloque TOML [docpact.rn_patrones.RN-XXX] = { type=..., ... }.

    Si el spec no tiene los campos requeridos para el tipo, agrega
    comentario "# REVISAR: falta ..." para que el usuario sepa qué completar.
    """
    lineas: list[str] = []
    lineas.append(f"[docpact.rn_patrones.{rn_id}]")
    lineas.append(f"type = \"{tipo}\"")

    # Spec ya viene con type incluido; lo saltamos en el render
    rendered = {k: v for k, v in spec.items() if k != "type"}
    for key, value in rendered.items():
        lineas.append(f"{key} = {_render_value(value)}")

    # Verificar campos requeridos
    requeridos = _TOML_REQUIRED_FIELDS.get(tipo, [])
    faltantes = [r for r in requeridos if r not in spec or not spec[r]]
    if faltantes:
        lineas.append(
            f"# REVISAR: faltan campos requeridos para '{tipo}': {', '.join(faltantes)}"
        )

    lineas.append("")  # newline final
    return "\n".join(lineas)


# ──────────────────── pipeline de sugerencia ────────────────────


def sugerir_spec_para_contrato(c: Contrato) -> dict:
    """Pipeline: infiere el tipo y genera un spec minimo razonable.

    Returns:
        dict con keys: tipo, confidence, spec, bloque_toml
    """
    tipo, confidence = inferir_tipo_validador(c)

    # Spec minimo segun tipo
    spec: dict = {"type": tipo}
    if tipo == "tenant_safe":
        spec["forbid"] = ["unfiltered_objects", ".objects.all", ".objects.filter"]
    elif tipo == "state_transition":
        # El usuario tiene que completar estos manualmente
        spec["from_estado"] = ""
        spec["to_estado"] = ""
        spec["matriz_attr"] = ""
        spec["modulo"] = ""
    elif tipo == "no_import":
        spec["forbid"] = []  # usuario completa
    elif tipo == "required_groups":
        spec["allowed"] = []  # usuario completa
    elif tipo == "has_pattern":
        spec["pattern"] = ""  # usuario completa

    rn_id = c.rn[0].id if c.rn else "RN-UNKNOWN"
    bloque = generar_bloque_toml(rn_id, tipo, spec)
    return {
        "tipo": tipo,
        "confidence": confidence,
        "spec": spec,
        "bloque_toml": bloque,
    }

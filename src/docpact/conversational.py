"""docpact.conversational — interfaz conversacional para docpact.

Mejora #9 de docpact. Permite a un usuario no-dev hacer preguntas
en lenguaje natural sobre las reglas de negocio y el codigo.

Las queries se mapean a una intencion + tipo de validador. La respuesta
combina el conocimiento de docpact con sugerencias concretas.
"""
from __future__ import annotations

import re
from typing import Any


# ──────────────────── parsear_pregunta ────────────────────


_INTENCIONES = {
    "tenant_safe": [
        re.compile(r"\btenant\b", re.IGNORECASE),
        re.compile(r"multi.?tenant", re.IGNORECASE),
        re.compile(r"para_usuario", re.IGNORECASE),
        re.compile(r"filtro.*tenant", re.IGNORECASE),
        re.compile(r"viola.*tenant", re.IGNORECASE),
        re.compile(r"seguro.*tenant", re.IGNORECASE),
    ],
    "state_transition": [
        re.compile(r"\bestado\b", re.IGNORECASE),
        re.compile(r"\btransici[oó]n\b", re.IGNORECASE),
        re.compile(r"cambiar.*estado", re.IGNORECASE),
    ],
    "no_import": [
        re.compile(r"import\w*\s*(algo|algo|module|paquete)", re.IGNORECASE),
        re.compile(r"importo\s*(algo\s*)?que\s*no\s*debia", re.IGNORECASE),
        re.compile(r"no.*import", re.IGNORECASE),
    ],
    "required_groups": [
        re.compile(r"\bgrupo\b", re.IGNORECASE),
        re.compile(r"\bpermiso\b", re.IGNORECASE),
        re.compile(r"solo\s+(admin|supervisor|gerente)", re.IGNORECASE),
        re.compile(r"quien\s+puede\s+acceder", re.IGNORECASE),
    ],
}


def parsear_pregunta(pregunta: str) -> dict:
    """Parsea una pregunta en lenguaje natural y retorna la intencion.

    Returns:
        dict con keys: tipo, confidence, pregunta_original
    """
    scores: dict[str, int] = {tipo: 0 for tipo in _INTENCIONES}
    for tipo, patterns in _INTENCIONES.items():
        for p in patterns:
            if p.search(pregunta):
                scores[tipo] += 1

    mejor_tipo = "general"
    mejor_score = 0
    for tipo, score in scores.items():
        if score > mejor_score:
            mejor_score = score
            mejor_tipo = tipo

    if mejor_tipo == "general":
        confidence = 0.3
    else:
        max_p = len(_INTENCIONES[mejor_tipo])
        confidence = min(0.9, 0.5 + (mejor_score / max_p) * 0.4)

    return {
        "tipo": mejor_tipo,
        "confidence": confidence,
        "pregunta_original": pregunta,
    }


# ──────────────────── responder_pregunta ────────────────────


_RESPUESTAS_BASE: dict[str, str] = {
    "tenant_safe": (
        "La pregunta es sobre **seguridad multi-tenant**.\n"
        "Verifica que el codigo use `para_usuario(user)` antes de "
        "cualquier consulta a la base de datos.\n\n"
        "Comando util: `docpact check --no-runtime` para detectar "
        "queries sin filtro de tenant."
    ),
    "state_transition": (
        "La pregunta es sobre **transiciones de estado**.\n"
        "Verifica que el codigo respete la matriz de estados definida "
        "en el modulo correspondiente.\n\n"
        "Comando util: `docpact check` para detectar "
        "transiciones no permitidas."
    ),
    "no_import": (
        "La pregunta es sobre **imports prohibidos**.\n"
        "Verifica que el codigo NO importe modulos que violan "
        "la separacion de concerns.\n\n"
        "Comando util: `docpact check` para detectar "
        "imports prohibidos."
    ),
    "required_groups": (
        "La pregunta es sobre **permisos o grupos**.\n"
        "Verifica que el codigo verifique el grupo/permiso "
        "antes de ejecutar la accion.\n\n"
        "Comando util: `docpact check` para detectar "
        "acciones sin verificacion de permisos."
    ),
    "general": (
        "Tu pregunta es general. docpact puede verificar:\n"
        "- Seguridad multi-tenant (usa `para_usuario`?)\n"
        "- Transiciones de estado (respetan la matriz?)\n"
        "- Imports prohibidos (separacion de concerns?)\n"
        "- Permisos y grupos (verificacion de acceso?)\n\n"
        "Comando util: `docpact check` para un verificado completo."
    ),
}


def responder_pregunta(pregunta: str) -> str:
    """Pipeline: pregunta -> parsear -> responder.

    Returns:
        String con la respuesta y sugerencia de accion.
    """
    intencion = parsear_pregunta(pregunta)
    return _RESPUESTAS_BASE.get(intencion["tipo"], _RESPUESTAS_BASE["general"])

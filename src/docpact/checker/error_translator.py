"""Traductor de errores técnicos a lenguaje humano.

El LLM del agente es quien explica, pero este módulo provee
el contexto necesario para que la explicación sea precisa y accionable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ErrorHumano:
    """Representación de un error en lenguaje humano."""

    titulo: str  # Resumen en 1 línea
    que_pasa: str  # Qué está mal (explicación simple)
    por_que_importa: str  # Por qué debería importarle al dueño
    como_arreglar: str  # Pasos concretos para arreglar
    urgencia: str  # "alta", "media", "baja"


# ── Templates de traducción por campo ──

_TEMPLATES: dict[str, dict[str, str]] = {
    "side_effects": {
        "titulo": "Efecto no declarado en {funcion}",
        "que_pasa": "La función {funcion} {accion} pero dice que no tiene efectos secundarios.",
        "por_que_importa": "Si no declarás los efectos, el sistema no puede verificar que se cumplan las reglas de negocio.",
        "como_arreglar": "Abrí el docstring de {funcion} y agregá el efecto al campo side_effects.",
    },
    "dependencias": {
        "titulo": "Dependencia no encontrada",
        "que_pasa": "La función {funcion} usa {dependencia} pero no existe en el proyecto.",
        "por_que_importa": "El código no va a funcionar si las dependencias no están.",
        "como_arreglar": "Verificá que {dependencia} esté instalada o importada correctamente.",
    },
    "rn_tests": {
        "titulo": "Regla de negocio sin test",
        "que_pasa": "La regla {rn} no tiene un test que la verifique.",
        "por_que_importa": "Sin test, no hay forma de saber si la regla se cumple.",
        "como_arreglar": "Creá un archivo tests/rn/test_{rn}.py con un test que verifique la regla.",
    },
    "input": {
        "titulo": "Tipo de entrada incorrecto en {funcion}",
        "que_pasa": "El parámetro {parametro} debería ser {tipo_esperado} pero parece ser {tipo_actual}.",
        "por_que_importa": "Esto puede causar errores inesperados en producción.",
        "como_arreglar": "Corregí el tipo del parámetro {parametro} en el docstring o en el código.",
    },
    "output": {
        "titulo": "Tipo de salida incorrecto en {funcion}",
        "que_pasa": "La función {funcion} debería devolver {tipo_esperado} pero devuelve {tipo_actual}.",
        "por_que_importa": "Esto puede romper código que depende de esta función.",
        "como_arreglar": "Corregí el tipo de retorno en el docstring o en el código.",
    },
    "borde": {
        "titulo": "Caso borde no manejado en {funcion}",
        "que_pasa": "La función {funcion} no maneja el caso {caso}.",
        "por_que_importa": "Esto puede causar errores en producción cuando se dé ese caso.",
        "como_arreglar": "Agregá manejo para el caso {caso} en la función.",
    },
    "firma": {
        "titulo": "Firma no coincide en {funcion}",
        "que_pasa": "La función {funcion} tiene parámetros diferentes a los declarados en el CONTRATO.",
        "por_que_importa": "El CONTRATO dice una cosa y el código hace otra.",
        "como_arreglar": "Actualizá el CONTRATO para que coincida con la firma real.",
    },
    "marker_honesty": {
        "titulo": "Marcador engañoso en {funcion}",
        "que_pasa": "La función {funcion} tiene un marcador {marcador} pero no parece implementar esa regla.",
        "por_que_importa": "Los marcadores falsos dan una falsa sensación de cumplimiento.",
        "como_arreglar": "Remové el marcador {marcador} o implementá la regla real.",
    },
    "transitive": {
        "titulo": "Efecto transitivo no declarado",
        "que_pasa": "La función {funcion} llama a {callee} que tiene efectos, pero no los declara.",
        "por_que_importa": "Los efectos ocultos pueden causar problemas difíciles de debuggear.",
        "como_arreglar": "Agregá los efectos de {callee} al CONTRATO de {funcion}.",
    },
}


def traducir_error(
    campo: str,
    funcion: str,
    mensaje: str,
    datos_extra: dict | None = None,
) -> ErrorHumano:
    """Traduce un error técnico a lenguaje humano.

    El LLM del agente usa esta información para generar
    una explicación personalizada al dueño de negocio.

    Args:
        campo: Campo del error (side_effects, dependencias, etc.)
        funcion: Nombre de la función con el error
        mensaje: Mensaje técnico del error
        datos_extra: Datos adicionales para personalizar la explicación

    Returns:
        ErrorHumano con contexto para el LLM
    """
    datos = datos_extra or {}
    template = _TEMPLATES.get(campo, _TEMPLATES["side_effects"])

    # Llenar templates con datos disponibles (safe formatting)
    vars_ctx = {"funcion": funcion, "mensaje": mensaje, **datos}

    def _safe_format(text: str) -> str:
        """Formatea string ignorando variables faltantes."""
        try:
            return text.format(**vars_ctx)
        except KeyError:
            # Reemplazar variables faltantes con ""
            import re
            result = text
            for key in vars_ctx:
                result = result.replace("{" + key + "}", str(vars_ctx[key]))
            # Limpiar variables sin reemplazo
            result = re.sub(r"\{[a-z_]+\}", "", result)
            return result

    titulo = _safe_format(template["titulo"])
    que_pasa = _safe_format(template["que_pasa"])
    por_que = _safe_format(template["por_que_importa"])
    como = _safe_format(template["como_arreglar"])

    # Determinar urgencia
    urgencia = "media"
    if campo in ("side_effects", "rn_tests"):
        urgencia = "alta"
    elif campo in ("borde", "marker_honesty"):
        urgencia = "baja"

    return ErrorHumano(
        titulo=titulo,
        que_pasa=que_pasa,
        por_que_importa=por_que,
        como_arreglar=como,
        urgencia=urgencia,
    )


def generar_resumen_humano(hallazgos: list[dict]) -> dict:
    """Genera un resumen legible para el dueño de negocio.

    Agrupa errores por urgencia y da un panorama general.
    El agente puede usar esto para explicar el estado del proyecto.

    Args:
        hallazgos: Lista de hallazgos del checker

    Returns:
        Resumen estructurado para el dueño
    """
    por_urgencia = {"alta": [], "media": [], "baja": []}

    for h in hallazgos:
        ctx = h.get("contexto", {})
        error_humano = traducir_error(
            campo=h.get("campo", ""),
            funcion=h.get("funcion", ""),
            mensaje=h.get("mensaje", ""),
            datos_extra=ctx,
        )
        por_urgencia[error_humano.urgencia].append({
            "titulo": error_humano.titulo,
            "que_pasa": error_humano.que_pasa,
            "por_que_importa": error_humano.por_que_importa,
            "como_arreglar": error_humano.como_arreglar,
            "archivo": h.get("archivo", ""),
            "funcion": h.get("funcion", ""),
        })

    total = len(hallazgos)
    alta = len(por_urgencia["alta"])
    media = len(por_urgencia["media"])
    baja = len(por_urgencia["baja"])

    if alta > 0:
        diagnostico = f"Hay {alta} problemas urgentes que necesitan atención inmediata."
    elif media > 0:
        diagnostico = f"Todo está funcionando pero hay {media} mejoras recomendadas."
    else:
        diagnostico = "El proyecto está en buen estado."

    return {
        "diagnostico": diagnostico,
        "total_errores": total,
        "por_urgencia": {
            "alta": alta,
            "media": media,
            "baja": baja,
        },
        "detalles": por_urgencia,
    }

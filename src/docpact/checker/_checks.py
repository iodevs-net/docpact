"""Conversión de errores de checkers a Hallazgo.

Helper para eliminar código repetitivo de creación de Hallazgo
en todo el pipeline de verificación.
"""

from __future__ import annotations

from docpact.checker.models import Hallazgo


def to_hallazgo(
    err: object,
    nombre: str,
    archivo: str,
    default_linea: int,
    *,
    tipo: str = "error",
) -> Hallazgo:
    """Convierte cualquier checker output a Hallazgo.

    Args:
        err: Objeto con atributos .campo, .mensaje, .linea, .sugerencia
             (típicamente ErrorParser o similar).
        nombre: Nombre de la función siendo verificada.
        archivo: Ruta del archivo fuente.
        default_linea: Línea por defecto si err.linea es 0 o None.
        tipo: Tipo de hallazgo ("error", "warning", "info").

    Returns:
        Hallazgo construido con los campos del error.
    """
    return Hallazgo(
        tipo=tipo,
        campo=err.campo,
        funcion=nombre,
        archivo=archivo,
        linea=err.linea or default_linea,
        mensaje=err.mensaje,
        sugerencia=err.sugerencia,
    )

"""Verificador de RNs contra el registro oficial.

Valida que las RNs declaradas en CONTRATOs existan en
docs/reglas-del-negocio/REGISTRO.md del proyecto.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from docpact.models.contrato import ErrorParser, ReglaNegocio

_RN_RE = re.compile(r"RN-\d{3}")
_REGISTRO_PATH = Path("docs") / "reglas-del-negocio" / "REGISTRO.md"


def check_rn_against_registry(
    proyecto_root: str | Path,
    rns: list[ReglaNegocio],
) -> tuple[list[ErrorParser], list[ErrorParser]]:
    """Verifica que las RNs declaradas existan en el registro oficial.

    Args:
        proyecto_root: Ruta raíz del proyecto.
        rns: Lista de reglas de negocio declaradas en el CONTRATO.

    Returns:
        Tupla (errores, infos):
        - errores: RNs declaradas pero ausentes en el registro.
        - infos: RNs confirmadas en el registro.
    """
    registry_ids = _cargar_ids_registro(proyecto_root)
    if registry_ids is None:
        # No hay registro — no se puede validar, skip silencioso
        return [], []

    errores: list[ErrorParser] = []
    infos: list[ErrorParser] = []

    for rn in rns:
        if rn.id not in registry_ids:
            errores.append(ErrorParser(
                campo="rn-registry",
                mensaje=f"RN '{rn.id}' declarada en CONTRATO pero no encontrada "
                        f"en docs/reglas-del-negocio/REGISTRO.md",
                sugerencia=f"Agrega '{rn.id}' al registro oficial en "
                           f"docs/reglas-del-negocio/REGISTRO.md",
            ))
        else:
            infos.append(ErrorParser(
                campo="rn-registry",
                mensaje=f"RN '{rn.id}' confirmada en el registro oficial",
            ))

    return errores, infos


def _cargar_ids_registro(
    proyecto_root: str | Path,
) -> Optional[set[str]]:
    """Carga los IDs RN-XXX del registro oficial.

    Returns:
        Set de IDs o None si el archivo no existe.
    """
    ruta = Path(proyecto_root) / _REGISTRO_PATH
    if not ruta.exists():
        return None

    try:
        texto = ruta.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    return set(_RN_RE.findall(texto))

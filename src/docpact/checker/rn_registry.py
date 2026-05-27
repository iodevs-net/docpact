"""Lee RN-XXX desde docs/reglas-del-negocio/REGISTRO.md

Retorna dict RN_ID -> descripcion para enriquecer CONTRATOs.
"""

from __future__ import annotations

import re
from pathlib import Path

from docpact.models.contrato import ReglaNegocio


def cargar_registro(project_root: str | Path) -> dict[str, str]:
    """Parsea REGISTRO.md y retorna {RN_ID: descripcion}."""
    ruta = Path(project_root) / "docs" / "reglas-del-negocio" / "REGISTRO.md"
    if not ruta.exists():
        return {}

    content = ruta.read_text(encoding="utf-8")
    resultados: dict[str, str] = {}

    for match in re.finditer(
        r"\|\s*(RN-[\w-]+)\s*\|\s*([^|]+)", content
    ):
        rn_id = match.group(1).strip()
        desc = match.group(2).strip().replace("`", "")
        if rn_id and desc:
            resultados[rn_id] = desc

    return resultados


def enriquecer_rn(
    rn_list: list[ReglaNegocio],
    project_root: Path,
) -> list[ReglaNegocio]:
    """Retorna nueva lista con descripciones desde REGISTRO.md."""
    registro = cargar_registro(project_root)
    result = []
    for rn in rn_list:
        if rn.id in registro and not rn.descripcion:
            result.append(ReglaNegocio(id=rn.id, descripcion=registro[rn.id]))
        else:
            result.append(rn)
    return result

"""Lee RN-XXX desde docs/reglas-del-negocio/REGISTRO.md

Retorna dict RN_ID -> descripcion para enriquecer CONTRATOs.
Ademas provee funciones de cross-reference para detectar:
- rns_fake: declaradas en CONTRATOS pero NO existen en REGISTRO
- rns_huerfanas: existen en REGISTRO pero NO aparecen en ningun CONTRATO
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from docpact.models.contrato import ReglaNegocio


# IDs que NO cuentan como "reales" — son placeholders, work-in-progress, etc.
# El audit los excluye de las estadisticas para no inflar las metricas.
_RN_PLACEHOLDERS = re.compile(r"^RN-(?:XXX|NO-APLICA|TBD|WIP)$", re.IGNORECASE)


def cargar_registro(project_root: str | Path) -> dict[str, str]:
    """Parsea REGISTRO.md y retorna {RN_ID: descripcion}."""
    ruta = Path(project_root) / "docs" / "reglas-del-negocio" / "REGISTRO.md"
    if not ruta.exists():
        return {}

    content = ruta.read_text(encoding="utf-8")
    resultados: dict[str, str] = {}

    for match in re.finditer(r"\|\s*(RN-[\w-]+)\s*\|\s*([^|]+)", content):
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


def es_rn_placeholder(rn_id: str) -> bool:
    """True si el ID es un placeholder (RN-XXX, RN-NO-APLICA, etc.) y no una regla real."""
    return bool(_RN_PLACEHOLDERS.match(rn_id))


# ── Cross-reference: detectar mentiras y olvidos ──


@dataclass
class RNFakeHallazgo:
    """Una RN declarada en CONTRATO pero que NO existe en REGISTRO.md.

    Esto indica una MENTIRA del agente: declaro una regla que no existe
    en la documentacion canonica. Debe corregirse.
    """
    rn_id: str
    archivo: str
    linea: int
    funcion: str
    sugerencia: str = "Verificar si la RN existe en docs/reglas-del-negocio/REGISTRO.md. Si no existe, agregarla o quitarla del CONTRATO."


@dataclass
class RNHuerfanaHallazgo:
    """Una RN que existe en REGISTRO.md pero NO aparece en ningun CONTRATO.

    Esto indica un OLVIDO: la regla esta documentada pero no implementada
    (o no se declaro en el CONTRATO). Debe cubrirse.
    """
    rn_id: str
    descripcion: str
    sugerencia: str = "Si la regla esta implementada, agregar 'rn: [RN-XXX]' al CONTRATO de la funcion que la implementa. Si NO esta implementada, marcarla como 'pendiente' en REGISTRO.md."


@dataclass
class ResultadoCrossRef:
    """Resultado completo del cross-reference entre CONTRATOS y REGISTRO."""
    rns_fake: list[RNFakeHallazgo] = field(default_factory=list)
    rns_huerfanas: list[RNHuerfanaHallazgo] = field(default_factory=list)
    rns_placeholders: list[str] = field(default_factory=list)  # excluidas de fake

    @property
    def total_fake(self) -> int:
        return len(self.rns_fake)

    @property
    def total_huerfanas(self) -> int:
        return len(self.rns_huerfanas)

    def es_sano(self) -> bool:
        """True si no hay RNs fake y todas las RNs del REGISTRO estan cubiertas."""
        return self.total_fake == 0 and self.total_huerfanas == 0


def crossref_contratos_registro(
    contratos: list,  # list[ContratoExtraido]
    project_root: str | Path,
) -> ResultadoCrossRef:
    """Cruza las RNs declaradas en CONTRATOS contra el REGISTRO.md canonico.

    Detecta:
    - rns_fake: declaradas en CONTRATOS pero NO en REGISTRO
    - rns_huerfanas: en REGISTRO pero NO en ningun CONTRATO
    - rns_placeholders: RN-XXX, RN-NO-APLICA, etc. (excluidas del conteo)

    Args:
        contratos: Lista de ContratoExtraido del proyecto (de check_proyecto).
        project_root: Raiz del proyecto (donde esta docs/reglas-del-negocio/).

    Returns:
        ResultadoCrossRef con las RNs problematicas.
    """
    registro = cargar_registro(project_root)
    resultado = ResultadoCrossRef()

    # Set de RNs declaradas en CONTRATOS (excluyendo placeholders)
    rns_en_contratos: set[str] = set()
    for c in contratos:
        if not c.contrato:
            continue
        for rn in c.contrato.rn:
            rn_id = rn.id
            if es_rn_placeholder(rn_id):
                if rn_id not in resultado.rns_placeholders:
                    resultado.rns_placeholders.append(rn_id)
                continue
            rns_en_contratos.add(rn_id)
            if rn_id not in registro:
                # MENTIRA: declarada en codigo pero no en documentacion
                resultado.rns_fake.append(
                    RNFakeHallazgo(
                        rn_id=rn_id,
                        archivo=c.archivo,
                        linea=c.linea,
                        funcion=c.funcion,
                    )
                )

    # RNs huerfanas: en REGISTRO pero no en CONTRATOS
    for rn_id, descripcion in sorted(registro.items()):
        if es_rn_placeholder(rn_id):
            continue
        if rn_id not in rns_en_contratos:
            resultado.rns_huerfanas.append(
                RNHuerfanaHallazgo(rn_id=rn_id, descripcion=descripcion)
            )

    return resultado

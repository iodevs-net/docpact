"""Modelos de datos del pipeline de verificación.

Extraídos de orchestrator.py para separar responsabilidades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from docpact.config import DocpactConfig
from docpact.models.contrato import Contrato, ErrorParser


@dataclass
class Hallazgo:
    """Un hallazgo individual de la verificación."""

    tipo: str  # "error" o "warning"
    campo: str
    funcion: str
    archivo: str
    linea: int
    mensaje: str
    sugerencia: str = ""
    contexto: dict = field(default_factory=dict)  # Datos extra para explicación humana

    def a_error_parser(self) -> ErrorParser:
        """Convierte a ErrorParser para compatibilidad con el parser."""
        return ErrorParser(
            campo=self.campo,
            mensaje=self.mensaje,
            linea=self.linea,
            sugerencia=self.sugerencia,
        )


def _suprimir_hallazgos(
    hallazgos: list[Hallazgo], config: DocpactConfig
) -> list[Hallazgo]:
    """Filtra hallazgos cuyo mensaje coincida con patrones de supresión."""
    if not config.warnings_suppress:
        return hallazgos
    return [h for h in hallazgos if not config.debe_suprimir(h.mensaje)]


@dataclass
class ResultadoFuncion:
    """Resultado de la verificación de una función."""

    nombre: str
    archivo: str
    linea: int
    tiene_contrato: bool
    contrato: Optional[Contrato] = None
    hallazgos: list[Hallazgo] = field(default_factory=list)
    codigo_funcion: str = ""

    @property
    def errores(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.tipo == "error"]

    @property
    def warnings(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.tipo == "warning"]

    @property
    def valido(self) -> bool:
        return len(self.errores) == 0


@dataclass
class ResultadoArchivo:
    """Resultado de la verificación de un archivo completo."""

    archivo: str
    funciones: list[ResultadoFuncion] = field(default_factory=list)

    @property
    def total_funciones(self) -> int:
        return len(self.funciones)

    @property
    def funciones_con_contrato(self) -> int:
        return sum(1 for f in self.funciones if f.tiene_contrato)

    @property
    def total_errores(self) -> int:
        return sum(len(f.errores) for f in self.funciones)

    @property
    def total_warnings(self) -> int:
        return sum(len(f.warnings) for f in self.funciones)


@dataclass
class ResultadoProyecto:
    """Resultado de la verificación de todo el proyecto."""

    archivos: list[ResultadoArchivo] = field(default_factory=list)
    config: DocpactConfig = field(default_factory=DocpactConfig)
    rns_fake: list = field(default_factory=list)
    rns_huerfanas: list = field(default_factory=list)
    rns_placeholders: list[str] = field(default_factory=list)

    @property
    def total_funciones(self) -> int:
        return sum(a.total_funciones for a in self.archivos)

    @property
    def funciones_con_contrato(self) -> int:
        return sum(a.funciones_con_contrato for a in self.archivos)

    @property
    def total_errores(self) -> int:
        return sum(a.total_errores for a in self.archivos)

    @property
    def total_warnings(self) -> int:
        return sum(a.total_warnings for a in self.archivos)

    @property
    def total_archivos(self) -> int:
        return len(self.archivos)

    def _ponderar_hallazgos(self) -> tuple[int, int]:
        """Agrupa hallazgos por campo y aplica pesos diferenciales."""
        PESOS_ERROR = {
            "rn_tests": 20,
            "side_effects": 15,
            "presencia": 12,
            "rn": 10,
            "dependencias": 5,
        }
        PESOS_WARNING = {
            "side_effects": 5,
            "rn": 3,
            "dependencias": 2,
        }
        ERROR_DEFAULT = 10
        WARNING_DEFAULT = 3

        err_ponderado = 0
        warn_ponderado = 0
        for archivo in self.archivos:
            for func in archivo.funciones:
                for h in func.hallazgos:
                    if h.tipo == "error":
                        err_ponderado += PESOS_ERROR.get(h.campo, ERROR_DEFAULT)
                    elif h.tipo == "warning":
                        warn_ponderado += PESOS_WARNING.get(h.campo, WARNING_DEFAULT)
        return err_ponderado, warn_ponderado

    def calcular_score(self) -> int:
        """Calcula el score AI-Native (0-100).

        DEPRECADO 2026-06-02: este score es "vanity metric" — no predice
        bugs evitados ni calidad real. Usar `metricas_honestas()` en su lugar.
        Se mantiene por compatibilidad con integraciones existentes.
        """
        if self.total_funciones == 0:
            return 0

        score = 100

        sin_contrato = self.total_funciones - self.funciones_con_contrato
        if sin_contrato > 0:
            penalty_sin = min(30, int((sin_contrato / self.total_funciones) * 50))
            score -= penalty_sin

        err_pond, warn_pond = self._ponderar_hallazgos()
        if err_pond > 0:
            penalty_errores = min(40, err_pond)
            score -= penalty_errores

        if warn_pond > 0:
            penalty_warnings = min(15, warn_pond)
            score -= penalty_warnings

        return max(0, score)

    def metricas_honestas(self) -> dict:
        """Métricas que SÍ predicen calidad del proyecto (vs REGISTRO)."""
        return {
            "rns_fake": len(self.rns_fake),
            "rns_huerfanas": len(self.rns_huerfanas),
            "rns_placeholders": len(self.rns_placeholders),
            "funciones_sin_contrato": self.total_funciones - self.funciones_con_contrato,
            "funciones_totales": self.total_funciones,
            "score_legacy": self.calcular_score(),
        }

    @property
    def nivel(self) -> str:
        score = self.calcular_score()
        if score >= 90:
            return "L4 — AI-Optimized"
        elif score >= 75:
            return "L3 — AI-Native"
        elif score >= 50:
            return "L2 — AI-Friendly"
        elif score >= 25:
            return "L1 — AI-Aware"
        return "L0 — Human-Native"

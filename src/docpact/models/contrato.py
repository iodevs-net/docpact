"""Dataclasses del dominio CONTRATO.

Cada CONTRATO extraído de un docstring se representa con estas clases.
Son inmutables (frozen=True) para garantizar integridad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TipoFuncion(Enum):
    """Tipo de símbolo donde se encontró el CONTRATO."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"


@dataclass(frozen=True)
class CampoInput:
    """Declaración de un parámetro de entrada en el CONTRATO."""
    nombre: str
    tipo: str
    descripcion: str = ""


@dataclass(frozen=True)
class SideEffect:
    """Declaración de un side effect."""
    descripcion: str


@dataclass(frozen=True)
class ReglaNegocio:
    """Declaración de una regla de negocio referenciada."""
    id: str  # ej: "RN-010"
    descripcion: str = ""


@dataclass(frozen=True)
class CasoBorde:
    """Declaración de un caso borde."""
    condicion: str
    comportamiento: str


@dataclass(frozen=True)
class Dependencia:
    """Declaración de una dependencia externa."""
    ref: str  # ej: "soporte/models/ticket.py::Ticket"


@dataclass(frozen=True)
class Contrato:
    """CONTRATO parseado y validado.

    Campos opcionales son None si no se declararon en el docstring.
    side_effects es obligatorio — si no se declara, es lista vacía con advertencia.
    """
    input: dict[str, CampoInput] = field(default_factory=dict)
    output: Optional[str] = None
    output_descripcion: str = ""
    side_effects: list[SideEffect] = field(default_factory=list)
    rn: list[ReglaNegocio] = field(default_factory=list)
    borde: list[CasoBorde] = field(default_factory=list)
    dependencias: list[Dependencia] = field(default_factory=list)

    def tiene_side_effects(self) -> bool:
        """Retorna True si hay side effects declarados (no 'ninguno')."""
        return len(self.side_effects) > 0

    @property
    def resumen(self) -> str:
        """Resumen legible del contrato."""
        partes = []
        if self.input:
            partes.append(f"input({len(self.input)} params)")
        if self.output:
            partes.append(f"output: {self.output}")
        if self.side_effects:
            partes.append(f"side_effects({len(self.side_effects)}): {', '.join(s.descripcion[:30] for s in self.side_effects)}")
        else:
            partes.append("side_effects: ninguno")
        if self.rn:
            partes.append(f"rn: {', '.join(r.id for r in self.rn)}")
        return " | ".join(partes)


@dataclass(frozen=True)
class ErrorParser:
    """Error encontrado durante parseo o validación."""
    campo: str  # nombre del campo donde ocurre, o "general"
    mensaje: str
    linea: int = 0
    sugerencia: str = ""

    def __str__(self) -> str:
        return f"[{self.campo}] L{self.linea}: {self.mensaje}"


@dataclass(frozen=True)
class ContratoExtraido:
    """Resultado completo de la extracción de un CONTRATO de un archivo."""
    funcion: str
    tipo: TipoFuncion
    archivo: str
    linea: int
    contrato: Contrato
    raw_text: str  # texto original del bloque CONTRATO
    errores: list[ErrorParser] = field(default_factory=list)

    @property
    def es_valido(self) -> bool:
        """El contrato se parseó sin errores críticos."""
        return len(self.errores) == 0

    @property
    def ubicacion(self) -> str:
        """Etiqueta de ubicación: archivo::funcion:linea."""
        return f"{self.archivo}::{self.funcion}:{self.linea}"

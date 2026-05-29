"""Lexer para bloques CONTRATO en docstrings.

Convierte el texto del bloque CONTRATO en una lista de tokens
estructurados. Usa indentación relativa: detecta el nivel de
los campos raíz automáticamente (pueden estar al mismo nivel
que CONTRATO: o indentados +2 espacios).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TipoToken(Enum):
    """Tipos de token que produce el lexer."""

    MARCA_CONTRATO = "MARCA_CONTRATO"
    CAMPO_SIMPLE = "CAMPO_SIMPLE"
    CAMPO_COMPUESTO = "CAMPO_COMPUESTO"
    ITEM_LISTA = "ITEM_LISTA"
    SUB_CAMPO = "SUB_CAMPO"
    TEXTO_LIBRE = "TEXTO_LIBRE"


@dataclass(frozen=True)
class Token:
    """Un token individual del bloque CONTRATO."""

    tipo: TipoToken
    valor: str
    linea: int
    indentacion: int = 0

    def __repr__(self) -> str:
        return f"Token({self.tipo.name}, {self.valor!r}, L{self.linea})"


def tokenizar(docstring: str) -> list[Token]:
    """Tokeniza un docstring extrayendo el bloque CONTRATO.

    Detecta automáticamente el nivel de indentación de los campos
    raíz. Soporta dos estilos:

    Estilo 1 (campos al mismo nivel que CONTRATO:):
        CONTRATO:
        input:
          param: type — desc
        side_effects: ninguno

    Estilo 2 (campos indentados +2):
        CONTRATO:
          input:
            param: type — desc
          side_effects: ninguno

    Args:
        docstring: El texto completo del docstring de una función.

    Returns:
        Lista de tokens encontrados. Vacía si no hay bloque CONTRATO.
    """
    lineas = docstring.split("\n")
    tokens: list[Token] = []

    # Encontrar la línea CONTRATO: y su indentación base
    base_indent = None
    start_idx = -1
    for i, linea in enumerate(lineas):
        if "CONTRATO:" in linea.strip():
            base_indent = len(linea) - len(linea.lstrip())
            start_idx = i
            tokens.append(Token(TipoToken.MARCA_CONTRATO, linea.strip(), i + 1, 0))
            break

    if base_indent is None:
        return []

    # Encontrar líneas después de CONTRATO: para determinar el nivel de campos
    lineas_restantes = []
    for i in range(start_idx + 1, len(lineas)):
        raw = lineas[i]
        stripped = raw.strip()
        if not stripped:
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent < base_indent:
            # Fin del bloque (misma indentación que CONTRATO: = campos raíz)
            break
        lineas_restantes.append((i, raw, stripped, indent))

    if not lineas_restantes:
        return tokens

    # La primera línea con contenido define el nivel de los campos raíz
    primer_indent = lineas_restantes[0][3]
    nivel_campos = primer_indent

    # Campos raíz válidos en docpact
    CAMPOS_RAIZ = {"input", "output", "side_effects", "rn", "borde", "dependencias", "reglas"}

    for i, raw, stripped, indent in lineas_restantes:
        linea_num = i + 1

        # Clasificación semántica de campos raíz (independiente de espacios exactos)
        es_campo_raiz = False
        if ":" in stripped:
            posible_raiz = stripped.split(":", 1)[0].strip().lower()
            if posible_raiz in CAMPOS_RAIZ:
                es_campo_raiz = True

        if es_campo_raiz:
            if stripped.endswith(":"):
                # Campo compuesto (ej. input:, rn:, dependencias:)
                nombre_campo = stripped[:-1].strip()
                tokens.append(
                    Token(TipoToken.CAMPO_COMPUESTO, nombre_campo, linea_num, indent)
                )
            else:
                # Campo simple (ej. side_effects: ninguno, rn: [RN-010])
                tokens.append(Token(TipoToken.CAMPO_SIMPLE, stripped, linea_num, indent))

        elif indent > nivel_campos and stripped.startswith("-"):
            # Item de lista
            tokens.append(Token(TipoToken.ITEM_LISTA, stripped, linea_num, indent))

        elif indent > nivel_campos and not stripped.startswith("-") and ":" in stripped:
            # Sub-campo (ej. param: type)
            tokens.append(Token(TipoToken.SUB_CAMPO, stripped, linea_num, indent))

        else:
            tokens.append(Token(TipoToken.TEXTO_LIBRE, stripped, linea_num, indent))

    return tokens

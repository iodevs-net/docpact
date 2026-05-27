"""Parser de CONTRATOS — extrae docstrings y tokeniza bloques CONTRATO."""

from .extractor import extraer_docstrings
from .lexer import tokenizar, Token, TipoToken
from .parser import parsear
from .ts_parser import extraer_contratos_ts

__all__ = [
    "extraer_docstrings", "tokenizar", "parsear", "Token", "TipoToken",
    "extraer_contratos_ts",
]

"""Parser de CONTRATOS — extrae docstrings y tokeniza bloques CONTRATO."""

from .extractor import extraer_docstrings
from .lexer import tokenizar, Token, TipoToken
from .parser import parsear

__all__ = ["extraer_docstrings", "tokenizar", "parsear", "Token", "TipoToken"]

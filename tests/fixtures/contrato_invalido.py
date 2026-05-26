"""Fixture: función con CONTRATO inválido (errores de formato)."""


def proceso_erroneo() -> None:
    """Procesa datos.

    CONTRATO:
      input:
        datos_invalidos — falta tipo y separador
      output:
      side_effects:
      rn:
        - regla-sin-formato-rn
      borde:
        caso sin separador
    """
    pass

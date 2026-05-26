"""Fixture: función con CONTRATO mínimo (solo side_effects)."""


def ping() -> str:
    """Healthcheck.

    CONTRATO:
      side_effects: ninguno
    """
    return "pong"

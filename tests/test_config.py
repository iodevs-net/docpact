"""Tests del config de docpact."""

from docpact.config import DocpactConfig


def test_config_defaults():
    """Config por defecto debe tener valores sensibles."""
    c = DocpactConfig()
    assert c.strict is False
    assert c.min_score == 75
    assert len(c.exclude) > 0
    assert len(c.patrones_side_effects) > 0
    assert c.rn_prefix == "RN-"


def test_config_debe_excluir():
    """Debe excluir directorios comunes."""
    from pathlib import Path
    c = DocpactConfig()
    assert c.debe_excluir(Path("node_modules/foo/bar.js"))
    assert c.debe_excluir(Path(".venv/lib/python3.12/site-packages"))
    assert not c.debe_excluir(Path("soporte/services/tickets.py"))


def test_config_patrones_compilados():
    """Patrones compilados deben funcionar para matching."""
    c = DocpactConfig()
    patrones = c.patrones_compilados
    assert "db_write" in patrones
    assert len(patrones["db_write"]) > 0
    # Verificar que el patrón compilado hace match
    import re
    assert any(p.search("Ticket.objects.create()") for p in patrones["db_write"])


def test_config_desde_toml_sin_archivo():
    """Sin archivo, desde_toml debe retornar config por defecto."""
    c = DocpactConfig.desde_toml("/no/existe/docpact.toml")
    assert c.strict is False

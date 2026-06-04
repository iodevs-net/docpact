"""Tests del loader de rn_patrones: aceptar specs legacy ('patron') y semánticos ('type')."""

from __future__ import annotations

from pathlib import Path

import pytest

from docpact.config import DocpactConfig


@pytest.fixture
def toml_con_patron_legacy(tmp_path: Path) -> Path:
    toml = tmp_path / "docpact.toml"
    toml.write_text(
        """[docpact]
[docpact.rn_patrones]
"RN-001" = { patron = "INTERVALO" }
""",
        encoding="utf-8",
    )
    return toml


@pytest.fixture
def toml_con_type_semantico(tmp_path: Path) -> Path:
    toml = tmp_path / "docpact.toml"
    toml.write_text(
        """[docpact]
[docpact.rn_patrones]
"RN-002" = { type = "tenant_safe", forbid = ["unfiltered_objects"] }
""",
        encoding="utf-8",
    )
    return toml


@pytest.fixture
def toml_mixto(tmp_path: Path) -> Path:
    toml = tmp_path / "docpact.toml"
    toml.write_text(
        """[docpact]
[docpact.rn_patrones]
"RN-LEGACY" = { patron = "X" }
"RN-SEMANTIC" = { type = "no_import", patterns = ["stripe"] }
""",
        encoding="utf-8",
    )
    return toml


def test_loader_acepta_spec_legacy_con_patron(toml_con_patron_legacy):
    cfg = DocpactConfig.desde_toml(toml_con_patron_legacy)
    assert "RN-001" in cfg.rn_patrones
    assert cfg.rn_patrones["RN-001"]["patron"] == "INTERVALO"


def test_loader_acepta_spec_semantico_con_type(toml_con_type_semantico):
    cfg = DocpactConfig.desde_toml(toml_con_type_semantico)
    assert "RN-002" in cfg.rn_patrones
    assert cfg.rn_patrones["RN-002"]["type"] == "tenant_safe"
    assert cfg.rn_patrones["RN-002"]["forbid"] == ["unfiltered_objects"]


def test_loader_acepta_mezcla_legacy_y_semantico(toml_mixto):
    cfg = DocpactConfig.desde_toml(toml_mixto)
    assert set(cfg.rn_patrones.keys()) == {"RN-LEGACY", "RN-SEMANTIC"}

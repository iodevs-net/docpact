"""Tests para `diagnostico()` en docpact.mcp_server.

Cubre la estructura del dict retornado y los valores esperados.
Sin dependencias del sistema de archivos real (usa tmp_path).
"""
from __future__ import annotations

import json


from docpact.mcp_server import diagnostico


EXPECTED_KEYS = {
    "python_version",
    "python_executable",
    "docpact_module_path",
    "docpact_in_PATH",
    "cwd",
    "project_root_env",
    "index_path",
    "index_exists",
}


def test_diagnostico_retorna_dict_con_keys_esperadas():
    """diagnostico() retorna un dict con todas las keys esperadas."""
    diag = diagnostico()
    assert isinstance(diag, dict)
    assert set(diag.keys()) == EXPECTED_KEYS


def test_diagnostico_tipos_de_valores():
    """Cada valor en diagnostico() tiene el tipo esperado."""
    diag = diagnostico()
    assert isinstance(diag["python_version"], str)
    assert isinstance(diag["python_executable"], str)
    assert isinstance(diag["docpact_module_path"], str)
    assert diag["docpact_in_PATH"] is None or isinstance(diag["docpact_in_PATH"], str)
    assert isinstance(diag["cwd"], str)
    assert diag["project_root_env"] is None or isinstance(diag["project_root_env"], str)
    assert isinstance(diag["index_path"], str)
    assert isinstance(diag["index_exists"], bool)


def test_diagnostico_index_path_termina_en_index_json():
    """El index_path debe apuntar a .docpact/index.json relativo al cwd."""
    diag = diagnostico()
    assert diag["index_path"].endswith(".docpact/index.json")
    assert diag["cwd"] in diag["index_path"]


def test_diagnostico_index_exists_false_si_no_existe(tmp_path, monkeypatch):
    """Si el .docpact/index.json no existe, index_exists debe ser False."""
    monkeypatch.chdir(tmp_path)
    diag = diagnostico()
    assert diag["index_exists"] is False


def test_diagnostico_index_exists_true_si_existe(tmp_path, monkeypatch):
    """Si el .docpact/index.json existe, index_exists debe ser True."""
    docpact_dir = tmp_path / ".docpact"
    docpact_dir.mkdir()
    (docpact_dir / "index.json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    diag = diagnostico()
    assert diag["index_exists"] is True


def test_diagnostico_serializable_a_json():
    """El dict debe ser serializable a JSON (sin valores no-JSON)."""
    diag = diagnostico()
    json.dumps(diag)

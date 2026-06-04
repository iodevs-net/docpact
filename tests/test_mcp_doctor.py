"""Tests para el subcomando `docpact mcp-doctor`.

Cubre que el subcomando existe, que acepta --json, y que retorna
codigos de salida correctos sin crashear.
"""
from __future__ import annotations

import contextlib
import io
import json

import pytest

from docpact.cli.main import main


def test_mcp_doctor_help_exit_0(capsys):
    """`docpact mcp-doctor --help` exit 0 y muestra usage."""
    with pytest.raises(SystemExit) as exc_info:
        main(["mcp-doctor", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "mcp-doctor" in captured.out
    assert "--json" in captured.out


def test_mcp_doctor_sin_args_exit_0_o_1(capsys, tmp_path, monkeypatch):
    """`docpact mcp-doctor` exit 0 (todo OK) o 1 (problemas). Nunca crashea."""
    monkeypatch.chdir(tmp_path)
    rc = main(["mcp-doctor"])
    assert rc in (0, 1)
    captured = capsys.readouterr()
    assert "docpact MCP doctor" in captured.out or "{" in captured.out


def test_mcp_doctor_json_output_es_json_valido(capsys, tmp_path, monkeypatch):
    """`docpact mcp-doctor --json` produce JSON parseable con keys esperadas."""
    monkeypatch.chdir(tmp_path)
    rc = main(["mcp-doctor", "--json"])
    assert rc in (0, 1)
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert "problemas" in out
    assert "ok" in out
    assert isinstance(out["problemas"], list)
    assert isinstance(out["ok"], bool)
    if out["problemas"]:
        assert out["ok"] is False


def test_mcp_doctor_json_con_index_existente_ok_true(tmp_path, monkeypatch):
    """Si el index existe, --json no debe reportar problemas sobre el index."""
    docpact_dir = tmp_path / ".docpact"
    docpact_dir.mkdir()
    (docpact_dir / "index.json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["mcp-doctor", "--json"])
    assert rc in (0, 1)
    out = json.loads(buf.getvalue())
    problemas_sobre_index = [p for p in out["problemas"] if "index" in p.lower()]
    assert problemas_sobre_index == []


def test_dispatch_mcp_doctor_registrado():
    """El subcomando mcp-doctor debe estar registrado (no 'unknown command')."""
    with pytest.raises(SystemExit) as exc_info:
        main(["mcp-doctor", "--help"])
    assert exc_info.value.code == 0

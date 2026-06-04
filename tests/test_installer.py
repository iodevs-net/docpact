"""Tests para docpact.installer (Mejora #6 — install-mcp).

Cubre:
- Deteccion de host (OMP, Claude Code, project-level, unknown)
- Generacion de config JSON segun host
- Escritura de config al path correcto (con creacion de directorios padre)
- Verificacion de que el wrapper arranca
- Integracion install_mcp()
"""
from __future__ import annotations

import json
from pathlib import Path


from docpact.installer import (
    detectar_host,
    escribir_config,
    generar_config,
    install_mcp,
    verificar_wrapper,
)


# ─────────────────────────── detectar_host ───────────────────────────


def test_detectar_host_omp_cuando_existe_omp_dir(tmp_path, monkeypatch):
    """Si ~/.omp/ existe (incluso vacio), host = 'omp' (preferido)."""
    home = tmp_path / "home"
    (home / ".omp").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    assert detectar_host() == "omp"


def test_detectar_host_omp_project_cuando_existe_omp_en_cwd(tmp_path, monkeypatch):
    """Si .omp/ existe en cwd, host = 'omp_project'."""
    project = tmp_path / "project"
    (project / ".omp").mkdir(parents=True)
    home = tmp_path / "home"  # sin ~/.omp/
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    assert detectar_host(cwd=project) == "omp_project"


def test_detectar_host_claude_code_cuando_existe_claude_mcp(tmp_path, monkeypatch):
    """Si ~/.claude/mcp/ existe, host = 'claude_code'."""
    home = tmp_path / "home"
    (home / ".claude" / "mcp").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    assert detectar_host() == "claude_code"


def test_detectar_host_project_cuando_existe_mcp_json_en_cwd(tmp_path, monkeypatch):
    """Si .mcp.json existe en cwd, host = 'project'."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {}}))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    assert detectar_host(cwd=project) == "project"


def test_detectar_host_unknown_si_no_hay_ninguno(tmp_path, monkeypatch):
    """Si no hay config de ningun host, retorna 'unknown'."""
    home = tmp_path / "empty_home"
    home.mkdir()
    cwd = tmp_path / "empty_cwd"
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))

    assert detectar_host(cwd=cwd) == "unknown"


# ─────────────────────────── generar_config ───────────────────────────


def test_generar_config_omp_usa_path_absoluto_y_args_correctos():
    """generar_config para OMP retorna mcpServers con command absoluto."""
    cfg = generar_config(
        host="omp",
        project_root=Path("/path/to/proj"),
        wrapper=Path("/abs/wrapper.sh"),
    )

    assert "mcpServers" in cfg
    assert "docpact" in cfg["mcpServers"]
    server = cfg["mcpServers"]["docpact"]
    assert server["command"] == "/abs/wrapper.sh"
    assert "--project-root" in server["args"]
    assert "/path/to/proj" in server["args"]
    # OMP format incluye $schema
    assert "$schema" in cfg


def test_generar_config_claude_code_usa_type_stdio():
    """generar_config para Claude Code retorna mcpServers con type=stdio."""
    cfg = generar_config(
        host="claude_code",
        project_root=Path("/path/to/proj"),
        wrapper=Path("/abs/wrapper.sh"),
    )

    server = cfg["mcpServers"]["docpact"]
    assert server["type"] == "stdio"
    assert server["command"] == "/abs/wrapper.sh"
    assert "mcp" in server["args"]  # CC wrapper-format: "mcp" subcommand


def test_generar_config_project_incluye_type_stdio():
    """generar_config para project-level usa el mismo formato que CC."""
    cfg = generar_config(
        host="project",
        project_root=Path("/path/to/proj"),
        wrapper=Path("/abs/wrapper.sh"),
    )

    server = cfg["mcpServers"]["docpact"]
    assert server["type"] == "stdio"
    assert server["command"] == "/abs/wrapper.sh"


# ─────────────────────────── escribir_config ───────────────────────────


def test_escribir_config_crea_archivo_en_target(tmp_path):
    """escribir_config debe crear el archivo con el contenido JSON correcto."""
    target = tmp_path / "mcp.json"
    cfg = {"mcpServers": {"docpact": {"command": "/x"}}}

    escribir_config(target, cfg)

    assert target.exists()
    assert json.loads(target.read_text()) == cfg


def test_escribir_config_crea_directorios_padre_si_faltan(tmp_path):
    """escribir_config crea directorios padre recursivamente."""
    target = tmp_path / "deep" / "nested" / "path" / "mcp.json"
    cfg = {"mcpServers": {}}

    escribir_config(target, cfg)

    assert target.exists()
    assert target.parent.exists()


# ─────────────────────────── verificar_wrapper ───────────────────────────


def test_verificar_wrapper_retorna_true_si_arranca_y_emite_starting(tmp_path):
    """Si el wrapper arranca y emite 'docpact MCP server v' en <3s, retorna True."""
    wrapper = tmp_path / "good_wrapper.sh"
    wrapper.write_text(
        "#!/bin/bash\necho '2026-06-04 [docpact.mcp] INFO: docpact MCP server v2 starting (stdio)'\nsleep 0.1\n"
    )
    wrapper.chmod(0o755)

    assert verificar_wrapper(wrapper, tmp_path) is True


def test_verificar_wrapper_retorna_false_si_no_existe(tmp_path):
    """Si el wrapper no existe, retorna False sin crashear."""
    nonexistent = tmp_path / "does_not_exist.sh"

    assert verificar_wrapper(nonexistent, tmp_path) is False


def test_verificar_wrapper_retorna_false_si_no_es_ejecutable(tmp_path):
    """Si el wrapper existe pero no es ejecutable, retorna False."""
    wrapper = tmp_path / "not_executable.sh"
    wrapper.write_text("#!/bin/bash\necho 'docpact MCP server'\n")
    # NO chmod

    assert verificar_wrapper(wrapper, tmp_path) is False


def test_verificar_wrapper_retorna_false_si_no_emite_senal_de_startup(tmp_path):
    """Si arranca pero no emite 'docpact MCP server', retorna False (probable error)."""
    wrapper = tmp_path / "broken_wrapper.sh"
    wrapper.write_text("#!/bin/bash\necho 'something else'\n")
    wrapper.chmod(0o755)

    assert verificar_wrapper(wrapper, tmp_path) is False


# ─────────────────────────── install_mcp (integracion) ───────────────────────────


def test_install_mcp_omp_escribe_en_omp_path_y_retorna_status(tmp_path, monkeypatch):
    """install_mcp(host='omp') escribe en ~/.omp/agent/mcp.json."""
    home = tmp_path / "home"
    (home / ".omp").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text("#!/bin/bash\necho 'docpact MCP server v2 starting (stdio)'\n")
    wrapper.chmod(0o755)
    project = tmp_path / "project"
    project.mkdir()

    result = install_mcp(
        project_root=project,
        wrapper=wrapper,
        host="omp",
    )

    assert result["host"] == "omp"
    assert result["config_path"] == home / ".omp" / "agent" / "mcp.json"
    assert result["config_path"].exists()
    assert result["wrapper_verified"] is True


def test_install_mcp_claude_code_escribe_en_claude_mcp_path(tmp_path, monkeypatch):
    """install_mcp(host='claude_code') escribe en ~/.claude/mcp/docpact.json."""
    home = tmp_path / "home"
    (home / ".claude" / "mcp").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text("#!/bin/bash\necho 'docpact MCP server v2 starting (stdio)'\n")
    wrapper.chmod(0o755)
    project = tmp_path / "project"
    project.mkdir()

    result = install_mcp(
        project_root=project,
        wrapper=wrapper,
        host="claude_code",
    )

    assert result["host"] == "claude_code"
    assert result["config_path"] == home / ".claude" / "mcp" / "docpact.json"
    assert result["config_path"].exists()


def test_install_mcp_falla_con_error_explicito_si_wrapper_no_anda(tmp_path, monkeypatch):
    """Si el wrapper no arranca, install_mcp retorna error claro, no crashea."""
    home = tmp_path / "home"
    (home / ".omp").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    wrapper = tmp_path / "broken.sh"
    wrapper.write_text("#!/bin/bash\necho 'not the right output'\n")
    wrapper.chmod(0o755)
    project = tmp_path / "project"
    project.mkdir()

    result = install_mcp(
        project_root=project,
        wrapper=wrapper,
        host="omp",
    )

    assert result["wrapper_verified"] is False
    assert "error" in result
    assert "wrapper" in result["error"].lower()
    # Y NO debe haber escrito el config (porque el wrapper no anda)
    assert not (home / ".omp" / "agent" / "mcp.json").exists()

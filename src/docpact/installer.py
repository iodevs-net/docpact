"""docpact.installer — CLI helper para instalar docpact como MCP server.

Detecta el host del agent (OMP, Claude Code) y escribe el config
correspondiente. Verifica que el wrapper arranca antes de escribir
para evitar dejar configs zombie si el wrapper esta roto.

Soporta:
- OMP user-level (~/.omp/agent/mcp.json)
- OMP project-level (.omp/mcp.json)
- Claude Code user-level (~/.claude/mcp/docpact.json)
- Claude Code project-level (.mcp.json)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

# Substring que el wrapper emite al arrancar (presente en el log
# de startup de docpact.mcp_server).
STARTUP_SIGNAL = "docpact MCP server"
STARTUP_TIMEOUT_SECONDS = 3.0


def detectar_host(
    home: Path | None = None,
    cwd: Path | None = None,
) -> str:
    """Detecta que host de agent esta instalado.

    Prioridad (mayor a menor):
    1. OMP user-level (~/.omp/)            → "omp"
    2. OMP project-level (./.omp/)         → "omp_project"
    3. Claude Code user-level              → "claude_code"
       (~/.claude/mcp/)
    4. Project-level (.mcp.json)           → "project"

    Returns:
        Uno de: "omp" | "omp_project" | "claude_code" | "project" | "unknown"
    """
    home = home or Path(os.environ.get("HOME", "~")).expanduser()
    cwd = cwd or Path.cwd()

    if (home / ".omp").is_dir():
        return "omp"
    if (cwd / ".omp").is_dir():
        return "omp_project"
    if (home / ".claude" / "mcp").is_dir():
        return "claude_code"
    if (cwd / ".mcp.json").is_file():
        return "project"

    return "unknown"


def generar_config(
    host: str,
    project_root: Path,
    wrapper: Path,
) -> dict[str, Any]:
    """Genera el dict de config MCP para el host dado.

    Args:
        host: uno de los valores retornados por detectar_host()
        project_root: path absoluto al proyecto (e.g. iodesk-3/)
        wrapper: path absoluto al wrapper script

    Returns:
        dict listo para serializar a JSON.
    """
    if host in ("omp", "omp_project"):
        return {
            "$schema": (
                "https://raw.githubusercontent.com/can1357/oh-my-pi/main/"
                "packages/coding-agent/src/config/mcp-schema.json"
            ),
            "mcpServers": {
                "docpact": {
                    "command": str(wrapper),
                    "args": ["--project-root", str(project_root)],
                }
            },
        }
    if host in ("claude_code", "project"):
        return {
            "mcpServers": {
                "docpact": {
                    "type": "stdio",
                    "command": str(wrapper),
                    "args": ["mcp", "--project-root", str(project_root)],
                }
            },
        }
    raise ValueError(f"host no soportado: {host}")


def escribir_config(target: Path, config: dict[str, Any]) -> None:
    """Escribe el config al path objetivo, creando directorios padre."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=2) + "\n")


def verificar_wrapper(wrapper: Path, project_root: Path) -> bool:
    """Verifica que el wrapper arranca y emite la senal de startup.

    Retorna True si:
    - Existe y es un archivo
    - Es ejecutable
    - Arranca en <STARTUP_TIMEOUT_SECONDS
    - Emite STARTUP_SIGNAL en stdout o stderr
    """
    if not wrapper.exists() or not wrapper.is_file():
        return False
    if not os.access(wrapper, os.X_OK):
        return False

    try:
        result = subprocess.run(
            [str(wrapper), "--project-root", str(project_root)],
            capture_output=True,
            text=True,
            timeout=STARTUP_TIMEOUT_SECONDS,
            input="",
        )
    except subprocess.TimeoutExpired as e:
        # El server sigue corriendo (espera JSON-RPC en stdin). La señal
        # de startup se emite ANTES de entrar al loop, asi que esta en
        # el output capturado por TimeoutExpired. Si esta, es OK.
        stdout = e.stdout or ""
        stderr = e.stderr or ""
        return STARTUP_SIGNAL in (stdout + stderr)
    except (FileNotFoundError, PermissionError, OSError):
        return False

    combined = (result.stdout or "") + (result.stderr or "")
    return STARTUP_SIGNAL in combined


def _config_path_for_host(host: str, project_root: Path, home: Path) -> Path | None:
    """Determina el path objetivo del config segun el host."""
    if host == "omp":
        return home / ".omp" / "agent" / "mcp.json"
    if host == "omp_project":
        return project_root / ".omp" / "mcp.json"
    if host == "claude_code":
        return home / ".claude" / "mcp" / "docpact.json"
    if host == "project":
        return project_root / ".mcp.json"
    return None


def install_mcp(
    project_root: Path,
    wrapper: Path,
    host: str,
) -> dict[str, Any]:
    """Pipeline principal: detecta, verifica, genera, escribe.

    Returns:
        dict con keys: host, config_path, wrapper_verified, error.
        Si wrapper_verified es False, error tiene la razon y
        config_path queda en None (no se escribio nada).
    """
    home = Path(os.environ.get("HOME", "~")).expanduser()

    # 1. Verificar wrapper primero (falla rapida, evita config zombie)
    if not verificar_wrapper(wrapper, project_root):
        return {
            "host": host,
            "config_path": None,
            "wrapper_verified": False,
            "error": (
                f"wrapper no arranca o no emite '{STARTUP_SIGNAL}': {wrapper}"
            ),
        }

    # 2. Determinar path objetivo
    target = _config_path_for_host(host, project_root, home)
    if target is None:
        return {
            "host": host,
            "config_path": None,
            "wrapper_verified": True,
            "error": f"host no soportado: {host}",
        }

    # 3. Generar y escribir
    config = generar_config(host, project_root, wrapper)
    escribir_config(target, config)

    return {
        "host": host,
        "config_path": target,
        "wrapper_verified": True,
        "error": None,
    }

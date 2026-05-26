"""MCP server para docpact — expone verificación de CONTRATOS como herramientas.

Cualquier agente (Claude Code, Cursor, etc.) puede llamar estas herramientas
sin pensar en comandos de terminal.

Protocolo: JSON-RPC 2.0 sobre stdio (MCP estándar).
Uso: python -m docpact.mcp_server
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _responder(id: Any, resultado: Any = None, error: Any = None) -> None:
    """Envía una respuesta JSON-RPC por stdout."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": id}
    if error:
        msg["error"] = {"code": -32000, "message": str(error)}
    else:
        msg["result"] = resultado
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _notificar(method: str, params: dict | None = None) -> None:
    """Envía una notificación (sin id, sin respuesta esperada)."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params:
        msg["params"] = params
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> None:
    """Loop principal del MCP server."""
    from docpact.api import check_file, check_proyecto, extract_contratos
    from docpact.config import DocpactConfig

    # Enviar inicialización
    _notificar("initialized")

    for line in sys.stdin:
        if not line.strip():
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {}) or {}

        try:
            if method == "initialize":
                _responder(req_id, {
                    "protocolVersion": "0.1.0",
                    "capabilities": {
                        "tools": {
                            "docpact_check": "Verifica CONTRATOS de un archivo o directorio",
                            "docpact_extract": "Extrae CONTRATOS de un archivo",
                            "docpact_score": "Calcula el score AI-Native del proyecto",
                        }
                    },
                })

            elif method == "tools/list":
                _responder(req_id, {
                    "tools": [
                        {
                            "name": "docpact_check",
                            "description": "Verifica CONTRATOS de un archivo Python. "
                                           "Retorna funciones, errores, warnings y score. "
                                           "Args: path (str), strict (bool, opcional).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {
                                        "type": "string",
                                        "description": "Ruta al archivo o directorio"
                                    },
                                    "strict": {
                                        "type": "boolean",
                                        "description": "Si True, falla si hay funciones sin CONTRATO"
                                    }
                                },
                                "required": ["path"]
                            }
                        },
                        {
                            "name": "docpact_extract",
                            "description": "Extrae todos los CONTRATOS de un archivo o directorio. "
                                           "Args: path (str), incluir_privadas (bool, opcional).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {
                                        "type": "string",
                                        "description": "Ruta al archivo o directorio"
                                    },
                                    "incluir_privadas": {
                                        "type": "boolean",
                                        "description": "Incluir funciones privadas"
                                    }
                                },
                                "required": ["path"]
                            }
                        },
                        {
                            "name": "docpact_score",
                            "description": "Calcula el score AI-Native del proyecto completo. "
                                           "Args: path (str). Return: score (int), nivel (str).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {
                                        "type": "string",
                                        "description": "Ruta al proyecto"
                                    }
                                },
                                "required": ["path"]
                            }
                        },
                    ]
                })

            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})

                if tool_name == "docpact_check":
                    path = arguments.get("path", "")
                    strict = arguments.get("strict", False)
                    config = DocpactConfig()
                    if strict:
                        config.strict = True
                    resultado = check_proyecto(path, config=config)
                    _responder(req_id, {
                        "total_funciones": resultado.total_funciones,
                        "funciones_con_contrato": resultado.funciones_con_contrato,
                        "errores": resultado.total_errores,
                        "warnings": resultado.total_warnings,
                        "score": resultado.calcular_score(),
                        "nivel": resultado.nivel,
                        "valido": resultado.total_errores == 0,
                        "detalle": [
                            {
                                "archivo": a.archivo,
                                "funciones": [
                                    {
                                        "nombre": f.nombre,
                                        "linea": f.linea,
                                        "valido": f.valido,
                                        "hallazgos": [
                                            {"tipo": h.tipo, "mensaje": h.mensaje,
                                             "sugerencia": h.sugerencia}
                                            for h in f.hallazgos
                                        ],
                                    }
                                    for f in a.funciones
                                ],
                            }
                            for a in resultado.archivos
                        ],
                    })

                elif tool_name == "docpact_extract":
                    path = arguments.get("path", "")
                    incluir_privadas = arguments.get("incluir_privadas", False)
                    contratos = extract_contratos(path, incluir_privadas=incluir_privadas)
                    _responder(req_id, contratos)

                elif tool_name == "docpact_score":
                    path = arguments.get("path", "")
                    config = DocpactConfig()
                    resultado = check_proyecto(path, config=config)
                    _responder(req_id, {
                        "score": resultado.calcular_score(),
                        "nivel": resultado.nivel,
                        "total_funciones": resultado.total_funciones,
                        "funciones_con_contrato": resultado.funciones_con_contrato,
                        "errores": resultado.total_errores,
                        "warnings": resultado.total_warnings,
                    })

                else:
                    _responder(req_id, error=f"Unknown tool: {tool_name}")

            elif method == "shutdown":
                _responder(req_id, None)
                break

        except Exception as e:
            _responder(req_id, error=str(e))


if __name__ == "__main__":
    main()

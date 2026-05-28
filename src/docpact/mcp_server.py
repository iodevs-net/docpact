"""MCP server para docpact — expone verificación de CONTRATOS como herramientas.

Protocolo: JSON-RPC 2.0 sobre stdio (MCP estándar).
Uso: docpact mcp
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

logger = logging.getLogger("docpact.mcp")
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


def _responder(id: Any, resultado: Any = None, error: Any = None) -> None:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": id}
    if error:
        msg["error"] = {"code": -32000, "message": str(error)}
    else:
        msg["result"] = resultado
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _notificar(method: str, params: dict | None = None) -> None:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params:
        msg["params"] = params
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _tool_result(data: dict) -> dict:
    """Wrap tool output in MCP CallToolResult format."""
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}

def main() -> int:
    """Loop principal del MCP server."""
    from docpact.api import check_file, check_proyecto, extract_contratos
    from docpact.config import DocpactConfig

    logger.info("docpact MCP server started (stdio)")
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

        # Notifications (no id) — no response needed per JSON-RPC spec
        if req_id is None:
            logger.debug("notification: %s", method)
            continue
        try:
            if method == "initialize":
                client_version = params.get("protocolVersion", "2024-11-05")
                _responder(
                    req_id,
                    {
                        "protocolVersion": client_version,
                        "capabilities": {"tools": {}},
                    },
                )

            elif method == "tools/list":
                _responder(
                    req_id,
                    {
                        "tools": [
                            {
                                "name": "docpact_check",
                                "description": "Verifica CONTRATOS de un archivo Python. "
                                "Retorna score, errores, warnings.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "path": {"type": "string"},
                                        "strict": {"type": "boolean"},
                                    },
                                    "required": ["path"],
                                },
                            },
                            {
                                "name": "docpact_extract",
                                "description": "Extrae CONTRATOS de un archivo o directorio.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "path": {"type": "string"},
                                        "incluir_privadas": {"type": "boolean"},
                                    },
                                    "required": ["path"],
                                },
                            },
                            {
                                "name": "docpact_score",
                                "description": "Score AI-Native del proyecto.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "path": {"type": "string"},
                                    },
                                    "required": ["path"],
                                },
                            },
                        ]
                    },
                )

            elif method == "tools/call":
                tool_name = params.get("name", "")
                args = params.get("arguments", {})

                if tool_name == "docpact_check":
                    r = check_proyecto(
                        args.get("path", ""), strict=args.get("strict", False)
                    )
                    _responder(
                        req_id,
                        _tool_result({
                            "valido": r.total_errores == 0,
                            "errores": r.total_errores,
                            "warnings": r.total_warnings,
                            "score": r.calcular_score(),
                            "nivel": r.nivel,
                            "total_funciones": r.total_funciones,
                            "funciones_con_contrato": r.funciones_con_contrato,
                        }),
                    )

                elif tool_name == "docpact_extract":
                    cs = extract_contratos(
                        args.get("path", ""),
                        incluir_privadas=args.get("incluir_privadas", False),
                    )
                    _responder(req_id, _tool_result(cs))

                elif tool_name == "docpact_score":
                    r = check_proyecto(args.get("path", ""))
                    _responder(
                        req_id,
                        _tool_result({
                            "score": r.calcular_score(),
                            "nivel": r.nivel,
                            "total_funciones": r.total_funciones,
                            "funciones_con_contrato": r.funciones_con_contrato,
                            "errores": r.total_errores,
                        }),
                    )

                else:
                    _responder(req_id, error=f"Unknown tool: {tool_name}")

            elif method == "shutdown":
                _responder(req_id, None)
                break

        except Exception as e:
            logger.error("Error processing request #%s (%s): %s", req_id, method, e)
            _responder(req_id, error=str(e))

    return 0


if __name__ == "__main__":
    main()

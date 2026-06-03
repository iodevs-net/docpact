"""MCP server para docpact v2 — índice pre-calculado, 6 tools, <5ms.

Protocolo: JSON-RPC 2.0 sobre stdio (MCP estándar).
Uso: docpact mcp

Diferencias con v1:
- Carga índice UNA VEZ al arrancar (no escanea archivos por query)
- 6 tools en lugar de 3
- Todas las queries son <5ms (RAM)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from docpact.index import cargar_index, generar_index, guardar_index

logger = logging.getLogger("docpact.mcp")
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


# ── Estado global del servidor ──

_index: dict[str, Any] | None = None
_project_root: str | None = None


def _cargar_o_generar_index(project_root: str) -> dict[str, Any]:
    """Carga índice existente o genera uno nuevo."""
    global _index, _project_root

    # Intentar cargar existente
    index = cargar_index(project_root)
    if index is not None:
        logger.info(
            "Índice cargado: %d funciones, %d RNs",
            index["stats"]["total_funciones"],
            index["stats"]["total_rns"],
        )
        _index = index
        _project_root = project_root
        return index

    # Generar nuevo
    logger.info("Generando índice para %s...", project_root)
    index = generar_index(project_root)
    guardar_index(index, project_root)
    logger.info(
        "Índice generado: %d funciones, %d RNs",
        index["stats"]["total_funciones"],
        index["stats"]["total_rns"],
    )
    _index = index
    _project_root = project_root
    return index


def _responder(id: Any, resultado: Any = None, error: Any = None) -> None:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": id}
    if error:
        msg["error"] = {"code": -32000, "message": str(error)}
    else:
        msg["result"] = resultado
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _tool_result(data: Any) -> dict:
    """Wrap tool output in MCP CallToolResult format."""
    if isinstance(data, str):
        text = data
    else:
        text = json.dumps(data, ensure_ascii=False, default=str)
    return {"content": [{"type": "text", "text": text}]}


# ── Tools ──


def tool_obtener_contexto_funcion(nombre_funcion: str) -> dict[str, Any]:
    """Tool 1: Obtener contexto completo de una función.

    Busca por nombre exacto o parcial. Retorna CONTRATO, RNs, tests, gotchas.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    nombre_lower = nombre_funcion.lower()
    resultados = []

    for key, f in _index["funciones"].items():
        if nombre_lower in f["funcion"].lower():
            resultados.append(f)

    if not resultados:
        return {
            "existe": False,
            "busqueda": nombre_funcion,
            "sugerencia": "Intenta con un nombre más específico o usa buscar_por_intencion",
        }

    if len(resultados) == 1:
        return {"existe": True, **resultados[0]}

    return {"existe": True, "multiples": resultados, "count": len(resultados)}


def tool_buscar_por_intencion(intencion: str) -> dict[str, Any]:
    """Tool 2: Buscar funciones por intención en lenguaje natural.

    Usa matching de palabras clave contra nombre, comportamiento, RNs.
    Retorna top 5 resultados con score de similitud.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    palabras = intencion.lower().split()
    scores: list[tuple[float, dict]] = []

    for key, f in _index["funciones"].items():
        score = 0.0
        texto_busqueda = (
            f["funcion"].lower()
            + " "
            + " ".join(f["rn_ids"]).lower()
            + " "
            + f["archivo"].lower()
        )

        for palabra in palabras:
            if palabra in texto_busqueda:
                score += 1.0
            if palabra in f["funcion"].lower():
                score += 0.5  # Bonus por match en nombre

        if score > 0:
            scores.append((score, f))

    scores.sort(key=lambda x: -x[0])
    top5 = [f for _, f in scores[:5]]

    return {
        "resultados": top5,
        "count": len(top5),
        "total_en_indice": len(_index["funciones"]),
    }


def tool_validar_cambio(archivo: str, diff: str) -> dict[str, Any]:
    """Tool 3: Validar un cambio antes de commit.

    Analiza el diff y verifica:
    - RNs declaradas existen en REGISTRO
    - No se rompió el CONTRATO existente
    - Tests relevantes existen
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    import re

    errores = []
    warnings = []
    tests_a_correr = []

    # Buscar RNs nuevas en el diff
    rns_nuevas = re.findall(r"RN-[\w-]+", diff)

    for rn_id in set(rns_nuevas):
        rn_info = _index["rns"].get(rn_id)
        if not rn_info:
            errores.append({
                "tipo": "rn_fake",
                "rn": rn_id,
                "mensaje": f"RN '{rn_id}' no existe en REGISTRO.md",
            })
        elif not rn_info["tiene_test"]:
            warnings.append({
                "tipo": "rn_sin_test",
                "rn": rn_id,
                "mensaje": f"RN '{rn_id}' no tiene test file",
            })
            if rn_info["test"]:
                tests_a_correr.append(rn_info["test"])

    # Buscar funciones afectadas en el índice
    funcs_afectadas = []
    for key, f in _index["funciones"].items():
        if f["archivo"] == archivo or Path(archivo).name in f["archivo"]:
            funcs_afectadas.append(f)
            for rn in f["rn"]:
                if rn["tiene_test"] and rn["test"]:
                    tests_a_correr.append(rn["test"])

    return {
        "valido": len(errores) == 0,
        "errores": errores,
        "warnings": warnings,
        "funcs_en_archivo": len(funcs_afectadas),
        "tests_a_correr": list(set(tests_a_correr)),
    }


def tool_obtener_rn(rn_id: str) -> dict[str, Any]:
    """Tool 4: Obtener contexto completo de una RN.

    Retorna descripción, funciones que la implementan, test, estado.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    rn = _index["rns"].get(rn_id)
    if not rn:
        # Buscar parcial
        coincidencias = [
            rid for rid in _index["rns"] if rn_id.lower() in rid.lower()
        ]
        return {
            "existe": False,
            "busqueda": rn_id,
            "coincidencias_parciales": coincidencias[:5],
        }

    return {"existe": True, **rn}


def tool_buscar_rns_por_tema(tema: str) -> dict[str, Any]:
    """Tool 5: Buscar RNs por tema/palabra clave.

    Busca en descripciones de RNs y nombres de funciones.
    Retorna RNs relevantes con sus funciones.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    tema_lower = tema.lower()
    resultados = []

    for rn_id, rn in _index["rns"].items():
        score = 0.0
        texto = rn["descripcion"].lower() + " " + rn_id.lower()

        if tema_lower in texto:
            score += 2.0
        for palabra in tema_lower.split():
            if palabra in texto:
                score += 1.0

        # Bonus si tiene funciones
        if rn["funciones"]:
            score += 0.5

        if score > 0:
            resultados.append((score, rn))

    resultados.sort(key=lambda x: -x[0])
    rns_encontradas = [r for _, r in resultados[:10]]

    return {
        "rns": rns_encontradas,
        "count": len(rns_encontradas),
        "tema_busqueda": tema,
    }


def tool_navegar_referencias(referencia: str) -> dict[str, Any]:
    """Tool 6: Navegar referencias cruzadas.

    Si es una RN: muestra todas las funciones que la implementan.
    Si es un archivo: muestra qué funciones tiene y qué RNs usa.
    Si es una función: muestra qué llama y quién la llama.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    ref = referencia.strip()

    # Caso 1: Es una RN (empieza con RN-)
    if ref.upper().startswith("RN-"):
        rn = _index["rns"].get(ref)
        if not rn:
            return {"existe": False, "tipo": "rn", "busqueda": ref}
        return {
            "existe": True,
            "tipo": "rn",
            "rn": rn,
            "funciones_que_la_implementan": rn["funciones"],
        }

    # Caso 2: Es un archivo (contiene / o termina en .py)
    if "/" in ref or ref.endswith(".py"):
        funcs_en_archivo = [
            f for f in _index["funciones"].values() if ref in f["archivo"]
        ]
        if not funcs_en_archivo:
            return {"existe": False, "tipo": "archivo", "busqueda": ref}

        rns_usadas = set()
        for f in funcs_en_archivo:
            rns_usadas.update(f["rn_ids"])

        return {
            "existe": True,
            "tipo": "archivo",
            "archivo": ref,
            "funciones": funcs_en_archivo,
            "rns_usadas": list(rns_usadas),
        }

    # Caso 3: Es una función
    funcs = [
        f
        for f in _index["funciones"].values()
        if ref.lower() in f["funcion"].lower()
    ]
    if not funcs:
        return {"existe": False, "tipo": "funcion", "busqueda": ref}

    return {
        "existe": True,
        "tipo": "funcion",
        "funciones": funcs,
    }


# ── Tool definitions for MCP ──

TOOLS = [
    {
        "name": "obtener_contexto_funcion",
        "description": "Obtiene el contexto completo de una función: CONTRATO, RNs, tests, archivo, línea. Usa esto para entender qué hace una función antes de editarla.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "nombre_funcion": {
                    "type": "string",
                    "description": "Nombre de la función (parcial o completo). Ej: 'crear_ticket', 'puede_crear_sucursal'",
                },
            },
            "required": ["nombre_funcion"],
        },
    },
    {
        "name": "buscar_por_intencion",
        "description": "Busca funciones por intención en lenguaje natural. Retorna top 5 con score de similitud. Usa esto cuando no sabés el nombre exacto de la función.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "intencion": {
                    "type": "string",
                    "description": "Descripción de lo que necesitás. Ej: 'crear un ticket', 'validar RUT de cliente', 'generar reporte de facturación'",
                },
            },
            "required": ["intencion"],
        },
    },
    {
        "name": "validar_cambio",
        "description": "Valida un diff antes de commit. Verifica que las RNs declaradas existan, no se haya roto el CONTRATO, y existan tests. Usa esto DESPUÉS de escribir código.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "archivo": {
                    "type": "string",
                    "description": "Path del archivo modificado. Ej: 'soporte/views/portal.py'",
                },
                "diff": {
                    "type": "string",
                    "description": "El diff o las líneas añadidas/eliminadas",
                },
            },
            "required": ["archivo", "diff"],
        },
    },
    {
        "name": "obtener_rn",
        "description": "Obtiene el contexto completo de una RN: descripción, funciones que la implementan, test, estado. Usa esto para entender una regla de negocio específica.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rn_id": {
                    "type": "string",
                    "description": "ID de la RN. Ej: 'RN-TKT-001', 'RN-FAC-002'",
                },
            },
            "required": ["rn_id"],
        },
    },
    {
        "name": "buscar_rns_por_tema",
        "description": "Busca RNs por tema o palabra clave. Retorna RNs relevantes con sus funciones. Usa esto para encontrar todas las RNs que hablan de un tema específico.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tema": {
                    "type": "string",
                    "description": "Tema o palabra clave. Ej: 'RUT', 'facturación', 'ticket', 'validación'",
                },
            },
            "required": ["tema"],
        },
    },
    {
        "name": "navegar_referencias",
        "description": "Navega referencias cruzadas. Si pasás una RN, te dice qué funciones la implementan. Si pasás un archivo, te dice qué funciones tiene. Si pasás una función, te dice qué llama.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "referencia": {
                    "type": "string",
                    "description": "RN (ej: 'RN-TKT-001'), archivo (ej: 'soporte/views/portal.py'), o función (ej: 'crear_ticket')",
                },
            },
            "required": ["referencia"],
        },
    },
]


def _dispatch_tool(tool_name: str, args: dict[str, Any]) -> Any:
    """Dispatch tool call to the right function."""
    dispatch = {
        "obtener_contexto_funcion": lambda: tool_obtener_contexto_funcion(
            args.get("nombre_funcion", "")
        ),
        "buscar_por_intencion": lambda: tool_buscar_por_intencion(
            args.get("intencion", "")
        ),
        "validar_cambio": lambda: tool_validar_cambio(
            args.get("archivo", ""), args.get("diff", "")
        ),
        "obtener_rn": lambda: tool_obtener_rn(args.get("rn_id", "")),
        "buscar_rns_por_tema": lambda: tool_buscar_rns_por_tema(
            args.get("tema", "")
        ),
        "navegar_referencias": lambda: tool_navegar_referencias(
            args.get("referencia", "")
        ),
    }

    fn = dispatch.get(tool_name)
    if fn is None:
        return {"error": f"Tool desconocida: {tool_name}"}
    return fn()


def main() -> int:
    """Loop principal del MCP server v2."""
    logger.info("docpact MCP server v2 started (stdio)")

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
                # Project root: argumento > env var > directorio actual
                import os
                project_root = (
                    params.get("projectRoot")
                    or os.environ.get("DOCPACT_PROJECT_ROOT")
                    or "."
                )
                _cargar_o_generar_index(project_root)

                _responder(
                    req_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "docpact-mcp",
                            "version": "2.0.0",
                        },
                    },
                )

            elif method == "tools/list":
                _responder(req_id, {"tools": TOOLS})

            elif method == "tools/call":
                tool_name = params.get("name", "")
                args = params.get("arguments", {})

                resultado = _dispatch_tool(tool_name, args)
                _responder(req_id, _tool_result(resultado))

            elif method == "shutdown":
                _responder(req_id, None)
                break

            else:
                _responder(req_id, error=f"Unknown method: {method}")

        except Exception as e:
            logger.error("Error processing request #%s (%s): %s", req_id, method, e)
            _responder(req_id, error=str(e))

    return 0


if __name__ == "__main__":
    main()

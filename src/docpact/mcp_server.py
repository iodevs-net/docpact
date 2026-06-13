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
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from docpact.index import (
    cargar_index,
    generar_index,
    guardar_index,
    _cosine_similarity,
    _try_load_embedder,
)

logger = logging.getLogger("docpact.mcp")
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


# ── Diagnóstico (usado por `docpact mcp-doctor` y al arrancar) ──


def diagnostico() -> dict[str, Any]:
    """Diagnóstico del entorno MCP — clave cuando el host no carga las tools.

    Retorna dict con: python_version, docpact_path, binary_in_PATH, cwd,
    project_root_env, index_path, index_exists. Sin secretos.
    """
    cwd = os.getcwd()
    return {
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "docpact_module_path": str(Path(__file__).resolve()),
        "docpact_in_PATH": shutil.which("docpact"),
        "cwd": cwd,
        "project_root_env": os.environ.get("DOCPACT_PROJECT_ROOT"),
        "index_path": str(Path(cwd) / ".docpact" / "index.json"),
        "index_exists": (Path(cwd) / ".docpact" / "index.json").exists(),
    }


def _log_startup_info() -> None:
    """Log de diagnóstico al arrancar — clave cuando el host MCP no carga tools."""
    diag = diagnostico()
    logger.info("docpact MCP server v2 starting (stdio)")
    logger.info("  Python:         %s", diag["python_version"])
    logger.info("  docpact path:   %s", diag["docpact_module_path"])
    logger.info("  docpact in PATH: %s", diag["docpact_in_PATH"] or "NOT FOUND")
    logger.info("  CWD:            %s", diag["cwd"])
    logger.info("  Project root:   %s", diag["project_root_env"] or "(CWD)")
    logger.info("  Index:          %s [%s]", diag["index_path"],
                "EXISTS" if diag["index_exists"] else "MISSING — run `docpact index`")


# ── Estado global del servidor ──

_index: dict[str, Any] | None = None
_project_root: str | None = None
_embedder: Any | None = None  # FastEmbed TextEmbedding (optional)


def _cargar_o_generar_index(project_root: str, force: bool = False) -> dict[str, Any]:
    """Carga índice existente o genera uno nuevo.

    Auto-regenera si el índice está obsoleto (más viejo que un .py modificado).
    Inicializa el embedder FastEmbed una sola vez.
    """
    global _index, _project_root, _embedder

    # Inicializar embedder una sola vez
    if _embedder is None:
        _embedder = _try_load_embedder()
        if _embedder is not None:
            logger.info("FastEmbed cargado: jina-embeddings-v2-base-es (búsqueda semántica habilitada)")
        else:
            logger.warning(
                "FastEmbed no instalado — detección de conflictos usa keywords (menos precisa). "
                "Instalar: pip install fastembed"
            )

    index_path = Path(project_root) / ".docpact" / "index.json"

    if not force and index_path.exists():
        index_mtime = index_path.stat().st_mtime

        # Buscar el .py más reciente del proyecto
        root = Path(project_root)
        latest_py = max(
            (f.stat().st_mtime for f in root.rglob("*.py")
             if not any(p in f.parts for p in ["__pycache__", ".venv", "venv", "node_modules", ".git", "migrations"])),
            default=0,
        )

        # Si el índice es más viejo que el .py más reciente, regenerar
        if latest_py > index_mtime:
            logger.info("Índice obsoleto, regenerando...")
            index = generar_index(project_root, embedder=_embedder)
            guardar_index(index, project_root)
            _index = index
            _project_root = project_root
            return index

    # Intentar cargar existente
    index = cargar_index(project_root)
    if index is not None:
        logger.info(
            "Índice cargado: %d funciones, %d RNs%s",
            index["stats"]["total_funciones"],
            index["stats"]["total_rns"],
            " (con embeddings)" if index["stats"].get("has_embeddings") else "",
        )
        _index = index
        _project_root = project_root
        return index

    # Generar nuevo
    logger.info("Generando índice para %s...", project_root)
    index = generar_index(project_root, embedder=_embedder)
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


def _limpiar_output(output: str) -> str:
    """Limpia output de pytest para mostrar solo lo relevante."""
    lineas = output.strip().split("\n")
    # Quitar warnings y líneas vacías
    relevantes = [
        l for l in lineas
        if l.strip()
        and not l.startswith("WARNING")
        and not l.startswith("=")
        and "hypothesis" not in l.lower()
        and "warnings summary" not in l.lower()
    ]
    return "\n".join(relevantes[-10:])  # Últimas 10 líneas relevantes


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

    Si hay embeddings disponibles, usa búsqueda semántica (cosine similarity)
    combinada con keyword matching (0.7 semántica + 0.3 keyword).
    Fallback a keyword-only si no hay embeddings.
    Retorna top 5 resultados con score de similitud.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    palabras = intencion.lower().split()
    embeddings = _index.get("embeddings")
    tiene_semantica = (
        embeddings is not None
        and embeddings.get("funciones")
        and _embedder is not None
    )

    scores: list[tuple[float, str, dict]] = []  # (score, key, func)

    for key, f in _index["funciones"].items():
        # ── Keyword score (original) ──
        kw_score = 0.0
        texto_busqueda = (
            f["funcion"].lower()
            + " "
            + " ".join(f["rn_ids"]).lower()
            + " "
            + f["archivo"].lower()
        )
        for palabra in palabras:
            if palabra in texto_busqueda:
                kw_score += 1.0
            if palabra in f["funcion"].lower():
                kw_score += 0.5

        if tiene_semantica:
            # ── Semantic score ──
            func_emb = embeddings["funciones"].get(key)
            if func_emb is not None and _embedder is not None:
                query_emb = list(_embedder.embed([intencion]))[0]
                sem_score = _cosine_similarity(
                    [float(x) for x in query_emb],
                    func_emb,
                )
                # Normalizar de [-1, 1] a [0, 1]
                sem_score = max(0.0, (sem_score + 1.0) / 2.0)
                # Combinar: 0.7 semántica + 0.3 keyword
                combined = 0.7 * sem_score + 0.3 * min(kw_score / 3.0, 1.0)
            else:
                combined = kw_score
        else:
            combined = kw_score

        if combined > 0 or kw_score > 0:
            scores.append((combined if tiene_semantica else kw_score, key, f))

    scores.sort(key=lambda x: -x[0])
    top5 = [(f, s) for s, _, f in scores[:5]]

    return {
        "resultados": [f for f, _ in top5],
        "scores": [round(s, 4) for _, s in top5],
        "busqueda_tipo": "semantica" if tiene_semantica else "keyword",
        "count": len(top5),
        "total_en_indice": len(_index["funciones"]),
    }


def tool_validar_cambio(archivo: str, diff: str, ejecutar_tests: bool = True) -> dict[str, Any]:
    """Tool 3: Validar un cambio antes de commit — ENFORCEMENT.

    Analiza el diff Y ejecuta tests relevantes.
    Si algún test falla, el cambio es INVÁLIDO.
    El agente NO puede commitar hasta que todo pase.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    import re
    import subprocess
    import os

    errores = []
    warnings = []
    tests_a_correr = []
    test_results = []

    # Buscar RNs nuevas en el diff
    rns_nuevas = re.findall(r"RN-[\w-]+", diff)

    for rn_id in set(rns_nuevas):
        rn_info = _index["rns"].get(rn_id)
        if not rn_info:
            errores.append({
                "tipo": "rn_fake",
                "rn": rn_id,
                "mensaje": f"RN '{rn_id}' no existe en REGISTRO.md",
                "accion": f"Quita '{rn_id}' del CONTRATO o agrégala a docs/reglas-del-negocio/REGISTRO.md",
            })
        elif not rn_info["tiene_test"]:
            warnings.append({
                "tipo": "rn_sin_test",
                "rn": rn_id,
                "mensaje": f"RN '{rn_id}' no tiene test file",
                "accion": f"Crea tests/rn/test_rn_{rn_id.replace('RN-', '')}.py con Hypothesis PBT",
            })
            if rn_info["test"]:
                tests_a_correr.append(rn_info["test"])

    # Buscar funciones afectadas en el índice (solo para info, no para tests)
    funcs_afectadas = []
    for key, f in _index["funciones"].items():
        if f["archivo"] == archivo or Path(archivo).name in f["archivo"]:
            funcs_afectadas.append(f)

    # Tests a correr: SOLO los de las RNs que aparecen en el diff
    tests_rn_especificos = []
    for rn_id in set(rns_nuevas):
        rn_info = _index["rns"].get(rn_id)
        if rn_info and rn_info.get("test"):
            tests_rn_especificos.append(rn_info["test"])

    tests_unicos = list(set(tests_rn_especificos))

    # ═══ ENFORCEMENT: ejecutar tests reales ═══
    # Solo ejecutar tests ESPECÍFICOS de las RNs en el diff,
    # usando filtro -k para no ejecutar tests no relacionados
    if ejecutar_tests and tests_unicos:
        project_root = _index.get("project_root", ".")

        # Agrupar tests por archivo y extraer filtro -k por RN
        tests_por_archivo: dict[str, set[str]] = {}
        for test_file in tests_unicos:
            test_path = Path(test_file)
            if not test_path.is_absolute():
                test_path = Path(project_root) / test_file

            if not test_path.exists():
                test_results.append({
                    "test": test_file,
                    "status": "SKIP",
                    "razon": "Archivo de test no encontrado",
                })
                continue

            try:
                rel_test = str(test_path.relative_to(project_root))
            except ValueError:
                rel_test = str(test_path)

            tests_por_archivo.setdefault(rel_test, set())

        # Extraer keywords de las RNs para filtro -k
        rn_keywords = []
        for rn_id in rns_nuevas:
            # RN-CL-001 → CL001, RN-TKT-003 → TKT003
            clean = rn_id.upper().replace("RN-", "").replace("-", "")
            rn_keywords.append(clean)

        # Construir filtro -k
        k_filter = " or ".join(rn_keywords) if rn_keywords else None

        for test_file_rel in tests_por_archivo:
            cmd = [
                sys.executable, "-m", "pytest",
                test_file_rel,
                "-q", "--no-header", "--tb=short",
                "-p", "no:cacheprovider",
                "-n", "0",  # Sin parallel para tests rápidos
            ]
            if k_filter:
                cmd.extend(["-k", k_filter])

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=project_root,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                )
                passed = result.returncode == 0
                test_results.append({
                    "test": test_file_rel,
                    "status": "PASS" if passed else "FAIL",
                    "output": result.stdout[-500:] if not passed else "",
                    "returncode": result.returncode,
                })
                if not passed:
                    errores.append({
                        "tipo": "test_fallido",
                        "test": test_file_rel,
                        "mensaje": f"Test {test_file_rel} FALLÓ — tu cambio rompió el comportamiento existente",
                        "output_limpio": _limpiar_output(result.stdout),
                        "accion": f"Lee el output del test y corrige tu código para que pase. El test verifica una RN real.",
                    })
            except subprocess.TimeoutExpired:
                test_results.append({
                    "test": test_file_rel,
                    "status": "TIMEOUT",
                    "razon": "Test excedió 30s",
                })
                errores.append({
                    "tipo": "test_timeout",
                    "test": test_file_rel,
                    "mensaje": f"Test {test_file_rel} excedió timeout — posible loop infinito o query lenta",
                    "accion": "Revisa tu código para asegurar que no hay queries N+1 o loops infinitos",
                })
            except Exception as e:
                test_results.append({
                    "test": test_file_rel,
                    "status": "ERROR",
                    "razon": str(e),
                })

    # Construir resumen accionable
    if errores:
        acciones = [e.get("accion", e["mensaje"]) for e in errores]
        resumen = f"BLOQUEADO: {len(errores)} error(es). Acciones:\n" + "\n".join(f"  {i+1}. {a}" for i, a in enumerate(acciones))
    else:
        resumen = "APROBADO: cambio válido, podés commitar"

    return {
        "valido": len(errores) == 0,
        "errores": errores,
        "warnings": warnings,
        "funcs_en_archivo": len(funcs_afectadas),
        "tests_a_correr": tests_unicos,
        "test_results": test_results,
        "resumen": resumen,
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

    Si hay embeddings, usa búsqueda semántica combinada con keyword.
    Fallback a keyword-only si no hay embeddings.
    Retorna RNs relevantes con sus funciones.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    tema_lower = tema.lower()
    embeddings = _index.get("embeddings")
    tiene_semantica = (
        embeddings is not None
        and embeddings.get("rns")
        and _embedder is not None
    )

    resultados: list[tuple[float, dict]] = []

    for rn_id, rn in _index["rns"].items():
        # ── Keyword score (original) ──
        kw_score = 0.0
        texto = rn["descripcion"].lower() + " " + rn_id.lower()

        if tema_lower in texto:
            kw_score += 2.0
        for palabra in tema_lower.split():
            if palabra in texto:
                kw_score += 1.0
        if rn["funciones"]:
            kw_score += 0.5

        if tiene_semantica:
            # ── Semantic score ──
            rn_emb = embeddings["rns"].get(rn_id)
            if rn_emb is not None and _embedder is not None:
                query_emb = list(_embedder.embed([tema]))[0]
                sem_score = _cosine_similarity(
                    [float(x) for x in query_emb],
                    rn_emb,
                )
                sem_score = max(0.0, (sem_score + 1.0) / 2.0)
                combined = 0.7 * sem_score + 0.3 * min(kw_score / 3.0, 1.0)
            else:
                combined = kw_score
        else:
            combined = kw_score

        if combined > 0 or kw_score > 0:
            resultados.append((combined if tiene_semantica else kw_score, rn))

    resultados.sort(key=lambda x: -x[0])
    rns_encontradas = [r for _, r in resultados[:10]]

    return {
        "rns": rns_encontradas,
        "count": len(rns_encontradas),
        "tema_busqueda": tema,
        "busqueda_tipo": "semantica" if tiene_semantica else "keyword",
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
        "description": (
            "Obtiene el contexto completo de una función: CONTRATO, RNs asociadas, tests, archivo y línea. "
            "Acepta nombre parcial (case-insensitive). Si hay múltiples coincidencias, retorna todas.\n\n"
            "EJEMPLO — Antes de editar una función:\n"
            "  Llamada: obtener_contexto_funcion(nombre_funcion='crear_ticket')\n"
            "  Retorna: {existe: true, funcion: 'crear_ticket', contrato: {...}, rn_ids: ['RN-TKT-001'], "
            "test: 'tests/test_tickets.py', archivo: 'soporte/services/tickets.py', linea: 42}\n\n"
            "EJEMPLO — Búsqueda parcial:\n"
            "  Llamada: obtener_contexto_funcion(nombre_funcion='ticket')\n"
            "  Retorna: {existe: true, multiples: [...], count: 3} (todas las funciones con 'ticket' en el nombre)"
        ),
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
        "description": (
            "Busca funciones por intención en lenguaje natural. Si FastEmbed está disponible, usa búsqueda semántica "
            "(cosine similarity + keyword matching: 0.7 semántica + 0.3 keyword). Fallback a keyword-only si no hay embeddings. "
            "Retorna top 5 resultados con score de similitud.\n\n"
            "EJEMPLO — No sabés el nombre exacto de la función:\n"
            "  Llamada: buscar_por_intencion(intencion='validar RUT de cliente')\n"
            "  Retorna: {resultados: [{funcion: 'validar_rut', ...}], scores: [0.8723], busqueda_tipo: 'semantica', count: 1}\n\n"
            "EJEMPLO — Buscar funciones de facturación:\n"
            "  Llamada: buscar_por_intencion(intencion='generar factura y enviar por email')\n"
            "  Retorna: {resultados: [{funcion: 'generar_factura', ...}, {funcion: 'enviar_factura_email', ...}], scores: [0.81, 0.65]}"
        ),
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
        "description": (
            "Valida un diff Y ejecuta tests relevantes antes de commit. Analiza RNs referenciadas en el diff "
            "(verifica que existan en REGISTRO.md) y ejecuta SOLO los tests de esas RNs usando filtro pytest -k. "
            "Si algún test falla, el cambio es INVÁLIDO y el agente NO puede commitar. Esto es ENFORCEMENT, no solo verificación.\n\n"
            "EJEMPLO — Validar antes de commitar un cambio en tickets:\n"
            "  Llamada: validar_cambio(\n"
            "    archivo='soporte/services/tickets.py',\n"
            "    diff='@@ -42,3 +42,5 @@\\n def crear_ticket(data):\\n+    if not data.get(\"prioridad\"):\\n"
            "+        raise ValueError(\"Prioridad requerida\")\\n     # RN-TKT-001: ...'\n"
            "  )\n"
            "  Retorna: {valido: true, errores: [], warnings: [], test_results: [{test: 'tests/test_tickets.py', status: 'PASS'}], "
            "resumen: 'APROBADO: cambio válido, podés commitar'}\n\n"
            "EJEMPLO — Cambio que rompe una RN (test falla):\n"
            "  Retorna: {valido: false, errores: [{tipo: 'test_fallido', test: 'tests/test_tickets.py', "
            "mensaje: 'Test tests/test_tickets.py FALLÓ — tu cambio rompió el comportamiento existente'}], "
            "resumen: 'BLOQUEADO: 1 error(es). Acciones: 1. Lee el output del test y corrige tu código'}\n\n"
            "EJEMPLO — Referencia a RN inexistente:\n"
            "  Retorna: {valido: false, errores: [{tipo: 'rn_fake', rn: 'RN-FAKE-999', "
            "mensaje: \"RN 'RN-FAKE-999' no existe en REGISTRO.md\"}]}"
        ),
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
                "ejecutar_tests": {
                    "type": "boolean",
                    "description": "Si True (default), ejecuta los tests relevantes. Si False, solo verifica existencia de RNs.",
                    "default": True,
                },
            },
            "required": ["archivo", "diff"],
        },
    },
    {
        "name": "obtener_rn",
        "description": (
            "Obtiene el contexto completo de una RN: descripción, funciones que la implementan, test asociado, y estado. "
            "Acepta ID parcial (retorna coincidencias). Usa esto para entender una regla de negocio específica.\n\n"
            "EJEMPLO — Ver detalle de una RN:\n"
            "  Llamada: obtener_rn(rn_id='RN-TKT-001')\n"
            "  Retorna: {existe: true, descripcion: 'Los tickets deben tener prioridad asignada', "
            "funciones: [{funcion: 'crear_ticket', archivo: 'tickets.py'}], tiene_test: true, test: 'tests/test_rn_TKT001.py'}\n\n"
            "EJEMPLO — Búsqueda parcial:\n"
            "  Llamada: obtener_rn(rn_id='TKT')\n"
            "  Retorna: {existe: false, busqueda: 'TKT', coincidencias_parciales: ['RN-TKT-001', 'RN-TKT-002']}"
        ),
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
        "description": (
            "Busca RNs por tema o palabra clave. Si FastEmbed está disponible, usa búsqueda semántica combinada "
            "(0.7 semántica + 0.3 keyword). Fallback a keyword-only. Retorna hasta 10 RNs relevantes con sus funciones.\n\n"
            "EJEMPLO — Buscar RNs relacionadas con validación:\n"
            "  Llamada: buscar_rns_por_tema(tema='validación RUT')\n"
            "  Retorna: {rns: [{id: 'RN-CL-001', descripcion: 'El RUT debe ser válido...', funciones: [...]}], "
            "count: 1, busqueda_tipo: 'semantica'}\n\n"
            "EJEMPLO — Explorar RNs de facturación:\n"
            "  Llamada: buscar_rns_por_tema(tema='facturación')\n"
            "  Retorna: {rns: [{id: 'RN-FAC-001', ...}, {id: 'RN-FAC-002', ...}], count: 2}"
        ),
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
        "description": (
            "Navega referencias cruzadas. Detecta automáticamente el tipo de referencia:\n"
            "- Si empieza con 'RN-': muestra funciones que implementan esa RN\n"
            "- Si contiene '/' o termina en '.py': muestra funciones del archivo y qué RNs usa\n"
            "- Siempre: muestra qué funciones coinciden y sus dependencias\n\n"
            "EJEMPLO — Ver qué funciones implementan una RN:\n"
            "  Llamada: navegar_referencias(referencia='RN-TKT-001')\n"
            "  Retorna: {tipo: 'rn', rn: {...}, funciones_que_la_implementan: [{funcion: 'crear_ticket'}, {funcion: 'editar_ticket'}]}\n\n"
            "EJEMPLO — Ver qué hay en un archivo:\n"
            "  Llamada: navegar_referencias(referencia='soporte/views/portal.py')\n"
            "  Retorna: {tipo: 'archivo', funciones: [{funcion: 'dashboard'}, {funcion: 'listar_tickets'}], rns_usadas: ['RN-TKT-001']}\n\n"
            "EJEMPLO — Buscar por nombre de función:\n"
            "  Llamada: navegar_referencias(referencia='crear_ticket')\n"
            "  Retorna: {tipo: 'funcion', funciones: [{funcion: 'crear_ticket', archivo: 'tickets.py', rn_ids: ['RN-TKT-001']}]}"
        ),
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
    {
        "name": "obtener_briefing",
        "description": (
            "Obtiene el briefing completo de reglas de negocio del proyecto. Lee esto ANTES de empezar a codear "
            "para entender qué debes respetar: RNs activas, side effects, zonas de riesgo. "
            "El briefing se auto-regenera cuando el código cambia (fingerprint-based cache).\n\n"
            "EJEMPLO — Inicio de sesión de trabajo:\n"
            "  Llamada: obtener_briefing()\n"
            "  Retorna: {briefing: '# Briefing DocPact\\n\\n## RNs Activas\\n- RN-TKT-001: ...', "
            "path: 'docs/briefing.md', updated: true}\n\n"
            "NO requiere parámetros. Llamar al inicio de cada sesión de coding."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "modificar_archivo",
        "description": (
            "Valida un cambio contra los CONTRATOs ANTES de aplicarlo. Analiza side effects declarados en los CONTRATOs "
            "y verifica que el diff no viole ninguna RN. Si el cambio viola side effects o RNs, lo RECHAZA con detalles. "
            "Usar SIEMPRE antes de modificar un archivo que tenga CONTRATOs.\n\n"
            "EJEMPLO — Validar cambio antes de aplicar:\n"
            "  Llamada: modificar_archivo(\n"
            "    archivo='soporte/services/tickets.py',\n"
            "    diff='def crear_ticket(data):\\n    # código nuevo que envía email\\n    send_email(to=data[\"email\"])'\n"
            "  )\n"
            "  Retorna: {allowed: true, message: 'Cambio válido', violations: []}\n\n"
            "EJEMPLO — Cambio que viola un CONTRATO:\n"
            "  Retorna: {allowed: false, message: 'Violación de CONTRATO', violations: [\n"
            "    {funcion: 'crear_ticket', tipo: 'side_effect_no_declarado', "
            "mensaje: \"Side effect 'email_send' no está en el CONTRATO\", sugerencia: \"Agregar 'email_send' al side_effects del CONTRATO\"}]}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "archivo": {
                    "type": "string",
                    "description": "Path del archivo a modificar. Ej: 'soporte/services/tickets.py'",
                },
                "diff": {
                    "type": "string",
                    "description": "El diff o código nuevo a aplicar",
                },
            },
            "required": ["archivo", "diff"],
        },
    },
    {
        "name": "listar_rns",
        "description": (
            "Lista TODAS las RNs del proyecto con descripción, funciones que las implementan, y estado (tiene test, "
            "está en registro). Útil para ver el panorama completo o responder preguntas del dueño de negocio.\n\n"
            "EJEMPLO — Ver todas las reglas:\n"
            "  Llamada: listar_rns()\n"
            "  Retorna: {rns: [{id: 'RN-TKT-001', descripcion: 'Tickets deben tener prioridad', "
            "funciones: ['crear_ticket'], tiene_test: true, en_registro: true}, ...], total: 12, con_test: 8, en_registro: 12}\n\n"
            "NO requiere parámetros. Usar cuando el dueño de negocio pregunte 'qué reglas hay' o necesites el panorama completo."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "verificar_conflicto",
        "description": (
            "Verifica si una nueva RN entrará en conflicto con las existentes. Detecta tres tipos de conflictos:\n"
            "1. Duplicados: descripción muy similar a una existente (similitud > 0.7)\n"
            "2. Mismo concepto: tema similar que podría chocar (similitud > 0.4)\n"
            "3. Overrides: afecta una función ya regulada por otra RN\n"
            "SIEMPRE usar ANTES de crear una RN nueva.\n\n"
            "EJEMPLO — Verificar antes de crear:\n"
            "  Llamada: verificar_conflicto(rn_descripcion='Los tickets deben tener prioridad asignada antes de 24 horas')\n"
            "  Retorna: {tiene_conflictos: true, conflictos: [{tipo: 'duplicado', rn_id: 'RN-TKT-001', "
            "similitud: 0.85, explicacion: 'La RN propuesta es muy similar a RN-TKT-001', "
            "accion: 'Revisá si es la misma regla. Si lo es, usá RN-TKT-001 en lugar de crear una nueva.'}], "
            "consejo: 'Encontré posibles conflictos. Revisá cada uno antes de crear la RN.'}\n\n"
            "EJEMPLO — Sin conflictos:\n"
            "  Retorna: {tiene_conflictos: false, conflictos: [], total_conflictos: 0, "
            "consejo: 'No detecté conflictos. Podés proceder a crear la RN.'}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rn_descripcion": {
                    "type": "string",
                    "description": "Descripción de la RN que querés crear. Ej: 'Los tickets deben tener prioridad asignada antes de 24 horas'",
                },
            },
            "required": ["rn_descripcion"],
        },
    },
    {
        "name": "crear_rn",
        "description": (
            "Crea una nueva RN en el REGISTRO.md. VALIDAR PRIMERO con verificar_conflicto para evitar duplicados. "
            "El agente DEBE confirmar con el usuario antes de ejecutar. El ID debe seguir el formato RN-[CATEGORIA]-[NUMERO]. "
            "Retorna la línea agregada y el siguiente paso (agregar la RN al CONTRATO de la función que la implementa).\n\n"
            "EJEMPLO — Crear una nueva regla de negocio:\n"
            "  Llamada: crear_rn(\n"
            "    rn_id='RN-FAC-003',\n"
            "    descripcion='Las facturas deben incluir IVA desglosado en la línea de detalle'\n"
            "  )\n"
            "  Retorna: {creada: true, rn_id: 'RN-FAC-003', descripcion: 'Las facturas deben incluir IVA...'\n"
            "    linea_agregada: '- **RN-FAC-003**: Las facturas deben incluir IVA desglosado...',\n"
            "    siguiente_paso: \"Agregar 'rn: [RN-FAC-003]' al CONTRATO de la función que la implementa.\"}\n\n"
            "EJEMPLO — ID ya existe:\n"
            "  Retorna: {error: \"La RN 'RN-TKT-001' ya existe.\", rn_existente: {...}, sugerencia: 'Usá obtener_rn para ver detalles'}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rn_id": {
                    "type": "string",
                    "description": "ID de la RN. Formato: RN-[CATEGORIA]-[NUMERO]. Ej: 'RN-TKT-001', 'RN-FAC-002'",
                },
                "descripcion": {
                    "type": "string",
                    "description": "Descripción clara de la regla de negocio. Ej: 'Los tickets deben ser respondidos en menos de 4 horas hábiles'",
                },
                "archivo_registro": {
                    "type": "string",
                    "description": "Ruta al REGISTRO.md (default: docs/reglas-del-negocio/REGISTRO.md)",
                    "default": "docs/reglas-del-negocio/REGISTRO.md",
                },
            },
            "required": ["rn_id", "descripcion"],
        },
    },
    {
        "name": "explicar_rn",
        "description": (
            "Explica una RN en lenguaje simple para el dueño de negocio. Traduce la regla técnica a lenguaje natural: "
            "qué regla define, quién la implementa, si tiene test (está verificada), y estado actual "
            "(COMPLETA/PARCIAL/PENDIENTE). Útil para reuniones con stakeholders.\n\n"
            "EJEMPLO — Explicar una regla para el dueño de negocio:\n"
            "  Llamada: explicar_rn(rn_id='RN-TKT-001')\n"
            "  Retorna: {existe: true, id: 'RN-TKT-001', "
            "que_es: 'Los tickets deben tener prioridad asignada', "
            "quien_la_implementa: ['crear_ticket', 'editar_ticket'], "
            "donde_vive: ['soporte/services/tickets.py'], "
            "tiene_test: true, estado: 'COMPLETA - Implementada y verificada con test', "
            "resumen_para_dueno: \"La regla 'RN-TKT-001' dice: Los tickets deben tener prioridad asignada. "
            "Está implementada en: crear_ticket, editar_ticket. Tiene test que la verifica.\"}\n\n"
            "EJEMPLO — RN pendiente de implementación:\n"
            "  Retorna: {..., estado: 'PENDIENTE - No hay código que la implemente', "
            "resumen_para_dueno: \"... Todavía no tiene código que la cumpla. No tiene test aún.\"}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rn_id": {
                    "type": "string",
                    "description": "ID de la RN a explicar. Ej: 'RN-TKT-001'",
                },
            },
            "required": ["rn_id"],
        },
    },
    {
        "name": "setup_docpact",
        "description": (
            "Inicializa docpact en un proyecto: crea docpact.toml (configuración), directorio docs/reglas-del-negocio/ "
            "con REGISTRO.md, genera index.json (índice de funciones y RNs), y verifica FastEmbed. "
            "Ejecutar una sola vez al inicio del proyecto.\n\n"
            "EJEMPLO — Setup inicial:\n"
            "  Llamada: setup_docpact(project_root='/home/user/mi-proyecto')\n"
            "  Retorna: {setup_completo: true, pasos: [\n"
            "    {paso: 'docpact.toml', estado: 'creado', path: '/home/user/mi-proyecto/docpact.toml'},\n"
            "    {paso: 'docs/reglas-del-negocio/', estado: 'creado'},\n"
            "    {paso: 'index.json', estado: 'generado', path: '...'},\n"
            "    {paso: 'fastembed', estado: 'ok'}],\n"
            "    siguiente_paso: 'Usar crear_contrato para agregar reglas de negocio'}\n\n"
            "EJEMPLO — Re-ejecución (idempotente):\n"
            "  Retorna: {setup_completo: true, pasos: [{paso: 'docpact.toml', estado: 'ya_existia'}, ...]}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Raíz del proyecto (default: directorio actual)",
                },
            },
        },
    },
    {
        "name": "crear_contrato",
        "description": (
            "Genera un CONTRATO para una función desde lenguaje natural. El CONTRATO es un docstring estructurado "
            "con input, output, side_effects y RNs asociadas. Retorna el docstring formateado listo para insertar. "
            "El agente debe confirmar con el usuario antes de escribir en el archivo.\n\n"
            "EJEMPLO — Generar CONTRATO para una función nueva:\n"
            "  Llamada: crear_contrato(\n"
            "    archivo='src/tickets.py',\n"
            "    funcion='crear_ticket',\n"
            "    side_effects=['db_write', 'email_send'],\n"
            "    rn=['RN-TKT-001'],\n"
            "    input_desc='Dict con titulo, prioridad, asignado_a',\n"
            "    output_desc='Ticket creado con ID'\n"
            "  )\n"
            "  Retorna: {contrato_generado: '    \"\"\"\\n    CONTRATO:\\n    input: Dict con titulo, prioridad, asignado_a\\n"
            "    output: Ticket creado con ID\\n    side_effects: [db_write, email_send]\\n    rn: [RN-TKT-001]\\n    \"\"\"', "
            "siguiente_paso: 'Agregar el CONTRATO al docstring de crear_ticket en src/tickets.py', "
            "instruccion_agente: 'Insertar el siguiente CONTRATO al inicio del docstring... Usar modificar_archivo para aplicar el cambio.'}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "archivo": {"type": "string", "description": "Path del archivo. Ej: 'src/tickets.py'"},
                "funcion": {"type": "string", "description": "Nombre de la función. Ej: 'crear_ticket'"},
                "side_effects": {"type": "array", "items": {"type": "string"}, "description": "Side effects. Ej: ['db_write', 'email_send']"},
                "rn": {"type": "array", "items": {"type": "string"}, "description": "RNs que aplica. Ej: ['RN-TKT-001']"},
                "input_desc": {"type": "string", "description": "Descripción del input"},
                "output_desc": {"type": "string", "description": "Descripción del output"},
            },
            "required": ["archivo", "funcion", "side_effects"],
        },
    },
    {
        "name": "corregir_contrato",
        "description": (
            "Analiza un CONTRATO con problemas y sugiere corrección. Lee el docstring actual de la función, "
            "lo muestra junto con el problema detectado, y da instrucciones para corregirlo. "
            "Útil cuando la verificación encuentra CONTRATOs desactualizados o incorrectos.\n\n"
            "EJEMPLO — Corregir side effects que no coinciden:\n"
            "  Llamada: corregir_contrato(\n"
            "    archivo='src/tickets.py',\n"
            "    funcion='crear_ticket',\n"
            "    problema='side_effects no coincide con implementación'\n"
            "  )\n"
            "  Retorna: {archivo: 'src/tickets.py', funcion: 'crear_ticket', "
            "problema_detectado: 'side_effects no coincide con implementación', "
            "docstring_actual: 'CONTRATO:\\n    input: ...\\n    side_effects: [db_write]\\n    ...', "
            "instruccion_agente: 'Revisar el CONTRATO de crear_ticket en src/tickets.py. "
            "Problema: side_effects no coincide con implementación. Usar modificar_archivo para aplicar la corrección.'}\n\n"
            "EJEMPLO — RN referenciada que ya no existe:\n"
            "  Llamada: corregir_contrato(archivo='src/facturas.py', funcion='emitir_factura', "
            "problema='RN-FAC-999 no existe en REGISTRO.md')"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "archivo": {"type": "string", "description": "Path del archivo"},
                "funcion": {"type": "string", "description": "Nombre de la función"},
                "problema": {"type": "string", "description": "Problema detectado. Ej: 'side_effects no coincide con implementación'"},
            },
            "required": ["archivo", "funcion", "problema"],
        },
    },
    {
        "name": "ejecutar_verificacion",
        "description": (
            "Ejecuta verificación completa de CONTRATOs en todo el proyecto. Analiza cada archivo Python, "
            "verifica que los CONTRATOs sean correctos (side effects declarados, RNs válidas, formato correcto), "
            "y retorna errores, warnings y un score de calidad (0-100).\n\n"
            "EJEMPLO — Verificar todo el proyecto:\n"
            "  Llamada: ejecutar_verificacion()\n"
            "  Retorna: {ejecutado: true, total_funciones: 45, funciones_con_contrato: 38, "
            "total_errores: 2, total_warnings: 5, score: 84, nivel: 'B', "
            "errores: [{archivo: 'tickets.py', funcion: 'crear_ticket', mensaje: 'side_effect email_send no declarado'}], "
            "warnings: [{archivo: 'facturas.py', funcion: 'emitir', mensaje: 'RN-FAC-003 no tiene test'}]}\n\n"
            "EJEMPLO — Verificar un proyecto específico:\n"
            "  Llamada: ejecutar_verificacion(project_root='/home/user/mi-proyecto')"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string", "description": "Raíz del proyecto (default: directorio actual)"},
            },
        },
    },
    {
        "name": "ejecutar_tests",
        "description": (
            "Ejecuta tests de Reglas de Negocio con pytest (tests/ directory, -x para stop on first failure, "
            "-q para output conciso). Retorna si pasaron o fallaron con el output relevante. "
            "Útil para verificar que los cambios no rompen RNs existentes.\n\n"
            "EJEMPLO — Ejecutar todos los tests:\n"
            "  Llamada: ejecutar_tests()\n"
            "  Retorna: {ejecutado: true, exito: true, output: '45 passed in 3.2s', return_code: 0}\n\n"
            "EJEMPLO — Tests con fallos:\n"
            "  Retorna: {ejecutado: true, exito: false, output: 'FAILED tests/test_tickets.py::test_crear_ticket_sin_prioridad', "
            "return_code: 1}\n\n"
            "EJEMPLO — Ejecutar tests de otro proyecto:\n"
            "  Llamada: ejecutar_tests(project_root='/home/user/otro-proyecto')"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string", "description": "Raíz del proyecto (default: directorio actual)"},
            },
        },
    },
    {
        "name": "generar_reporte",
        "description": (
            "Genera reporte de reglas de negocio del proyecto: total de RNs, cuántas tienen código implementado, "
            "cuántas tienen test, y detalle de cada RN. Útil para dashboards, reuniones de estado, o auditorías.\n\n"
            "EJEMPLO — Reporte completo:\n"
            "  Llamada: generar_reporte()\n"
            "  Retorna: {generado: true, total_rns: 12, rns_con_codigo: 10, rns_con_test: 8, "
            "rns_sin_codigo: 2, resumen: '12 RNs totales, 10 con código, 8 con test', "
            "rns: [{id: 'RN-TKT-001', descripcion: '...', tiene_codigo: true, tiene_test: true, en_registro: true}, ...]}\n\n"
            "EJEMPLO — Reporte de otro proyecto:\n"
            "  Llamada: generar_reporte(project_root='/home/user/mi-proyecto')"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string", "description": "Raíz del proyecto (default: directorio actual)"},
            },
        },
    },
    {
        "name": "explicar_errores",
        "description": (
            "Traduce errores técnicos de docpact a lenguaje simple para el dueño de negocio.\n"
            "Retorna: diagnóstico general, errores por urgencia, y para cada error:\n"
            "- título: qué está mal (1 línea)\n"
            "- qué_pasa: explicación simple\n"
            "- por_qué_importa: por qué debería importarle\n"
            "- cómo_arreglar: pasos concretos\n\n"
            "EJEMPLO — Errores encontrados:\n"
            "  Llamada: explicar_errores()\n"
            "  Retorna: {diagnostico: 'Hay 3 problemas urgentes', total_errores: 3,\n"
            "    por_urgencia: {alta: 3, media: 0, baja: 0},\n"
            "    detalles: {alta: [{titulo: 'Efecto no declarado en crear_ticket',\n"
            "      que_pasa: 'crear_ticket escribe en la BD pero dice que no tiene efectos',\n"
            "      por_que_importa: 'No se puede verificar si se cumple la regla',\n"
            "      como_arreglar: 'Agregá db_write al side_effects del docstring'}]}}\n\n"
            "EJEMPLO — Sin errores:\n"
            "  Llamada: explicar_errores()\n"
            "  Retorna: {diagnostico: 'Todo está en buen estado', total_errores: 0}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Raíz del proyecto (default: directorio actual)",
                },
            },
        },
    },
    {
        "name": "descubrir_reglas",
        "description": (
            "Analiza el código y descubre reglas de negocio potenciales que no están declaradas.\n"
            "Detecta patrones como validaciones, permisos, side effects, transiciones de estado.\n"
            "Útil para encontrar reglas que los desarrolladores olvidaron formalizar.\n\n"
            "EJEMPLO — Reglas descubiertas:\n"
            "  Llamada: descubrir_reglas()\n"
            "  Retorna: {archivos_escaneados: 50, reglas_encontradas: 23,\n"
            "    por_tipo: {validacion: 8, permiso: 5, negocio: 6, auditoria: 4},\n"
            "    por_confianza: {alta: 12, media: 8, baja: 3},\n"
            "    reglas: [{tipo: 'validacion', titulo: 'Validación de entrada detectada',\n"
            "      evidencia: 'if not cliente: raise ValueError',\n"
            "      archivo: 'clientes/services.py', linea: 45, confianza: 'alta',\n"
            "      sugerencia: 'Formalizar como CONTRATO con campo borde'}]}\n\n"
            "EJEMPLO — Escanear directorio específico:\n"
            "  Llamada: descubrir_reglas(project_root='/home/user/mi-proyecto')"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Raíz del proyecto (default: directorio actual)",
                },
            },
        },
    },
    {
        "name": "extraer_rns",
        "description": (
            "Analiza un proyecto y extrae reglas de negocio implícitas.\n"
            "Útil para: migrar proyectos existentes, crear librería de RNs por industria,\n"
            "extraer RNs de repos open-source.\n\n"
            "EJEMPLO — Extraer de proyecto actual:\n"
            "  Llamada: extraer_rns()\n"
            "  Retorna: {archivos_escaneados: 50, rns_encontradas: 120,\n"
            "    categorias: ['auth', 'ticket', 'notification'],\n"
            "    rns_sugeridas: [{categoria: 'auth', cantidad_evidencias: 25,\n"
            "      titulo_sugerido: 'RN-AUTH-001',\n"
            "      descripcion_sugerida: 'Regla de auth detectada en 25 lugares'}]}\n\n"
            "EJEMPLO — Extraer de repo externo:\n"
            "  Llamada: extraer_rns(project_root='/path/to/external-repo')"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Raíz del proyecto a analizar (default: directorio actual)",
                },
            },
        },
    },
    {
        "name": "predecir_bugs",
        "description": (
            "Analiza código y predice bugs potenciales usando AST.\n"
            "Detecta: mutable defaults, bare except, resource leaks, variables sin usar.\n\n"
            "EJEMPLO — Bugs encontrados:\n"
            "  Llamada: predecir_bugs()\n"
            "  Retorna: {archivos_escaneados: 50, total_bugs: 23,\n"
            "    por_severidad: {error: 2, warning: 15, info: 6},\n"
            "    por_tipo: {mutable_default: 8, bare_except: 5, resource_leak: 3},\n"
            "    bugs: [{tipo: 'mutable_default', severidad: 'warning',\n"
            "      mensaje: 'Argumento default mutable en crear_ticket',\n"
            "      sugerencia: 'Usar None como default',\n"
            "      archivo: 'tickets.py', linea: 45}]}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Raíz del proyecto (default: directorio actual)",
                },
            },
        },
    },
]


def tool_obtener_briefing() -> dict[str, Any]:
    """Tool 7: Obtener el briefing de reglas de negocio del proyecto.

    Retorna el briefing completo. El briefing se auto-actualiza
    cuando el código cambia (fingerprint-based cache).
    Usa esto para entender el contexto del proyecto ANTES de codear.
    """
    import os
    project_root = os.environ.get("DOCPACT_PROJECT_ROOT", ".")
    from docpact.briefing import generar_briefing, leer_briefing

    briefing_path, fue_regenerado = generar_briefing(project_root)
    contenido = leer_briefing(project_root)

    if contenido is None:
        return {"error": "No se pudo generar el briefing"}

    return {
        "briefing": contenido,
        "path": str(briefing_path),
        "updated": fue_regenerado,
    }

def tool_modificar_archivo(archivo: str, diff: str) -> dict[str, Any]:
    """Tool 8: Valida un cambio y verifica en tiempo real.

    Pipeline:
    1. Valida contra CONTRATOs (guard)
    2. Si hay violaciones, retorna error
    3. Si está OK, sugiere verificar con explicar_errores
    """
    import os
    project_root = os.environ.get("DOCPACT_PROJECT_ROOT", ".")
    from docpact.guard import validar_cambio

    resultado = validar_cambio(archivo, diff, project_root)

    respuesta = {
        "allowed": resultado.allowed,
        "message": resultado.message,
        "violaciones": [
            {"funcion": v.funcion, "tipo": v.tipo, "mensaje": v.mensaje, "sugerencia": v.sugerencia}
            for v in resultado.violations
        ],
        "total_violaciones": len(resultado.violations),
    }

    if resultado.allowed:
        respuesta["siguiente_paso"] = (
            "El cambio está permitido. Después de aplicarlo, "
            "usá explicar_errores para verificar que todo esté bien."
        )
    else:
        respuesta["instruccion_agente"] = (
            f"El cambio tiene {len(resultado.violations)} violación(es). "
            "No apliques el cambio hasta resolverlas."
        )

    return respuesta
def tool_listar_rns() -> dict[str, Any]:
    """Tool 9: Lista todas las RNs del proyecto con sus descripciones.

    Retorna lista completa de RNs: ID, descripción, funciones que la implementan,
    si tiene test, y si está en el registro. Útil para que el dueño de negocio
    vea qué reglas existen.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    rns = []
    for rn_id, rn in sorted(_index["rns"].items()):
        rns.append({
            "id": rn_id,
            "descripcion": rn["descripcion"],
            "funciones": [f["funcion"] for f in rn.get("funciones", [])],
            "tiene_test": rn.get("tiene_test", False),
            "en_registro": rn.get("en_registro", False),
        })

    return {
        "rns": rns,
        "total": len(rns),
        "con_test": sum(1 for r in rns if r["tiene_test"]),
        "en_registro": sum(1 for r in rns if r["en_registro"]),
    }


def _calcular_similitud(a: str, b: str) -> float:
    """Calcula similitud entre dos strings.

    Usa FastEmbed embeddings si está disponible (similitud semántica real).
    Fallback a keywords compartidas si no hay embedder.

    Returns: Score entre 0 y 1. Mayor = más similar.
    """
    # Intentar con FastEmbed si está disponible
    if _embedder is not None:
        try:
            import math
            from docpact.index import _cosine_similarity

            embeddings = list(_embedder.embed([a, b]))
            if len(embeddings) == 2:
                sim = _cosine_similarity(
                    [float(x) for x in embeddings[0]],
                    [float(x) for x in embeddings[1]],
                )
                # Normalizar de [-1, 1] a [0, 1]
                return max(0.0, (sim + 1.0) / 2.0)
        except Exception:
            pass  # Fallback a keywords

    # Fallback: similitud por keywords compartidas
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    stopwords = {"el", "la", "los", "las", "un", "una", "de", "del", "en", "que", "y", "o", "para", "por", "con", "sin", "no", "si", "se", "al", "es", "son", "ha", "hay", "como", "más", "menos", "todo", "toda", "este", "esta", "ese", "esa"}
    words_a -= stopwords
    words_b -= stopwords

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def tool_verificar_conflicto(rn_descripcion: str) -> dict[str, Any]:
    """Tool 10: Verifica conflictos y retorna evidencia para que el agente decida.

    Pipeline híbrido:
    1. Embeddings → candidatos por similitud semántica
    2. Glosario → expandir sinónimos del dominio
    3. Cross-reference → verificar si afectan mismas funciones
    4. Agente (LLM) → interpreta evidencia y decide

    El tool NO decide — el tool provee evidencia. El agente decide.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    # Cargar glosario de sinónimos
    sinonimos = _cargar_glosario()
    rn_expandida = _expandir_con_sinonimos(rn_descripcion, sinonimos)

    conflictos = []
    desc_lower = rn_descripcion.lower()

    for rn_id, rn in _index["rns"].items():
        # 1. Similitud semántica (embeddings)
        similitud = _calcular_similitud(rn_expandida, rn["descripcion"])

        # 2. Sinónimos: expandir la RN existente también
        rn_expandida_existente = _expandir_con_sinonimos(rn["descripcion"], sinonimos)
        similitud_expandida = _calcular_similitud(rn_expandida, rn_expandida_existente)
        similitud_final = max(similitud, similitud_expandida)

        # 3. Cross-reference: misma función afectada
        funcs_propuesta = _extraer_funciones_mencionadas(rn_expandida)
        funcs_existente = set()
        for f in rn.get("funciones", []):
            funcs_existente.add(f.get("funcion", "").lower())
        funcs_compartidas = funcs_propuesta & funcs_existente

        # Construir evidencia
        evidencia = {
            "rn_id": rn_id,
            "descripcion_existente": rn["descripcion"],
            "similitud_embeddings": round(similitud, 3),
            "similitud_con_sinonimos": round(similitud_expandida, 3),
            "similitud_final": round(similitud_final, 3),
            "funcs_propuesta": list(funcs_propuesta),
            "funcs_existente": list(funcs_existente),
            "funcs_compartidas": list(funcs_compartidas),
            "tiene_rn": rn.get("tiene_rn", False),
            "rn_ids": rn.get("rn_ids", []),
        }

        # Solo reportar si hay señal de conflicto
        if similitud_final > 0.3 or funcs_compartidas:
            evidencia["tipo_señal"] = []
            if similitud_final > 0.7:
                evidencia["tipo_señal"].append("duplicado_potencial")
            elif similitud_final > 0.4:
                evidencia["tipo_señal"].append("mismo_concepto")
            elif similitud_final > 0.3:
                evidencia["tipo_señal"].append("tema_similar")
            if funcs_compartidas:
                evidencia["tipo_señal"].append("misma_funcion")

            conflictos.append(evidencia)

    # Resumen para el agente
    return {
        "tiene_conflictos": len(conflictos) > 0,
        "total_conflictos": len(conflictos),
        "descripcion_evaluada": rn_descripcion,
        "glosario_aplicado": bool(sinonimos),
        "conflictos": sorted(conflictos, key=lambda x: x["similitud_final"], reverse=True),
        "instruccion_agente": (
            "Usá esta evidencia para decidir si hay conflicto real. "
            "Considerá: similitud > 0.7 = probable duplicado, "
            "similitud > 0.4 = mismo concepto, "
            "funcs compartidas = override potencial. "
            "El tool NO decide — VOS decidís."
        ),
    }


def _cargar_glosario() -> dict[str, list[str]]:
    """Carga glosario de sinónimos desde docpact.toml."""
    import tomllib
    from pathlib import Path

    config_path = Path("docpact.toml")
    if not config_path.exists():
        return {}

    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        return config.get("synonyms", {})
    except Exception:
        return {}


def _expandir_con_sinonimos(texto: str, sinonimos: dict[str, list[str]]) -> str:
    """Expande palabras en el texto usando sinónimos del glosario."""
    if not sinonimos:
        return texto

    resultado = texto.lower()
    for termino, sins in sinonimos.items():
        for sin in sins:
            if sin.lower() in resultado:
                resultado = resultado.replace(sin.lower(), termino.lower())
    return resultado


def _extraer_funciones_mencionadas(texto: str) -> set[str]:
    """Extrae nombres de funciones mencionadas en el texto."""
    import re
    # Buscar patrones como crear_ticket, enviar_email, etc.
    patron = r'\b([a-z_]+(?:_[a-z]+)+)\b'
    return set(re.findall(patron, texto.lower()))


def tool_crear_rn(rn_id: str, descripcion: str, archivo_registro: str = "docs/reglas-del-negocio/REGISTRO.md") -> dict[str, Any]:
    """Tool 11: Crea una nueva RN en el REGISTRO.md.

    Agrega la RN al registro y retorna la línea agregada.
    El agente debe confirmar con el usuario antes de ejecutar.
    Primero usar verificar_conflicto para validar.
    """
    import re
    from pathlib import Path

    if _index is None:
        return {"error": "Índice no cargado"}

    # Validar formato del ID
    if not re.match(r"^RN-[\w-]+$", rn_id):
        return {
            "error": f"Formato de ID inválido: '{rn_id}'. Debe ser 'RN-XXX' (ej: RN-TKT-001, RN-FAC-002)",
            "formato_esperado": "RN-[CATEGORIA]-[NUMERO]",
        }

    # Verificar que no exista
    if rn_id in _index["rns"]:
        return {
            "error": f"La RN '{rn_id}' ya existe.",
            "rn_existente": _index["rns"][rn_id],
            "sugerencia": "Usá obtener_rn para ver los detalles, o elegí otro ID.",
        }

    # Construir línea para REGISTRO.md
    linea = f"- **{rn_id}**: {descripcion}"

    # Escribir al archivo
    registro_path = Path(archivo_registro)
    if not registro_path.exists():
        registro_path.parent.mkdir(parents=True, exist_ok=True)
        registro_path.write_text(f"# Registro de Reglas de Negocio\n\n{linea}\n", encoding="utf-8")
    else:
        with open(registro_path, "a", encoding="utf-8") as f:
            f.write(f"\n{linea}")

    return {
        "creada": True,
        "rn_id": rn_id,
        "descripcion": descripcion,
        "archivo": str(registro_path),
        "linea_agregada": linea,
        "siguiente_paso": f"Agregar 'rn: [{rn_id}]' al CONTRATO de la función que la implementa.",
    }


def tool_explicar_rn(rn_id: str) -> dict[str, Any]:
    """Tool 12: Explica una RN en lenguaje simple para el dueño de negocio.

    Toma una RN técnica y la traduce a:
    - Qué regla define (en lenguaje simple)
    - Qué código la implementa
    - Si tiene test (está verificada)
    - Estado: completa o necesita implementación
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
            "sugerencia": "Verificá el ID. Podés usar listar_rns para ver todas las disponibles.",
        }

    # Construir explicación simple
    funcs = rn.get("funciones", [])
    funcs_nombres = [f["funcion"] for f in funcs]

    # Determinar estado
    if not funcs:
        estado = "PENDIENTE - No hay código que la implemente"
        estado_emoji = "⏳"
    elif rn.get("tiene_test"):
        estado = "COMPLETA - Implementada y verificada con test"
        estado_emoji = "✅"
    else:
        estado = "PARCIAL - Implementada pero sin test de verificación"
        estado_emoji = "⚠️"

    return {
        "existe": True,
        "id": rn_id,
        "que_es": rn["descripcion"],
        "quien_la_implementa": funcs_nombres if funcs else ["Nadie aún"],
        "donde_vive": [f["archivo"] for f in funcs] if funcs else [],
        "tiene_test": rn.get("tiene_test", False),
        "test_file": rn.get("test"),
        "estado": estado,
        "resumen_para_dueno": (
            f"La regla '{rn_id}' dice: {rn['descripcion']}. "
            f"{'Está implementada en: ' + ', '.join(funcs_nombres) + '.' if funcs else 'Todavía no tiene código que la cumpla.'} "
            f"{'Tiene test que la verifica.' if rn.get('tiene_test') else 'No tiene test aún.'}"
        ),
    }

def tool_setup_docpact(project_root: str | None = None) -> dict[str, Any]:
    """Tool 13: Inicializa docpact en un proyecto.

    Crea docpact.toml, genera index.json, verifica que todo esté listo.
    Ejecutar una sola vez al inicio del proyecto.
    """
    import os
    root = project_root or os.environ.get("DOCPACT_PROJECT_ROOT", ".")
    root_path = Path(root)

    result = {"pasos": [], "errores": []}

    # 1. Crear docpact.toml si no existe
    config_path = root_path / "docpact.toml"
    if not config_path.exists():
        config_content = f'''# docpact configuration
[project]
name = "{root_path.name}"

[rules]
# Add RN pattern rules here
'''
        config_path.write_text(config_content, encoding="utf-8")
        result["pasos"].append({"paso": "docpact.toml", "estado": "creado", "path": str(config_path)})
    else:
        result["pasos"].append({"paso": "docpact.toml", "estado": "ya_existia"})

    # 2. Crear directorio de docs si no existe
    docs_dir = root_path / "docs" / "reglas-del-negocio"
    if not docs_dir.exists():
        docs_dir.mkdir(parents=True, exist_ok=True)
        registro = docs_dir / "REGISTRO.md"
        registro.write_text("# Registro de Reglas de Negocio\n", encoding="utf-8")
        result["pasos"].append({"paso": "docs/reglas-del-negocio/", "estado": "creado"})
    else:
        result["pasos"].append({"paso": "docs/reglas-del-negocio/", "estado": "ya_existia"})

    # 3. Generar index
    try:
        from docpact.index import generar_index, guardar_index
        index = generar_index(str(root_path))
        path = guardar_index(index, str(root_path))
        result["pasos"].append({"paso": "index.json", "estado": "generado", "path": str(path)})
    except Exception as e:
        result["errores"].append({"paso": "index.json", "error": str(e)})

    # 4. Verificar FastEmbed
    try:
        from docpact.checker.doctor import check_fastembed
        check = check_fastembed()
        result["pasos"].append({"paso": "fastembed", "estado": "ok" if check.estado else "falta", "mensaje": check.mensaje})
    except Exception:
        result["pasos"].append({"paso": "fastembed", "estado": "no_verificado"})

    return {
        "setup_completo": len(result["errores"]) == 0,
        "pasos": result["pasos"],
        "errores": result["errores"],
        "siguiente_paso": "Usar crear_contrato para agregar reglas de negocio",
    }


def tool_crear_contrato(
    descripcion_nl: str,
    archivo: str | None = None,
    funcion: str | None = None,
) -> dict[str, Any]:
    """Tool 14: Sugiere un CONTRATO desde lenguaje natural.

    El dueño dice QUÉ quiere en lenguaje simple.
    El tool sugiere cómo se vería el CONTRATO.
    El agente completa los detalles y confirma con el usuario.
    """
    from pathlib import Path

    # Analizar la descripción para sugerir campos
    desc_lower = descripcion_nl.lower()

    # Detectar side effects
    side_effects_sugeridos = []
    if any(w in desc_lower for w in ["enviar", "email", "correo", "notificar", "mail"]):
        side_effects_sugeridos.append("email")
    if any(w in desc_lower for w in ["guardar", "crear", "actualizar", "eliminar", "base de datos", "bd"]):
        side_effects_sugeridos.append("db_write")
    if any(w in desc_lower for w in ["log", "audit", "bitacora", "registro"]):
        side_effects_sugeridos.append("audit")
    if any(w in desc_lower for w in ["cache", "memoria"]):
        side_effects_sugeridos.append("cache")

    # Detectar si es lectura o escritura
    es_escritura = any(w in desc_lower for w in ["crear", "guardar", "actualizar", "eliminar", "modificar", "enviar"])
    es_lectura = any(w in desc_lower for w in ["leer", "obtener", "consultar", "buscar", "listar"])

    # Detectar casos borde mencionados
    borde_sugeridos = []
    if any(w in desc_lower for w in ["si no", "si el cliente", "si el usuario"]):
        borde_sugeridos.append("validación de entrada")
    if any(w in desc_lower for w in ["error", "excepción", "fallo"]):
        borde_sugeridos.append("manejo de errores")

    # Construir sugerencia de CONTRATO
    contrato_sugerido = {
        "input": "completar con los parámetros de la función",
        "output": "completar con lo que devuelve",
        "side_effects": side_effects_sugeridos if side_effects_sugeridos else ["completar"],
        "rn": ["completar con RN-XXX si aplica"],
        "borde": borde_sugeridos if borde_sugeridos else [],
    }

    # Construir texto del CONTRATO
    lines = ['    """']
    lines.append(f'    CONTRATO:')
    lines.append(f'    input: {contrato_sugerido["input"]}')
    lines.append(f'    output: {contrato_sugerido["output"]}')
    lines.append(f'    side_effects: [{", ".join(contrato_sugerido["side_effects"])}]')
    if contrato_sugerido["rn"] != ["completar con RN-XXX si aplica"]:
        lines.append(f'    rn: [{", ".join(contrato_sugerido["rn"])}]')
    else:
        lines.append(f'    rn: []')
    if contrato_sugerido["borde"]:
        lines.append(f'    borde: [{", ".join(contrato_sugerido["borde"])}]')
    lines.append('    """')

    contrato_texto = "\n".join(lines)

    return {
        "descripcion_original": descripcion_nl,
        "contrato_sugerido": contrato_sugerido,
        "contrato_texto": contrato_texto,
        "campo_a_completar": [
            "input: qué recibe la función",
            "output: qué devuelve la función",
            "rn: qué RNs de negocio aplica (si alguna)",
        ],
        "instruccion_agente": (
            f"El dueño quiere: {descripcion_nl}. "
            f"El tool sugiere un CONTRATO con side_effects={side_effects_sugeridos}. "
            f"Completá los campos marcados y confirmá con el usuario antes de crear."
        ),
    }


def tool_corregir_contrato(archivo: str, funcion: str, problema: str) -> dict[str, Any]:
    """Tool 15: Corrige un CONTRATO con problemas.

    Analiza el problema sugerido y genera la corrección.
    """
    from pathlib import Path

    file_path = Path(archivo)
    if not file_path.exists():
        return {"error": f"Archivo no encontrado: {archivo}"}

    contenido = file_path.read_text(encoding="utf-8")

    # Buscar la función y su docstring
    import re
    patron = rf'def\s+{re.escape(funcion)}\s*\(.*?\).*?:\s*\n\s*"""(.*?)"""'
    match = re.search(patron, contenido, re.DOTALL)

    if not match:
        return {"error": f"No se encontró función {funcion} con docstring en {archivo}"}

    docstring_actual = match.group(1)

    return {
        "archivo": archivo,
        "funcion": funcion,
        "problema_detectado": problema,
        "docstring_actual": docstring_actual.strip(),
        "instruccion_agente": (
            f"Revisar el CONTRATO de {funcion} en {archivo}. "
            f"Problema: {problema}. "
            f"Usar modificar_archivo para aplicar la corrección."
        ),
    }


def tool_ejecutar_verificacion(project_root: str | None = None) -> dict[str, Any]:
    """Tool 16: Ejecuta verificación completa de CONTRATOs.

    Retorna resumen de errores, warnings y métricas.
    """
    import os
    root = project_root or os.environ.get("DOCPACT_PROJECT_ROOT", ".")

    try:
        from docpact.config import DocpactConfig
        from docpact.checker.orchestrator import check_proyecto

        config = DocpactConfig()
        resultado = check_proyecto(root, config)

        errores = []
        warnings = []
        for archivo_result in resultado.archivos:
            for func in archivo_result.funciones:
                for h in func.hallazgos:
                    item = {
                        "archivo": archivo_result.archivo,
                        "funcion": h.funcion,
                        "mensaje": h.mensaje,
                        "sugerencia": h.sugerencia,
                    }
                    if h.tipo == "error":
                        errores.append(item)
                    else:
                        warnings.append(item)

        return {
            "ejecutado": True,
            "total_funciones": resultado.total_funciones,
            "funciones_con_contrato": resultado.funciones_con_contrato,
            "total_errores": len(errores),
            "total_warnings": len(warnings),
            "errores": errores[:10],  # Top 10
            "warnings": warnings[:10],  # Top 10
            "score": resultado.calcular_score(),
            "nivel": resultado.nivel,
        }
    except Exception as e:
        return {"error": f"Error ejecutando verificación: {e}"}


def tool_ejecutar_tests(project_root: str | None = None) -> dict[str, Any]:
    """Tool 17: Ejecuta tests de Reglas de Negocio.

    Retorna resultados de tests: pasaron, fallaron, errores.
    """
    import os
    import subprocess
    root = project_root or os.environ.get("DOCPACT_PROJECT_ROOT", ".")

    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-x", "-q", "--tb=short", "--override-ini=addopts="],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
        )

        return {
            "ejecutado": True,
            "exito": result.returncode == 0,
            "output": result.stdout[-2000:] if result.stdout else "",
            "errores": result.stderr[-1000:] if result.stderr else "",
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Tests excedieron timeout de 60s"}
    except Exception as e:
        return {"error": f"Error ejecutando tests: {e}"}


def tool_generar_reporte(project_root: str | None = None) -> dict[str, Any]:
    """Tool 18: Genera reporte de reglas de negocio.

    Retorna resumen de RNs: cuántas hay, cuántas tienen código, cuántas tienen test.
    """
    import os
    root = project_root or os.environ.get("DOCPACT_PROJECT_ROOT", ".")

    try:
        from docpact.index import cargar_index
        index = cargar_index(root)

        if index is None:
            return {"error": "Índice no encontrado. Ejecutar setup_docpact primero."}

        rns = index.get("rns", {})
        stats = index.get("stats", {})

        rn_detalle = []
        for rn_id, rn in sorted(rns.items()):
            rn_detalle.append({
                "id": rn_id,
                "descripcion": rn["descripcion"],
                "tiene_codigo": len(rn.get("funciones", [])) > 0,
                "tiene_test": rn.get("tiene_test", False),
                "en_registro": rn.get("en_registro", False),
            })

        return {
            "generado": True,
            "total_rns": stats.get("total_rns", 0),
            "rns_con_codigo": stats.get("funciones_con_rn", 0),
            "rns_con_test": stats.get("rns_con_test", 0),
            "rns_sin_codigo": stats.get("total_rns", 0) - stats.get("funciones_con_rn", 0),
            "rns": rn_detalle,
            "resumen": (
                f"{stats.get('total_rns', 0)} RNs totales, "
                f"{stats.get('funciones_con_rn', 0)} con código, "
                f"{stats.get('rns_con_test', 0)} con test"
            ),
        }
    except Exception as e:
        return {"error": f"Error generando reporte: {e}"}

def tool_explicar_errores(project_root: str | None = None) -> dict[str, Any]:
    """Tool 19: Traduce errores técnicos a lenguaje humano.

    Ejecuta la verificación y retorna errores con contexto para explicación.
    El agente LLM usa esta información para generar explicaciones personalizadas.
    """
    import os
    root = project_root or os.environ.get("DOCPACT_PROJECT_ROOT", ".")

    try:
        from docpact.checker.orchestrator import check_proyecto
        from docpact.checker.error_translator import generar_resumen_humano
        from docpact.config import DocpactConfig

        config = DocpactConfig()
        resultado = check_proyecto(root, config)

        # Recopilar hallazgos con contexto
        hallazgos = []
        for archivo_result in resultado.archivos:
            for func in archivo_result.funciones:
                for h in func.hallazgos:
                    hallazgos.append({
                        "tipo": h.tipo,
                        "campo": h.campo,
                        "funcion": h.funcion,
                        "archivo": h.archivo,
                        "linea": h.linea,
                        "mensaje": h.mensaje,
                        "sugerencia": h.sugerencia,
                        "contexto": h.contexto,
                    })

        # Generar resumen humano
        resumen = generar_resumen_humano(hallazgos)

        return {
            "ejecutado": True,
            **resumen,
        }
    except Exception as e:
        return {"error": f"Error explicando errores: {e}"}

def tool_extraer_rns(project_root: str | None = None) -> dict[str, Any]:
    """Tool 21: Extrae reglas de negocio de un proyecto existente.

    Analiza código y sugiere RNs basadas en patrones detectados.
    Útil para migrar proyectos o crear librerías de RNs por industria.
    """
    import os
    root = project_root or os.environ.get("DOCPACT_PROJECT_ROOT", ".")

    try:
        from docpact.checker.rn_extractor import extraer_rns_de_proyecto
        return extraer_rns_de_proyecto(Path(root))
    except Exception as e:
        return {"error": f"Error extrayendo RNs: {e}"}


def tool_predecir_bugs(project_root: str | None = None) -> dict[str, Any]:
    """Tool 22: Predice bugs potenciales en el código.

    Analiza AST y detecta patrones comunes de bugs.
    """
    import os
    root = project_root or os.environ.get("DOCPACT_PROJECT_ROOT", ".")

    try:
        from docpact.checker.bug_predictor import escanear_proyecto
        return escanear_proyecto(root)
    except Exception as e:
        return {"error": f"Error prediciendo bugs: {e}"}


def tool_descubrir_reglas(project_root: str | None = None) -> dict[str, Any]:
    """Tool 20: Descubre reglas de negocio no declaradas en el código.

    Analiza el código buscando patrones que sugieren reglas no formalizadas.
    Cruza con el índice de CONTRATOs para saber cuáles ya están declaradas.
    """
    import os
    root = project_root or os.environ.get("DOCPACT_PROJECT_ROOT", ".")

    try:
        from docpact.checker.rule_discovery import escanear_proyecto
        return escanear_proyecto(Path(root), index=_index)
    except Exception as e:
        return {"error": f"Error descubriendo reglas: {e}"}




def _dispatch_tool(tool_name: str, args: dict[str, Any]) -> Any:
    """Dispatch tool call to the right function."""
    dispatch = {
        "obtener_contexto_funcion": lambda: tool_obtener_contexto_funcion(args.get("nombre_funcion", "")),
        "buscar_por_intencion": lambda: tool_buscar_por_intencion(args.get("intencion", "")),
        "validar_cambio": lambda: tool_validar_cambio(args.get("archivo", ""), args.get("diff", ""), ejecutar_tests=args.get("ejecutar_tests", True)),
        "obtener_rn": lambda: tool_obtener_rn(args.get("rn_id", "")),
        "buscar_rns_por_tema": lambda: tool_buscar_rns_por_tema(args.get("tema", "")),
        "navegar_referencias": lambda: tool_navegar_referencias(args.get("referencia", "")),
        "obtener_briefing": lambda: tool_obtener_briefing(),
        "modificar_archivo": lambda: tool_modificar_archivo(args.get("archivo", ""), args.get("diff", "")),
        "listar_rns": lambda: tool_listar_rns(),
        "verificar_conflicto": lambda: tool_verificar_conflicto(args.get("rn_descripcion", "")),
        "crear_rn": lambda: tool_crear_rn(args.get("rn_id", ""), args.get("descripcion", ""), args.get("archivo_registro", "docs/reglas-del-negocio/REGISTRO.md")),
        "explicar_rn": lambda: tool_explicar_rn(args.get("rn_id", "")),
        "setup_docpact": lambda: tool_setup_docpact(args.get("project_root")),
        "crear_contrato": lambda: tool_crear_contrato(args.get("descripcion_nl", ""), args.get("archivo"), args.get("funcion")),
        "corregir_contrato": lambda: tool_corregir_contrato(args.get("archivo", ""), args.get("funcion", ""), args.get("problema", "")),
        "ejecutar_verificacion": lambda: tool_ejecutar_verificacion(args.get("project_root")),
        "ejecutar_tests": lambda: tool_ejecutar_tests(args.get("project_root")),
        "generar_reporte": lambda: tool_generar_reporte(args.get("project_root")),
        "explicar_errores": lambda: tool_explicar_errores(args.get("project_root")),
        "descubrir_reglas": lambda: tool_descubrir_reglas(args.get("project_root")),
        "extraer_rns": lambda: tool_extraer_rns(args.get("project_root")),
        "predecir_bugs": lambda: tool_predecir_bugs(args.get("project_root")),
    }
    fn = dispatch.get(tool_name)
    if fn is None:
        return {"error": f"Tool desconocida: {tool_name}"}
    return fn()


def _build_agent_context() -> str:
    """Build agent-facing context string from the loaded index.

    Returns a comprehensive description of project state, available tools,
    and recommended workflow — injected into the MCP initialize response
    so agents understand docpact's capabilities without reading external docs.
    """
    # ── Project stats ──
    stats_section = "No project index loaded yet."
    if _index is not None:
        stats = _index.get("stats", {})
        total_funcs = stats.get("total_funciones", 0)
        funcs_with_rn = stats.get("funciones_con_rn", 0)
        total_rns = stats.get("total_rns", 0)
        rns_with_test = stats.get("rns_con_test", 0)
        has_emb = stats.get("has_embeddings", False)

        coverage = (
            f"{funcs_with_rn}/{total_funcs} functions have CONTRATOs"
            if total_funcs > 0
            else "no functions indexed"
        )
        rn_coverage = (
            f"{rns_with_test}/{total_rns} RNs have tests"
            if total_rns > 0
            else "no RNs indexed"
        )
        embedding_status = "enabled (semantic search active)" if has_emb else "disabled (keyword-only search)"

        stats_section = (
            f"- Functions: {total_funcs} total, {coverage}\n"
            f"- Business Rules (RNs): {total_rns} total, {rn_coverage}\n"
            f"- Semantic search: {embedding_status}\n"
            f"- Project root: {_project_root}"
        )

    return (
        "# Docpact — Business Rule Type Checker\n\n"
        "docpact verifies that Python code implements declared business rules.\n"
        "Functions declare contracts (CONTRATOs) in docstrings; docpact checks\n"
        "side effects, RN references, and test coverage against those declarations.\n\n"
        "## Project Status\n"
        f"{stats_section}\n\n"
        "## Available Tools (18 total)\n\n"
        "**Discovery & Context** — understand the codebase before editing:\n"
        "- `obtener_contexto_funcion` — full context for a function (contract, RNs, tests, location)\n"
        "- `buscar_por_intencion` — semantic/keyword search for functions by intent\n"
        "- `obtener_rn` — full context for a business rule\n"
        "- `buscar_rns_por_tema` — search RNs by topic\n"
        "- `navegar_referencias` — cross-reference navigation (RN→functions, file→functions, function→calls)\n"
        "- `obtener_briefing` — project briefing with active RNs, side effects, risk zones\n"
        "- `listar_rns` — list all business rules with status\n\n"
        "**Validation & Enforcement** — gate changes before commit:\n"
        "- `validar_cambio` — validate a diff + run relevant tests (ENFORCEMENT)\n"
        "- `modificar_archivo` — validate changes against contracts before applying\n\n"
        "**Contract Management** — create and maintain CONTRATOs:\n"
        "- `crear_contrato` — generate a CONTRATO docstring from natural language\n"
        "- `corregir_contrato` — diagnose and fix a broken CONTRATO\n\n"
        "**RN Management** — manage business rules lifecycle:\n"
        "- `verificar_conflicto` — check if a new RN conflicts with existing ones\n"
        "- `crear_rn` — create a new business rule (verify conflicts first!)\n"
        "- `explicar_rn` — explain an RN in plain language\n\n"
        "**Operations** — run checks and generate reports:\n"
        "- `ejecutar_verificacion` — full CONTRATO verification run\n"
        "- `ejecutar_tests` — run business rule tests with pytest\n"
        "- `generar_reporte` — generate coverage/compliance report\n"
        "- `setup_docpact` — initialize docpact in a project\n\n"
        "## Recommended Workflow\n\n"
        "1. **Start here**: Call `obtener_briefing` to understand the project's business rules\n"
        "2. **Before editing**: Call `obtener_contexto_funcion` on any function you plan to change\n"
        "3. **After editing**: Call `validar_cambio` with your diff — this is ENFORCEMENT, not optional\n"
        "4. **Adding features**: Verify conflicts with `verificar_conflicto`, then `crear_rn`, then `crear_contrato`\n"
        "5. **Exploring**: Use `buscar_por_intencion` when you don't know the function name\n\n"
        "## Further Reading\n\n"
        "See DOCPACT_AGENT_GUIDE.md in the project root for detailed usage patterns,\n"
        "CONTRATO format specification, and integration examples."
    )


def main() -> int:
    """Loop principal del MCP server v2."""
    _log_startup_info()

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
                force = params.get("force", False)
                _cargar_o_generar_index(project_root, force=force)

                agent_context = _build_agent_context()

                _responder(
                    req_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "docpact-mcp",
                            "version": "2.0.0",
                        },
                        "instructions": agent_context,
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

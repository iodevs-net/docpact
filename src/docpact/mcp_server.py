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
        "description": "Busca funciones por intención en lenguaje natural. Si FastEmbed está disponible, usa búsqueda semántica (cosine similarity + keyword). Retorna top 5 con score. Usa esto cuando no sabés el nombre exacto de la función.",
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
        "description": "Valida un diff Y ejecuta tests relevantes antes de commit. Si algún test falla, el cambio es INVÁLIDO. El agente NO puede commitar hasta que todo pase. Esto es ENFORCEMENT, no solo verificación.",
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
        "description": "Busca RNs por tema o palabra clave. Si FastEmbed está disponible, usa búsqueda semántica combinada con keyword. Retorna RNs relevantes con sus funciones.",
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
    {
        "name": "obtener_briefing",
        "description": "Obtiene el briefing de reglas de negocio del proyecto. Lee esto ANTES de empezar a codear para entender qué debes respetar: RNs activas, side effects, zonas de riesgo.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "modificar_archivo",
        "description": "Valida un cambio contra los CONTRATOs antes de aplicarlo. Si el cambio viola side effects o RNs, lo RECHAZA. Usa esto SIEMPRE antes de modificar un archivo.",
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
        "description": "Lista TODAS las RNs del proyecto con descripción, funciones que las implementan, y estado. Usa esto cuando el dueño de negocio pregunte 'qué reglas hay' o necesites ver el panorama completo.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "verificar_conflicto",
        "description": "Verifica si una nueva RN entrará en conflicto con existentes. Detecta duplicados, overrides, y choques de concepto. SIEMPRE usar ANTES de crear una RN nueva.",
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
        "description": "Crea una nueva RN en el REGISTRO.md. VALIDAR PRIMERO con verificar_conflicto. El agente DEBE confirmar con el usuario antes de ejecutar.",
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
        "description": "Explica una RN en lenguaje simple para el dueño de negocio. Traduce técnica a natural: qué regla define, quién la implementa, si está verificada, y estado actual.",
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
    """Tool 8: Valida un cambio contra los CONTRATOs antes de aplicarlo."""
    import os
    project_root = os.environ.get("DOCPACT_PROJECT_ROOT", ".")
    from docpact.guard import validar_cambio

    resultado = validar_cambio(archivo, diff, project_root)
    return {
        "allowed": resultado.allowed,
        "message": resultado.message,
        "violations": [
            {"funcion": v.funcion, "tipo": v.tipo, "mensaje": v.mensaje, "sugerencia": v.sugerencia}
            for v in resultado.violations
        ],
    }
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
    """Tool 10: Verifica si una nueva RN entrará en conflicto con existentes.

    Analiza:
    - Conflictos directos: misma entidad, regla opuesta
    - Overrides: misma función/concepto, comportamiento diferente
    - Duplicados: descripción muy similar a una existente

    Retorna lista de RNs potencialmente conflictivas con explicación.
    """
    if _index is None:
        return {"error": "Índice no cargado"}

    conflictos = []
    desc_lower = rn_descripcion.lower()

    for rn_id, rn in _index["rns"].items():
        existente_desc = rn["descripcion"].lower()

        # 1. Duplicado casi exacto (similitud > 0.7)
        similitud = _calcular_similitud(rn_descripcion, rn["descripcion"])
        if similitud > 0.7:
            conflictos.append({
                "tipo": "duplicado",
                "rn_id": rn_id,
                "descripcion": rn["descripcion"],
                "similitud": round(similitud, 2),
                "explicacion": f"La RN propuesta es muy similar a {rn_id}. Podría ser un duplicado.",
                "accion": f"Revisá si es la misma regla. Si lo es, usá {rn_id} en lugar de crear una nueva.",
            })
            continue

        # 2. Misma entidad/concepto (keywords compartidos significativos)
        similitud_concepto = _calcular_similitud(rn_descripcion, rn["descripcion"])
        if similitud_concepto > 0.4:
            conflictos.append({
                "tipo": "mismo_concepto",
                "rn_id": rn_id,
                "descripcion": rn["descripcion"],
                "similitud": round(similitud_concepto, 2),
                "explicacion": f"La RN propuesta trata un tema similar a {rn_id}. Verificá que no choquen.",
                "accion": "Compará las dos reglas. Si definen comportamientos diferentes para el mismo caso, una sobreescribe a la otra.",
            })

        # 3. Override potencial: misma función afectada
        if rn.get("funciones"):
            for func in rn["funciones"]:
                func_name = func.get("funcion", "").lower()
                # Si la descripción nueva menciona la misma función
                if func_name and func_name in desc_lower:
                    conflictos.append({
                        "tipo": "override",
                        "rn_id": rn_id,
                        "descripcion": rn["descripcion"],
                        "funcion_afectada": func["funcion"],
                        "explicacion": f"La RN propuesta afecta la función '{func['funcion']}', que ya está regulada por {rn_id}.",
                        "accion": f"Definí si la nueva regla reemplaza o complementa a {rn_id}. Si reemplaza, actualizá {rn_id} en lugar de crear una nueva.",
                    })

    return {
        "tiene_conflictos": len(conflictos) > 0,
        "conflictos": conflictos,
        "total_conflictos": len(conflictos),
        "descripcion_evaluada": rn_descripcion,
        "consejo": (
            "Encontré posibles conflictos. Revisá cada uno antes de crear la RN."
            if conflictos
            else "No detecté conflictos. Podés proceder a crear la RN."
        ),
    }


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
            args.get("archivo", ""),
            args.get("diff", ""),
            ejecutar_tests=args.get("ejecutar_tests", True),
        ),
        "obtener_rn": lambda: tool_obtener_rn(args.get("rn_id", "")),
        "buscar_rns_por_tema": lambda: tool_buscar_rns_por_tema(
            args.get("tema", "")
        ),
        "navegar_referencias": lambda: tool_navegar_referencias(
            args.get("referencia", "")
        ),
        "obtener_briefing": lambda: tool_obtener_briefing(),
        "modificar_archivo": lambda: tool_modificar_archivo(
            args.get("archivo", ""),
            args.get("diff", ""),
        ),
        "listar_rns": lambda: tool_listar_rns(),
        "verificar_conflicto": lambda: tool_verificar_conflicto(
            args.get("rn_descripcion", "")
        ),
        "crear_rn": lambda: tool_crear_rn(
            args.get("rn_id", ""),
            args.get("descripcion", ""),
            args.get("archivo_registro", "docs/reglas-del-negocio/REGISTRO.md"),
        ),
        "explicar_rn": lambda: tool_explicar_rn(args.get("rn_id", "")),
    }

    fn = dispatch.get(tool_name)
    if fn is None:
        return {"error": f"Tool desconocida: {tool_name}"}
    return fn()


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

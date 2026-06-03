"""Generador de índice pre-calculado para MCP server.

Escanea un proyecto UNA VEZ y genera .docpact/index.json
con toda la información que las tools MCP necesitan.
Consultas <5ms en RAM.

Incluye soporte opcional de búsqueda semántica via FastEmbed.
Si fastembed no está instalado, fallback a keyword-only.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from docpact.api import extract_contratos
from docpact.checker.rn_registry import cargar_registro


def _try_load_embedder() -> Any | None:
    """Intenta cargar TextEmbedding de FastEmbed con multilingual-e5-small.

    Modelo: intfloat/multilingual-e5-small (384 dims, ONNX, 60+ idiomas).
    Mejor para retrieval bilingüe (español/inglés) que bge-small-en-v1.5.
    Si fastembed no está instalado, retorna None (fallback a keyword).

    Returns:
        TextEmbedding instance o None si fastembed no está instalado.
    """
    try:
        from fastembed import TextEmbedding
        from fastembed.common.model_description import PoolingType, ModelSource

        TextEmbedding.add_custom_model(
            model="intfloat/multilingual-e5-small",
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf="intfloat/multilingual-e5-small"),
            dim=384,
            model_file="onnx/model.onnx",
        )
        return TextEmbedding(model_name="intfloat/multilingual-e5-small")
    except ImportError:
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calcula similitud coseno entre dos vectores (pure Python, sin numpy).

    Args:
        a: Primer vector.
        b: Segundo vector.

    Returns:
        Similitud coseno entre -1 y 1.
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _generate_embeddings(
    funciones: dict[str, dict[str, Any]],
    rns: dict[str, dict[str, Any]],
    embedder: Any | None = None,
) -> dict[str, Any] | None:
    """Genera embeddings para funciones y RNs usando FastEmbed.

    Args:
        funciones: Índice de funciones.
        rns: Índice de RNs.
        embedder: Instancia de TextEmbedding o None.

    Returns:
        Dict con embeddings serializable o None si embedder es None.
    """
    if embedder is None:
        return None

    # Preparar documentos para funciones
    func_keys: list[str] = []
    func_docs: list[str] = []
    for key, f in funciones.items():
        parts = [
            f["funcion"],
            f["contrato"].get("output_descripcion", "") or "",
            " ".join(f.get("rn_ids", [])),
            Path(f["archivo"]).name,
        ]
        doc = " ".join(p for p in parts if p)
        if doc.strip():
            func_keys.append(key)
            func_docs.append(doc)

    # Preparar documentos para RNs
    rn_keys: list[str] = []
    rn_docs: list[str] = []
    for rn_id, rn in rns.items():
        doc = f"{rn_id} {rn['descripcion']}"
        if doc.strip():
            rn_keys.append(rn_id)
            rn_docs.append(doc)

    # Generar embeddings en batch
    func_embeddings: dict[str, list[float]] = {}
    if func_docs:
        vectors = list(embedder.embed(func_docs))
        for key, vec in zip(func_keys, vectors):
            func_embeddings[key] = [round(float(x), 6) for x in vec]

    rn_embeddings: dict[str, list[float]] = {}
    if rn_docs:
        vectors = list(embedder.embed(rn_docs))
        for key, vec in zip(rn_keys, vectors):
            rn_embeddings[key] = [round(float(x), 6) for x in vec]

    return {
        "model": "intfloat/multilingual-e5-small",
        "dimension": 384,
        "funciones": func_embeddings,
        "rns": rn_embeddings,
    }


def generar_index(
    project_root: str | Path,
    embedder: Any | None = None,
) -> dict[str, Any]:
    """Genera el índice completo para el MCP server.

    Args:
        project_root: Raíz del proyecto Django/iodesk.
        embedder: Instancia de TextEmbedding (opcional). Si None, intenta
                  cargar automáticamente. Si fastembed no está instalado,
                  se omite la búsqueda semántica.

    Returns:
        Dict serializable con todo el índice.
    """
    root = Path(project_root)

    # 1. Extraer todos los contratos
    contratos = extract_contratos(root)

    # 2. Cargar registro de RNs
    registro = cargar_registro(root)

    # 3. Mapear archivos de test por RN
    tests_por_rn = _mapear_tests_rn(root)

    # 4. Buscar comments # RN-XXX en código fuente
    rn_comments = _buscar_rn_comments(root)

    # 5. Construir índices
    funciones = _indexar_funciones(contratos, registro, tests_por_rn, rn_comments)
    rns = _indexar_rns(contratos, registro, tests_por_rn)
    busqueda = _indexar_busqueda(funciones)

    # 6. Generar embeddings (opcional — fallback si FastEmbed no disponible)
    if embedder is None:
        embedder = _try_load_embedder()
    embeddings = _generate_embeddings(funciones, rns, embedder)

    return {
        "version": "1.1",
        "project_root": str(root),
        "stats": {
            "total_funciones": len(funciones),
            "funciones_con_rn": sum(1 for f in funciones.values() if f["rn"]),
            "total_rns": len(rns),
            "rns_con_test": sum(1 for r in rns.values() if r["tiene_test"]),
            "has_embeddings": embeddings is not None,
        },
        "funciones": funciones,
        "rns": rns,
        "busqueda": busqueda,
        "embeddings": embeddings,
    }


def _mapear_tests_rn(root: Path) -> dict[str, list[str]]:
    """Busca tests/rn/test_rn_XXX.py y retorna {RN_ID: [path_test]}."""
    rn_dir = root / "tests" / "rn"
    if not rn_dir.exists():
        return {}

    mapping: dict[str, list[str]] = {}
    for test_file in rn_dir.glob("test_rn_*.py"):
        # Extraer IDs del nombre del archivo
        # test_rn_TKT-001.py → TKT-001
        # test_rn_016.py → 016 (legacy)
        match = re.match(r"test_rn_(.+)\.py$", test_file.name)
        if match:
            rn_id_raw = match.group(1)
            # Buscar en el contenido del test qué RNs declara
            content = test_file.read_text(encoding="utf-8")
            rns_in_file = re.findall(r"RN-[\w-]+", content)
            for rn in set(rns_in_file):
                mapping.setdefault(rn, []).append(str(test_file))
            # Si no encontró RNs en contenido, usar el nombre
            if not rns_in_file:
                mapping.setdefault(rn_id_raw, []).append(str(test_file))

    return mapping


def _buscar_rn_comments(root: Path) -> dict[str, dict[str, list[str]]]:
    """Busca comments # RN-XXX en código fuente.

    Retorna: {filepath: {funcion: [RN_ID, ...]}}
    """
    result: dict[str, dict[str, list[str]]] = {}
    rn_pattern = re.compile(r"#\s*(RN-[\w-]+)")

    for py_file in root.rglob("*.py"):
        if any(part in py_file.parts for part in ["__pycache__", ".venv", "venv", "node_modules", ".git", "migrations", ".pytest_cache", "tests"]):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except (SyntaxError, UnicodeDecodeError):
            continue

        lines = content.split("\n")
        current_func = None
        file_comments: dict[str, list[str]] = {}

        for line in lines:
            # Detectar definición de función
            func_match = re.match(r"\s*def\s+(\w+)\s*\(", line)
            if func_match:
                current_func = func_match.group(1)

            # Buscar comments # RN-XXX
            rn_match = rn_pattern.search(line)
            if rn_match and current_func:
                file_comments.setdefault(current_func, []).append(rn_match.group(1))

        if file_comments:
            result[str(py_file)] = file_comments

    return result


def _indexar_funciones(
    contratos: list[dict[str, Any]],
    registro: dict[str, str],
    tests_por_rn: dict[str, list[str]],
    rn_comments: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, Any]]:
    """Indexa funciones con su contexto completo."""
    funciones: dict[str, dict[str, Any]] = {}

    for c in contratos:
        if not c.get("archivo"):
            continue
        # No incluir tests en el índice principal
        if "/tests/" in c["archivo"] or "\\tests\\" in c["archivo"]:
            continue

        archivo = c["archivo"]
        nombre = c["funcion"]
        key = f"{archivo}::{nombre}"

        contrato = c.get("contrato", {})
        rns = contrato.get("rn", [])

        # Enriquecer RNs con info del registro y tests
        rns_enriquecidas = []
        for r in rns:
            rn_id = r.get("id", "")
            rn_info = {
                "id": rn_id,
                "descripcion": r.get("descripcion") or registro.get(rn_id, ""),
                "en_registro": rn_id in registro,
            }
            # Agregar test si existe
            test_files = tests_por_rn.get(rn_id, [])
            rn_info["test"] = test_files[0] if test_files else None
            rn_info["tiene_test"] = len(test_files) > 0
            rns_enriquecidas.append(rn_info)

        # Obtener comments del código fuente
        func_comments = rn_comments.get(archivo, {}).get(nombre, [])

        funciones[key] = {
            "archivo": archivo,
            "funcion": nombre,
            "tipo": c.get("tipo", "function"),
            "linea": c.get("linea", 0),
            "contrato": {
                "input": contrato.get("input", {}),
                "output": contrato.get("output"),
                "output_descripcion": contrato.get("output_descripcion"),
                "side_effects": contrato.get("side_effects", []),
                "borde": contrato.get("borde", []),
                "dependencias": contrato.get("dependencias", []),
            },
            "rn": rns_enriquecidas,
            "rn_ids": [r["id"] for r in rns_enriquecidas],
            "rn_comments": func_comments,
            "tiene_rn": len(rns_enriquecidas) > 0,
        }

    return funciones


def _indexar_rns(
    contratos: list[dict[str, Any]],
    registro: dict[str, str],
    tests_por_rn: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    """Indexa RNs con todas las funciones que las implementan."""
    rns: dict[str, dict[str, Any]] = {}

    # Inicializar desde registro
    for rn_id, desc in registro.items():
        rns[rn_id] = {
            "id": rn_id,
            "descripcion": desc,
            "en_registro": True,
            "funciones": [],
            "test": None,
            "tiene_test": False,
        }

    # Enriquecer desde contratos
    for c in contratos:
        if "/tests/" in c.get("archivo", ""):
            continue
        contrato = c.get("contrato", {})
        for r in contrato.get("rn", []):
            rn_id = r.get("id", "")
            if not rn_id:
                continue
            if rn_id not in rns:
                rns[rn_id] = {
                    "id": rn_id,
                    "descripcion": r.get("descripcion", ""),
                    "en_registro": False,
                    "funciones": [],
                    "test": None,
                    "tiene_test": False,
                }
            rns[rn_id]["funciones"].append({
                "archivo": c["archivo"],
                "funcion": c["funcion"],
                "linea": c.get("linea", 0),
            })

    # Agregar tests
    for rn_id, test_files in tests_por_rn.items():
        if rn_id in rns:
            rns[rn_id]["test"] = test_files[0]
            rns[rn_id]["tiene_test"] = True

    return rns


def _indexar_busqueda(funciones: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """Indexa para búsqueda por palabras clave."""
    # Index por nombre de función
    por_nombre: dict[str, list[str]] = {}
    # Index por archivo
    por_archivo: dict[str, list[str]] = {}
    # Index por side_effect
    por_side_effect: dict[str, list[str]] = {}

    for key, f in funciones.items():
        # Nombre de función
        nombre_lower = f["funcion"].lower()
        por_nombre.setdefault(nombre_lower, []).append(key)

        # Archivo (solo nombre, no path completo)
        archivo = Path(f["archivo"]).name
        por_archivo.setdefault(archivo, []).append(key)

        # Side effects
        for se in f["contrato"]["side_effects"]:
            por_side_effect.setdefault(se, []).append(key)

    return {
        "por_nombre": por_nombre,
        "por_archivo": por_archivo,
        "por_side_effect": por_side_effect,
    }


def guardar_index(index: dict[str, Any], project_root: str | Path) -> Path:
    """Guarda el índice en .docpact/index.json."""
    root = Path(project_root)
    docpact_dir = root / ".docpact"
    docpact_dir.mkdir(exist_ok=True)

    index_path = docpact_dir / "index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return index_path


def cargar_index(project_root: str | Path) -> dict[str, Any] | None:
    """Carga el índice desde .docpact/index.json. None si no existe."""
    index_path = Path(project_root) / ".docpact" / "index.json"
    if not index_path.exists():
        return None
    return json.loads(index_path.read_text(encoding="utf-8"))

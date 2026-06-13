"""Detector proactivo de reglas de negocio no declaradas."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReglaDescubierta:
    tipo: str
    titulo: str
    evidencia: str
    archivo: str
    linea: int
    confianza: str
    sugerencia: str


_PATRONES = [
    {"tipo": "validacion", "patron": "raise.*Error.*if not|if not.*raise.*Error", "confianza": "alta", "titulo": "Validación de entrada detectada", "sugerencia": "Formalizar como CONTRATO con campo 'borde'"},
    {"tipo": "permiso", "patron": "permission_required|has_perm|is_authorized|LoginRequiredMixin", "confianza": "alta", "titulo": "Restricción de permiso detectada", "sugerencia": "Formalizar como RN con prefijo RN-SEG-"},
    {"tipo": "negocio", "patron": "\\.objects\\.create\\(|\\.objects\\.bulk_create\\(", "confianza": "alta", "titulo": "Creación de objeto detectada (side effect)", "sugerencia": "Verificar que esté declarado en 'side_effects: db_write'"},
    {"tipo": "estado", "patron": "status.*=.*EstadoTicket\\.|estado.*=.*EstadoTicket\\.", "confianza": "alta", "titulo": "Transición de estado detectada", "sugerencia": "Formalizar como RN con patrón state_transition"},
    {"tipo": "auditoria", "patron": "send_mail\\(|EmailMessage\\(|_enviar_email\\(", "confianza": "alta", "titulo": "Envío de email detectado", "sugerencia": "Verificar que esté declarado en 'side_effects: email'"},
    {"tipo": "auditoria", "patron": "BitacoraEntry\\.objects\\.create\\(|AuditService\\.log\\(", "confianza": "alta", "titulo": "Registro de auditoría detectado", "sugerencia": "Verificar que esté declarado en 'side_effects: audit'"},
]


def _construir_grafo_llamadas(raiz: Path) -> dict[str, list[str]]:
    llamadas: dict[str, list[str]] = {}
    for archivo in raiz.rglob("*.py"):
        if any(p.startswith(".") or p in ("__pycache__", "venv", ".venv", "node_modules", "tests") for p in archivo.parts):
            continue
        if archivo.name.startswith("test_") or archivo.name == "conftest.py":
            continue
        try:
            tree = ast.parse(archivo.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        funcs = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs[node.name] = f"{archivo}::{node.name}"
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller = f"{archivo}::{node.name}"
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        name = sub.func.id if isinstance(sub.func, ast.Name) else (sub.func.attr if isinstance(sub.func, ast.Attribute) else None)
                        if name and name in funcs:
                            llamadas.setdefault(funcs[name], []).append(caller)
    return llamadas


def detectar_patrones(archivo: Path) -> list[ReglaDescubierta]:
    try:
        tree = ast.parse(archivo.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    reglas = []
    lineas = archivo.read_text(encoding="utf-8").split("\n")
    for nodo in ast.walk(tree):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(nodo):
            if not hasattr(sub, "lineno") or sub.lineno < 1 or sub.lineno > len(lineas):
                continue
            for p in _PATRONES:
                try:
                    if re.search(p["patron"], lineas[sub.lineno - 1], re.IGNORECASE):
                        doc = ast.get_docstring(nodo)
                        if not (doc and "CONTRATO:" in doc):
                            reglas.append(ReglaDescubierta(p["tipo"], p["titulo"], lineas[sub.lineno - 1].strip(), str(archivo), sub.lineno, p["confianza"], p["sugerencia"]))
                except re.error:
                    continue
    return reglas


def _encontrar_funcion_que_contiene(archivo: Path, linea: int) -> str | None:
    try:
        tree = ast.parse(archivo.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                if node.lineno <= linea <= end:
                    return f"{archivo.resolve()}::{node.name}"
    except (SyntaxError, UnicodeDecodeError):
        pass
    return None


def escanear_proyecto(raiz: Path, index: dict | None = None) -> dict:
    reglas_totales = []
    archivos_escaneados = 0

    # Lookup de funciones del index (solo las que tienen CONTRATO)
    index_lookup = {}
    if index:
        for key, fd in index.get("funciones", {}).items():
            archivo = fd.get("archivo", "")
            linea = fd.get("linea", 0)
            archivo_rel = str(Path(archivo).relative_to(raiz)) if Path(archivo).is_absolute() and Path(archivo).is_relative_to(raiz) else archivo
            index_lookup[key] = {
                "nombre": fd.get("funcion", ""),
                "archivo_rel": archivo_rel,
                "linea": linea,
                "side_effects": fd.get("contrato", {}).get("side_effects", []),
                "rn_ids": fd.get("rn_ids", []),
            }

    # Grafo de llamadas normalizado a absolutos
    grafo = _construir_grafo_llamadas(raiz) if index else {}
    abs_grafo = {}
    for callee, callers in grafo.items():
        if "::" in callee:
            a, f = callee.split("::", 1)
            abs_callee = str(Path(a).resolve()) + "::" + f
            abs_callers = [str(Path(c.split("::")[0]).resolve()) + "::" + c.split("::")[1] for c in callers if "::" in c]
            abs_grafo[abs_callee] = abs_callers

    # Escanear
    for archivo in raiz.rglob("*.py"):
        if any(p.startswith(".") or p in ("__pycache__", "venv", ".venv", "node_modules", "tests") for p in archivo.parts):
            continue
        if archivo.name.startswith("test_") or archivo.name == "conftest.py":
            continue
        reglas_totales.extend(detectar_patrones(archivo))
        archivos_escaneados += 1

    # Cruzar
    reglas_cruzadas = []
    for r in reglas_totales:
        esta_declarada = False
        declaracion = ""
        archivo_abs = Path(r.archivo).resolve()

        # 1. Verificar callers
        if index and abs_grafo:
            func_key = _encontrar_funcion_que_contiene(archivo_abs, r.linea)
            if func_key:
                for caller_key in abs_grafo.get(func_key, []):
                    cd = index_lookup.get(caller_key)
                    if cd:
                        if r.tipo == "negocio" and "db_write" in cd["side_effects"]:
                            esta_declarada, declaracion = True, f"db_write en caller {cd['nombre']}"
                            break
                        elif r.tipo == "auditoria" and "email" in cd["side_effects"]:
                            esta_declarada, declaracion = True, f"email en caller {cd['nombre']}"
                            break
                        elif r.tipo == "auditoria" and "audit" in cd["side_effects"]:
                            esta_declarada, declaracion = True, f"audit en caller {cd['nombre']}"
                            break
                        elif cd["rn_ids"]:
                            esta_declarada, declaracion = True, f"RNs en caller: {', '.join(cd['rn_ids'])}"
                            break

        # 2. Verificar función directa
        if not esta_declarada and index:
            for key, cd in index_lookup.items():
                if cd["archivo_rel"] == r.archivo and abs(cd["linea"] - r.linea) < 30:
                    if r.tipo == "negocio" and "db_write" in cd["side_effects"]:
                        esta_declarada, declaracion = True, f"db_write en {cd['nombre']}"
                        break
                    elif r.tipo == "auditoria" and "email" in cd["side_effects"]:
                        esta_declarada, declaracion = True, f"email en {cd['nombre']}"
                        break
                    elif r.tipo == "auditoria" and "audit" in cd["side_effects"]:
                        esta_declarada, declaracion = True, f"audit en {cd['nombre']}"
                        break
                    elif cd["rn_ids"]:
                        esta_declarada, declaracion = True, f"RNs: {', '.join(cd['rn_ids'])}"
                        break

        archivo_rel = str(Path(r.archivo).relative_to(raiz)) if Path(r.archivo).is_absolute() and Path(r.archivo).is_relative_to(raiz) else r.archivo
        reglas_cruzadas.append({**r.__dict__, "archivo": archivo_rel, "esta_declarada": esta_declarada, "declaracion": declaracion})

    no_declaradas = [r for r in reglas_cruzadas if not r["esta_declarada"]]
    declaradas = [r for r in reglas_cruzadas if r["esta_declarada"]]
    por_tipo = {}
    for r in no_declaradas:
        por_tipo.setdefault(r["tipo"], []).append(r)

    return {
        "archivos_escaneados": archivos_escaneados,
        "total_encontradas": len(reglas_cruzadas),
        "ya_declaradas": len(declaradas),
        "sin_declarar": len(no_declaradas),
        "por_tipo": {k: len(v) for k, v in por_tipo.items()},
        "reglas": no_declaradas[:30],
    }

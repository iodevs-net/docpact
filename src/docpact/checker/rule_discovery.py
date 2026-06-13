"""Detector proactivo de reglas de negocio no declaradas.

Analiza el código para encontrar patrones que sugieren reglas
que no están formalizadas en CONTRATOs.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReglaDescubierta:
    """Una regla potencial descubierta en el código."""

    tipo: str  # "validacion", "estado", "permiso", "auditoria", "negocio"
    titulo: str  # Descripción corta
    evidencia: str  # Qué código sugiere esta regla
    archivo: str
    linea: int
    confianza: str  # "alta", "media", "baja"
    sugerencia: str  # Cómo formalizarla


# ── Patrones de detección ──

_PATRONES = [
    # Validaciones de entrada (solo en archivos de servicios/views)
    {
        "tipo": "validacion",
        "patron": "raise.*Error.*if not|if not.*raise.*Error",
        "confianza": "alta",
        "titulo": "Validación de entrada detectada",
        "sugerencia": "Formalizar como CONTRATO con campo 'borde'",
        "excluir_tests": True,
    },
    # Restricciones de permisos
    {
        "tipo": "permiso",
        "patron": "permission_required|has_perm|is_authorized|LoginRequiredMixin",
        "confianza": "alta",
        "titulo": "Restricción de permiso detectada",
        "sugerencia": "Formalizar como RN con prefijo RN-SEG-",
        "excluir_tests": True,
    },
    # Creación de objetos (side effects) - solo en servicios
    {
        "tipo": "negocio",
        "patron": "\\.objects\\.create\\(|\\.objects\\.bulk_create\\(",
        "confianza": "alta",
        "titulo": "Creación de objeto detectada (side effect)",
        "sugerencia": "Verificar que esté declarado en 'side_effects: db_write'",
        "excluir_tests": True,
    },
    # Transiciones de estado explícitas
    {
        "tipo": "estado",
        "patron": "status.*=.*EstadoTicket\\.|estado.*=.*EstadoTicket\\.",
        "confianza": "alta",
        "titulo": "Transición de estado detectada",
        "sugerencia": "Formalizar como RN con patrón state_transition",
        "excluir_tests": True,
    },
    # Emails/envíos
    {
        "tipo": "auditoria",
        "patron": "send_mail\\(|EmailMessage\\(|_enviar_email\\(",
        "confianza": "alta",
        "titulo": "Envío de email detectado",
        "sugerencia": "Verificar que esté declarado en 'side_effects: email'",
        "excluir_tests": True,
    },
    # Auditoría/bitácora
    {
        "tipo": "auditoria",
        "patron": "BitacoraEntry\\.objects\\.create\\(|AuditService\\.log\\(",
        "confianza": "alta",
        "titulo": "Registro de auditoría detectado",
        "sugerencia": "Verificar que esté declarado en 'side_effects: audit'",
        "excluir_tests": True,
    },
]


def detectar_patrones(archivo: Path) -> list[ReglaDescubierta]:
    """Detecta patrones de reglas en un archivo Python.

    Analiza el AST para encontrar patrones que sugieren
    reglas de negocio no declaradas.

    Args:
        archivo: Path al archivo Python

    Returns:
        Lista de reglas descubiertas
    """
    try:
        contenido = archivo.read_text(encoding="utf-8")
        tree = ast.parse(contenido)
    except (SyntaxError, UnicodeDecodeError):
        return []

    reglas = []
    lineas = contenido.split("\n")

    for nodo in ast.walk(tree):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Buscar en el cuerpo de la función
        for subnodo in ast.walk(nodo):
            linea_codigo = _obtener_linea(subnodo, lineas)
            if not linea_codigo:
                continue

            for patron_info in _PATRONES:
                if _matchea_patron(linea_codigo, patron_info["patron"]):
                    # Verificar si tiene CONTRATO
                    docstring = ast.get_docstring(nodo)
                    tiene_contrato = docstring and "CONTRATO:" in docstring

                    # Solo sugerir si NO tiene CONTRATO
                    if not tiene_contrato:
                        reglas.append(ReglaDescubierta(
                            tipo=patron_info["tipo"],
                            titulo=patron_info["titulo"],
                            evidencia=linea_codigo.strip(),
                            archivo=str(archivo),
                            linea=subnodo.lineno,
                            confianza=patron_info["confianza"],
                            sugerencia=patron_info["sugerencia"],
                        ))

    return reglas


def _obtener_linea(nodo: ast.AST, lineas: list[str]) -> str | None:
    """Obtiene la línea de código de un nodo AST."""
    if not hasattr(nodo, "lineno"):
        return None
    if nodo.lineno < 1 or nodo.lineno > len(lineas):
        return None
    return lineas[nodo.lineno - 1]


def _matchea_patron(linea: str, patron: str) -> bool:
    """Verifica si una línea matchea un patrón (simplificado)."""
    import re
    try:
        return bool(re.search(patron, linea, re.IGNORECASE))
    except re.error:
        return False


def escanear_proyecto(raiz: Path) -> dict:
    """Escanea todo el proyecto buscando patrones de reglas.

    Args:
        raiz: Raíz del proyecto

    Returns:
        Resumen de reglas descubiertas
    """
    reglas_totales = []
    archivos_escaneados = 0

    for archivo in raiz.rglob("*.py"):
        # Saltar directorios excluidos y tests
        if any(part.startswith(".") or part in ("__pycache__", "venv", ".venv", "node_modules", "tests")
               for part in archivo.parts):
            continue
        if archivo.name.startswith("test_") or archivo.name == "conftest.py":
            continue

        reglas = detectar_patrones(archivo)
        reglas_totales.extend(reglas)
        archivos_escaneados += 1

    # Agrupar por tipo
    por_tipo = {}
    for r in reglas_totales:
        por_tipo.setdefault(r.tipo, []).append(r)

    # Agrupar por confianza
    por_confianza = {"alta": [], "media": [], "baja": []}
    for r in reglas_totales:
        por_confianza[r.confianza].append(r)

    return {
        "archivos_escaneados": archivos_escaneados,
        "reglas_encontradas": len(reglas_totales),
        "por_tipo": {k: len(v) for k, v in por_tipo.items()},
        "por_confianza": {k: len(v) for k, v in por_confianza.items()},
        "reglas": [
            {
                "tipo": r.tipo,
                "titulo": r.titulo,
                "evidencia": r.evidencia,
                "archivo": r.archivo,
                "linea": r.linea,
                "confianza": r.confianza,
                "sugerencia": r.sugerencia,
            }
            for r in reglas_totales[:50]  # Top 50
        ],
    }

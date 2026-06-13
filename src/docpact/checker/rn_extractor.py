"""Extractor de Reglas de Negocio de código existente.

Analiza codebases y extrae reglas de negocio implícitas.
Útil para:
- Crear librería de RNs por industria
- Migrar proyectos existentes a docpact
- Extraer RNs de repos open-source
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RNExtraida:
    """Una regla de negocio extraída del código."""

    categoria: str  # auth, ticket, notification, etc.
    titulo: str
    descripcion: str
    evidencia: str  # Código que sugiere la regla
    archivo: str
    linea: int
    confianza: str  # alta, media, baja
    tipo: str  # permiso, validacion, negocio, notificacion, auditoria


# ── Patrones de extracción por categoría ──

_PATRONES_RN = [
    # Autenticación y permisos
    {"categoria": "auth", "patron": "LoginRequiredMixin|login_required|permission_required", "titulo": "Requiere autenticación", "tipo": "permiso"},
    {"categoria": "auth", "patron": "is_superuser|is_admin|group.*admin", "titulo": "Requiere permisos de admin", "tipo": "permiso"},
    {"categoria": "auth", "patron": "has_perm\\(|check_permission", "titulo": "Verificación de permiso", "tipo": "permiso"},

    # Tickets y soporte
    {"categoria": "ticket", "patron": "class.*Ticket|Ticket\\.", "titulo": "Gestión de tickets", "tipo": "negocio"},
    {"categoria": "ticket", "patron": "status.*=.*('atendido'|'asignado'|'resuelto'|'pendiente')", "titulo": "Transición de estado de ticket", "tipo": "negocio"},
    {"categoria": "ticket", "patron": "prioridad|urgente|urgency", "titulo": "Sistema de prioridades", "tipo": "negocio"},

    # Notificaciones
    {"categoria": "notification", "patron": "send_mail|EmailMessage|notificar|notify", "titulo": "Notificación por email", "tipo": "notificacion"},
    {"categoria": "notification", "patron": "SMS|whatsapp|push_notification", "titulo": "Notificación push/SMS", "tipo": "notificacion"},

    # Auditoría
    {"categoria": "audit", "patron": "log\\(|logger\\.|AuditLog|bitacora|audit", "titulo": "Registro de auditoría", "tipo": "auditoria"},
    {"categoria": "audit", "patron": "created_at|updated_at|timestamp", "titulo": "Timestamps de auditoría", "tipo": "auditoria"},

    # Validaciones
    {"categoria": "validation", "patron": "raise.*Error|ValidationError|validate", "titulo": "Validación de datos", "tipo": "validacion"},
    {"categoria": "validation", "patron": "if not.*:.*raise|if.*is None.*raise", "titulo": "Validación de entrada", "tipo": "validacion"},

    # Pagos y facturación
    {"categoria": "billing", "patron": "payment|pago|factura|invoice|billing", "titulo": "Sistema de pagos", "tipo": "negocio"},
    {"categoria": "billing", "patron": "subscription|suscripcion|plan|precio", "titulo": "Sistema de suscripciones", "tipo": "negocio"},

    # Inventario
    {"categoria": "inventory", "patron": "stock|inventario|existencia|cantidad", "titulo": "Gestión de inventario", "tipo": "negocio"},
    {"categoria": "inventory", "patron": "warehouse|bodega|deposito", "titulo": "Gestión de almacén", "tipo": "negocio"},

    # Multi-tenant
    {"categoria": "tenant", "patron": "tenant|organization|company|empresa", "titulo": "Multi-tenancy", "tipo": "negocio"},
    {"categoria": "tenant", "patron": "schema|namespace|isolat", "titulo": "Aislamiento de datos", "tipo": "negocio"},

    # Roles
    {"categoria": "roles", "patron": "role|rol|group|grupo", "titulo": "Sistema de roles", "tipo": "permiso"},
    {"categoria": "roles", "patron": "admin|supervisor|tecnico|cliente", "titulo": "Roles predefinidos", "tipo": "permiso"},

    # SLA
    {"categoria": "sla", "patron": "sla|deadline|tiempo_limite|response_time", "titulo": "Acuerdo de nivel de servicio", "tipo": "negocio"},
    {"categoria": "sla", "patron": "timeout|expir|expira", "titulo": "Timeout/expiración", "tipo": "negocio"},

    # Estados
    {"categoria": "state", "patron": "status|estado|state|fase", "titulo": "Máquina de estados", "tipo": "negocio"},
    {"categoria": "state", "patron": "transition|transicion|cambio_estado", "titulo": "Transición de estado", "tipo": "negocio"},
]


def extraer_rns_de_archivo(archivo: Path) -> list[RNExtraida]:
    """Extrae reglas de negocio de un archivo Python."""
    try:
        contenido = archivo.read_text(encoding="utf-8")
        tree = ast.parse(contenido)
    except (SyntaxError, UnicodeDecodeError):
        return []

    rns = []
    lineas = contenido.split("\n")

    for nodo in ast.walk(tree):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Buscar en docstring
        docstring = ast.get_docstring(nodo) or ""
        for patron_info in _PATRONES_RN:
            if re.search(patron_info["patron"], docstring, re.IGNORECASE):
                rns.append(RNExtraida(
                    categoria=patron_info["categoria"],
                    titulo=patron_info["titulo"],
                    descripcion=f"Detectado en docstring de {nodo.name}",
                    evidencia=docstring[:100],
                    archivo=str(archivo),
                    linea=nodo.lineno,
                    confianza="alta",
                    tipo=patron_info["tipo"],
                ))

        # Buscar en código
        for subnodo in ast.walk(nodo):
            if not hasattr(subnodo, "lineno"):
                continue
            if subnodo.lineno < 1 or subnodo.lineno > len(lineas):
                continue

            linea_codigo = lineas[subnodo.lineno - 1]
            for patron_info in _PATRONES_RN:
                try:
                    if re.search(patron_info["patron"], linea_codigo, re.IGNORECASE):
                        # Evitar duplicados
                        if not any(r.linea == subnodo.lineno and r.titulo == patron_info["titulo"] for r in rns):
                            rns.append(RNExtraida(
                                categoria=patron_info["categoria"],
                                titulo=patron_info["titulo"],
                                descripcion=f"Detectado en {nodo.name}",
                                evidencia=linea_codigo.strip()[:100],
                                archivo=str(archivo),
                                linea=subnodo.lineno,
                                confianza="media",
                                tipo=patron_info["tipo"],
                            ))
                except re.error:
                    continue

    return rns


def extraer_rns_de_proyecto(raiz: Path) -> dict:
    """Extrae todas las reglas de negocio de un proyecto."""
    rns_totales = []
    archivos_escaneados = 0
    por_categoria = {}

    for archivo in raiz.rglob("*.py"):
        if any(p.startswith(".") or p in ("__pycache__", "venv", ".venv", "node_modules", "tests") for p in archivo.parts):
            continue
        if archivo.name.startswith("test_") or archivo.name == "conftest.py":
            continue

        rns = extraer_rns_de_archivo(archivo)
        rns_totales.extend(rns)
        archivos_escaneados += 1

    # Agrupar por categoría
    for rn in rns_totales:
        por_categoria.setdefault(rn.categoria, []).append(rn)

    # Generar RNs sugeridas (agrupadas por categoría)
    rns_sugeridas = []
    for categoria, rns in por_categoria.items():
        # Tomar la evidencia más representativa
        evidencias = list(set(r.evidencia for r in rns))
        rns_sugeridas.append({
            "categoria": categoria,
            "cantidad_evidencias": len(rns),
            "titulo_sugerido": f"RN-{categoria.upper()}-001",
            "descripcion_sugerida": f"Regla de {categoria} detectada en {len(rns)} lugares",
            "evidencias": evidencias[:5],
            "archivos": list(set(r.archivo for r in rns)),
        })

    return {
        "archivos_escaneados": archivos_escaneados,
        "rns_encontradas": len(rns_totales),
        "categorias": list(por_categoria.keys()),
        "por_categoria": {k: len(v) for k, v in por_categoria.items()},
        "rns_sugeridas": sorted(rns_sugeridas, key=lambda x: x["cantidad_evidencias"], reverse=True),
        "rnsDetalle": [
            {
                "categoria": r.categoria,
                "titulo": r.titulo,
                "descripcion": r.descripcion,
                "evidencia": r.evidencia,
                "archivo": r.archivo,
                "linea": r.linea,
                "confianza": r.confianza,
                "tipo": r.tipo,
            }
            for r in rns_totales[:50]  # Top 50
        ],
    }

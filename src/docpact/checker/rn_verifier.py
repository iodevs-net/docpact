"""Verificador de patrones RN hardcoded — valida que el código implemente las reglas.

Escanea el proyecto buscando CONTRATOs con rn: [RN-XXX], luego verifica
que cada RN tenga su patrón de implementación en el fuente.

Resultado por RN:
  PASS      — keyword(s) encontrado(s) en el archivo indicado
  FAIL      — keyword(s) ausente(s)
  NO_PATTERN— no hay patrón definido para esta RN

Solo depende de stdlib (pathlib).
"""

from __future__ import annotations

from pathlib import Path
# ── Patrones RN — cada entrada mapea un ID a su verificación ──────────────

RN_PATTERNS: dict[str, dict] = {
    # ── Core ticket lifecycle ──
    "RN-001": {"description": "Estados base del ciclo de vida", "file": "soporte/constants.py", "must_contain": ["class Estado", "ATENDER", "RESUELTO"]},
    "RN-002": {"description": "Solo remoto/laboratorio/logistica/en_terreno descuentan horas", "file": "soporte/constants.py", "must_contain": ["ESTADOS_FACTURABLES", "remoto"]},
    "RN-003": {"description": "Gastos se asocian a sesiones de trabajo", "file": "soporte/selectors/gastos.py", "must_contain": ["gastos"]},
    "RN-004": {"description": "No saltos entre estados", "file": "soporte/state_machine/builder.py", "must_contain": ["TRANSICIONES_PERMITIDAS"]},
    "RN-005": {"description": "Suspendido puede reanudarse", "file": "soporte/state_machine/builder.py", "must_contain": ["suspendido", "reanudar"]},
    "RN-006": {"description": "resuelto es terminal", "file": "soporte/constants.py", "must_contain": ["resuelto", "ESTADOS_TERMINALES"]},
    "RN-007": {"description": "Al resolver suma tiempo de sesiones", "file": "soporte/models/ticket.py", "must_contain": ["tiempo_total_horas"]},
    "RN-008": {"description": "RESTRINGIDO no crea tickets", "file": "soporte/services/tickets.py", "must_contain": ["RESTRINGIDO", "PermissionError"]},
    "RN-009": {"description": "Alerta al 80% de consumo", "file": "soporte/signals.py", "must_contain": ["80", "alerta"]},
    "RN-010": {"description": "Consumo al 100% bloquea", "file": "soporte/services/sesiones.py", "must_contain": ["disponibles", "horas_extra_aprobadas"]},
    "RN-011": {"description": "Contrato vigente para crear tickets", "file": "clientes/selectors_contrato.py", "must_contain": ["vigente"]},
    "RN-012": {"description": "Corte mensual cruce de meses", "file": "soporte/selectors/sesiones.py", "must_contain": ["mes"]},
    "RN-013": {"description": "Cliente ve solo sus tickets", "file": "soporte/selectors/tickets.py", "must_contain": ["cliente", "filtro"]},
    "RN-014": {"description": "Checklists de mantencion", "file": "soporte/services/checklist.py", "must_contain": ["ChecklistPlantillaService"]},
    "RN-015": {"description": "Adjuntos validados", "file": "soporte/models/adjunto.py", "must_contain": ["RN-015"]},

    # ── Security ──
    "RN-SEG-001": {"description": "Permisos por grupo", "file": "clientes/dtos_permisos.py", "must_contain": ["calcular_permisos"]},
    "RN-SEG-002": {"description": "Solo supervision asigna tareas", "file": "soporte/views/ticket_gestion.py", "must_contain": ["puede_asignar_tareas"]},
    "RN-SEC-001": {"description": "Sesion expira 1 hora", "file": "nucleo/middleware/session_inactivity.py", "must_contain": ["3600"]},
    "RN-SEC-002": {"description": "Lockout tras 5 intentos", "file": "nucleo/middleware/ip_block.py", "must_contain": ["blocked_ip", "is_ip_blocked"]},
    "RN-SEC-003": {"description": "Logout registra heartbeat", "file": "nucleo/signals.py", "must_contain": ["logout", "heartbeat"]},
    "RN-C-016": {"description": "Credenciales fuera de logs", "file": "config/settings/logging.py", "must_contain": ["FILTERED_PASSWORD", "sanitize"]},

    # ── Multi-tenant ──
    "RN-TNT-001": {"description": "TenantManager fail-closed", "file": "nucleo/managers.py", "must_contain": [".none()"]},
    "RN-CL-001": {"description": "Filtro tenant en tickets", "file": "soporte/selectors/tickets.py", "must_contain": ["para_usuario"]},
    "RN-CL-002": {"description": "Clientes solo ven su info", "file": "nucleo/selectors/media.py", "must_contain": ["find_media_owner"]},
    "RN-CL-003": {"description": "Permisos por rol", "file": "soporte/selectors/tickets.py", "must_contain": ["permisos"]},
    "RN-CL-005": {"description": "Eliminacion logica clientes", "file": "clientes/services.py", "must_contain": ["eliminar", "permanente"]},
    "RN-CL-006": {"description": "Admin puede ver todo", "file": "soporte/views/adjuntos.py", "must_contain": ["is_superuser"]},

    # ── Colaboradores ──
    "RN-COL-001": {"description": "Solo administracion crea colaboradores", "file": "nucleo/services/colaborador.py", "must_contain": ["administracion"]},
    "RN-COL-002": {"description": "Colaborador edita su propio perfil", "file": "nucleo/selectors/colaborador.py", "must_contain": ["colaborador_id"]},
    "RN-COL-003": {"description": "Perfil crea grupo", "file": "nucleo/services/perfil.py", "must_contain": ["grupo"]},
    "RN-COL-004": {"description": "Bitacora filtrada por tenant", "file": "soporte/models/bitacora.py", "must_contain": ["obtener_filtro_tenant"]},
    "RN-COL-005": {"description": "Filtro tenant universal", "file": "nucleo/selectors/tenant.py", "must_contain": ["tenant_filter"]},
    "RN-COL-006": {"description": "Notificaciones por rol", "file": "soporte/services/notificaciones.py", "must_contain": ["notificar"]},

    # ── Facturacion ──
    "RN-FAC-001": {"description": "Marcar tickets facturados", "file": "facturacion/services.py", "must_contain": ["marcar_tickets"]},
    "RN-FAC-002": {"description": "Contrato vigente", "file": "clientes/models.py", "must_contain": ["es_vigente"]},
    "RN-FAC-004": {"description": "Reset bolsa dia 1", "file": "soporte/management/commands/reset_bolsa_horas.py", "must_contain": ["bolsa", "reset"]},
    "RN-FAC-005": {"description": "Marcar horas prueba facturadas", "file": "soporte/management/commands/marcar_horas_prueba_facturadas.py", "must_contain": ["prueba", "facturadas"]},
    "RN-FAC-007": {"description": "Permisos gastos por rol", "file": "nucleo/models.py", "must_contain": ["puede_ver_todos_los_gastos"]},

    # ── Gastos ──
    "RN-GAS-001": {"description": "Gastos por sesion", "file": "soporte/selectors/sesiones.py", "must_contain": ["RN-GAS-001"]},
    "RN-GAS-002": {"description": "Gasto pagado requiere fecha", "file": "soporte/models/gasto.py", "must_contain": ["pagado", "fecha"]},
    "RN-GAS-003": {"description": "Pago por transferencia", "file": "soporte/services/gastos.py", "must_contain": ["transferencia"]},
    "RN-GAS-004": {"description": "Pago todos los viernes", "file": "soporte/services/gastos.py", "must_contain": ["viernes"]},

    # ── Inventario ──
    "RN-INV-001": {"description": "CRUD dispositivos", "file": "inventario/validators_import.py", "must_contain": ["validar"]},
    "RN-INV-002": {"description": "Mantencion preventiva", "file": "soporte/selectors/mantenimiento.py", "must_contain": ["mantencion"]},
    "RN-INV-003": {"description": "Alertas mantencion", "file": "inventario/models.py", "must_contain": ["mantencion"]},
    "RN-INV-004": {"description": "Checklist respuestas", "file": "soporte/views/checklists_respuestas.py", "must_contain": ["checklist"]},
    "RN-INV-005": {"description": "Supervision recibe alertas", "file": "inventario/management/commands/verificar_mantenciones.py", "must_contain": ["supervision"]},
    "RN-INV-006": {"description": "Marca global sin tenant", "file": "inventario/models.py", "must_contain": ["Marca", "global"]},

    # ── Notificaciones ──
    "RN-NOT-001": {"description": "Notificacion creacion ticket", "file": "soporte/signals.py", "must_contain": ["notificar_creacion"]},
    "RN-NOT-002": {"description": "Notificacion asignacion", "file": "soporte/services/notificaciones.py", "must_contain": ["notificar_asignacion"]},
    "RN-NOT-004": {"description": "Vencer tickets programados", "file": "soporte/management/commands/vencer_tickets_programados.py", "must_contain": ["programado", "vencer"]},
    "RN-NOT-005": {"description": "Notificacion error desarrollo", "file": "soporte/services/error_report.py", "must_contain": ["desarrollo", "notificacion"]},

    # ── Reportes ──
    "RN-RPT-002": {"description": "Reportes mensuales", "file": "soporte/management/commands/enviar_reportes_mensuales.py", "must_contain": ["mensuales"]},

    # ── Dashboard ──
    "RN-DSH-001": {"description": "Dashboard estadisticas", "file": "soporte/selectors/dashboard.py", "must_contain": ["get_dashboard_stats"]},
    "RN-DSH-002": {"description": "Metricas personales", "file": "soporte/selectors/dashboard.py", "must_contain": ["metricas"]},

    # ── Prioridad ──
    "RN-PRI-001": {"description": "Prioridad normal/urgente", "file": "soporte/models/ticket.py", "must_contain": ["PrioridadTicket"]},

    # ── Bitacora ──
    "RN-BIT-001": {"description": "Adjuntos publicos/privados", "file": "soporte/selectors/adjuntos.py", "must_contain": ["es_publico"]},
    "RN-BIT-002": {"description": "Bitacora visible por tenant", "file": "soporte/models/bitacora.py", "must_contain": ["obtener_filtro_tenant"]},
    "RN-BIT-003": {"description": "Bitacora adjunta imagenes", "file": "soporte/services_adjuntos.py", "must_contain": ["bitacora", "imagen"]},
    "RN-BIT-004": {"description": "Cambio estado en bitacora", "file": "soporte/signals.py", "must_contain": ["registrar_cambio_estado"]},

    # ── Auditoria ──
    "RN-AUD-001": {"description": "Todo cambio registrado", "file": "soporte/services/audit.py", "must_contain": ["registrar_evento"]},

    # ── Datos ──
    "RN-DAT-002": {"description": "Adjuntos caducidad 90 dias", "file": "soporte/services_adjuntos.py", "must_contain": ["ADJUNTO_EXPIRY_DAYS"]},

    # ── Desarrollo ──
    "RN-DEV-001": {"description": "Grupo desarrollo = administracion", "file": "nucleo/selectors/perfil.py", "must_contain": ["desarrollo"]},
    "RN-DEV-002": {"description": "Error report auto-asigna", "file": "soporte/services/error_report.py", "must_contain": ["desarrollo", "asignar"]},
    "RN-DEV-003": {"description": "Tab Desarrollo visible solo grupo", "file": "soporte/selectors/tickets.py", "must_contain": ["desarrollo"]},

    # ── SLA ──
    "RN-SLA-001": {"description": "SLA 15 min atender", "file": "soporte/management/commands/verificar_sla.py", "must_contain": ["15", "atender"]},
    "RN-SLA-002": {"description": "SLA minutos en estado", "file": "soporte/models/ticket.py", "must_contain": ["sla_minutos_en_estado"]},
    "RN-SLA-003": {"description": "Notificacion incumplimiento SLA", "file": "soporte/management/commands/verificar_sla.py", "must_contain": ["notificar", "supervisor"]},

    # ── Tickets ──
    "RN-TKT-001": {"description": "No eliminar con gastos", "file": "soporte/models/ticket.py", "must_contain": ["gasto", "eliminar"]},
    "RN-TKT-002": {"description": "No eliminar con gasto pagado", "file": "soporte/models/ticket.py", "must_contain": ["pagado"]},
    "RN-TKT-003": {"description": "Supervision anula tickets", "file": "soporte/models/ticket.py", "must_contain": ["supervision", "anular"]},
    "RN-TKT-004": {"description": "Solo anulado se elimina", "file": "soporte/views/ticket_gestion.py", "must_contain": ["anulado", "eliminar"]},
}


def _read_file(path: Path) -> str | None:
    """Lee archivo; retorna None si no existe."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return None


def verify_rn(rn_id: str, project_root: Path) -> dict:
    """Verifica un solo patrón RN en el código fuente.

    Returns dict con keys: rn_id, description, file, status, found, missing.
    status es 'PASS', 'FAIL', o 'NO_PATTERN'.
    """
    pattern = RN_PATTERNS.get(rn_id)
    if pattern is None:
        return {
            "rn_id": rn_id,
            "description": "",
            "file": "",
            "status": "NO_PATTERN",
            "found": [],
            "missing": [],
        }

    file_path = project_root / pattern["file"]
    source = _read_file(file_path)
    if source is None:
        return {
            "rn_id": rn_id,
            "description": pattern["description"],
            "file": pattern["file"],
            "status": "FAIL",
            "found": [],
            "missing": list(pattern["must_contain"]),
        }

    found: list[str] = []
    missing: list[str] = []
    for keyword in pattern["must_contain"]:
        if keyword in source:
            found.append(keyword)
        else:
            missing.append(keyword)

    status = "PASS" if not missing else "FAIL"
    return {
        "rn_id": rn_id,
        "description": pattern["description"],
        "file": pattern["file"],
        "status": status,
        "found": found,
        "missing": missing,
    }


def verify_all_rns(project_root: Path) -> list[dict]:
    """Verifica todos los patrones RN definidos."""
    return [verify_rn(rn_id, project_root) for rn_id in RN_PATTERNS]


def print_results(results: list[dict]) -> None:
    """Imprime resultados formateados a stdout."""
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    no_pattern = sum(1 for r in results if r["status"] == "NO_PATTERN")

    print(f"\n{'=' * 60}")
    print(f"  RN Pattern Verifier — {len(results)} RNs checked")
    print(f"{'=' * 60}\n")

    icons = {"PASS": "✅", "FAIL": "❌", "NO_PATTERN": "⚠️"}
    for r in results:
        icon = icons[r["status"]]
        line = f"  {icon} {r['rn_id']:<16} {r['status']:<12}"
        if r["description"]:
            line += f" {r['description']}"
        print(line)
        if r["status"] == "FAIL" and r["missing"]:
            print(f"     Missing: {', '.join(r['missing'])}")
            print(f"     File: {r['file']}")

    print(f"\n{'─' * 60}")
    print(f"  PASS: {passed}  FAIL: {failed}  NO_PATTERN: {no_pattern}")
    print(f"{'─' * 60}\n")

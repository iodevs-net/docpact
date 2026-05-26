"""Fixture: función con CONTRATO completo (todos los campos)."""


def sumar_sesiones(tickets: list) -> dict:
    """Calcula horas totales de sesiones.

    CONTRATO:
      input:
        tickets: list[Ticket] — Lista de tickets con sesiones precargadas.
      output: dict — HorasCalculadas con total_horas, total_segundos.
      side_effects: ninguno
      rn:
        - RN-002: solo sesiones completadas descuentan horas
      borde:
        - tickets vacío: retorna {'total_horas': 0, 'total_segundos': 0}
        - sesión sin fin: se ignora en el cálculo
      dependencias:
        - soporte/models/ticket.py::Ticket
    """
    # RN-002: filtrar solo sesiones completadas
    total_segundos = 0
    for ticket in (tickets or []):
        for sesion in getattr(ticket, 'sesiones', []):
            if sesion.get('fin'):
                total_segundos += (sesion['fin'] - sesion['inicio']).total_seconds()
    return {
        'total_horas': total_segundos / 3600,
        'total_segundos': total_segundos,
    }

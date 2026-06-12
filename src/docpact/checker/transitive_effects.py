"""Verificador de efectos secundarios transitivos.

Analiza el AST de una función, resuelve las funciones que llama usando el índice global,
y verifica que todos los efectos secundarios heredados estén debidamente declarados
en el contrato de la función origen.
"""

from __future__ import annotations

import ast
from typing import Optional

from docpact.checker.contract_index import ContractIndex, ImportResolver
from docpact.checker.side_effects import _extraer_llamadas
from docpact.models.contrato import Contrato, ErrorParser


def _satisface_efecto(efectos_declarados: set[str], efecto_requerido: str) -> bool:
    """Verifica de forma semántica si el efecto requerido está cubierto por las descripciones."""
    # service_delegation = delegation marker — always satisfies
    if "service_delegation" in efectos_declarados:
        return True
    # Si la categoría técnica exacta está declarada, es un match directo
    if efecto_requerido in efectos_declarados:
        return True

    # Mapeo semántico en base a palabras clave (soporta español)
    mapeo_claves = {
        "db_write": [
            "db_write",
            "bd",
            "base de datos",
            "crea",
            "guarda",
            "actualiza",
            "registra",
            "elimina",
            "anula",
            "insert",
            "update",
            "delete",
            "save",
            "persiste",
            "escribe",
            "modifica",
            "transaccion",
            "atomic",
        ],
        "email": [
            "email",
            "correo",
            "notifica",
            "mensaje",
            "mail",
            "send_mail",
            "destinatario",
        ],
        "audit": ["audit", "bitacora", "audita", "log", "historial", "evento"],
        "external": [
            "external",
            "externo",
            "api",
            "http",
            "request",
            "httpx",
            "urllib",
            "servicio",
        ],
        "notification": [
            "notification",
            "notifica",
            "mensaje",
            "sms",
            "push",
            "alerta",
        ],
        "subprocess": [
            "subprocess",
            "subproceso",
            "sub proceso",
            "exec",
            "shell",
            "command",
            "pipeline",
            "docker",
            "ps",
            "df",
            "uptime",
            "hostname",
            "uname",
            "nproc",
            "free",
            "parted",
            "ip",
            "ping",
            "curl",
            "wget",
        ],
        "file_read": [
            "file_read",
            "lectura de archivo",
            "lee archivo",
            "abre archivo",
            "open",
            "/proc",
            "/sys",
            "/etc",
            "read_text",
            "read_bytes",
        ],
        "http_get": [
            "http_get",
            "http get",
            "peticion http",
            "request http",
            "httpx",
            "requests",
            "urlopen",
            "netdata",
            "api rest",
            "endpoint",
        ],
    }

    claves = mapeo_claves.get(efecto_requerido, [efecto_requerido])

    # Revisar si alguna palabra clave está contenida en alguna declaración descriptiva
    for dec in efectos_declarados:
        dec_lower = dec.lower()
        if any(c in dec_lower for c in claves):
            return True

    # FIX: el parser actual devuelve el side_effect completo del callee
    # (ej: 'subprocess (docker info, hostname, uname)') en vez de solo la
    # keyword ('subprocess'). En ese caso, hay que extraer la keyword
    # (primera palabra antes del '(' o espacio) y buscar en el mapeo.
    if "(" in efecto_requerido:
        keyword = efecto_requerido.split("(", 1)[0].strip().lower()
    else:
        keyword = efecto_requerido.split(" ", 1)[0].strip().lower()
    if keyword in mapeo_claves:
        claves = mapeo_claves[keyword]
        for dec in efectos_declarados:
            dec_lower = dec.lower()
            if any(c in dec_lower for c in claves):
                return True

    return False


def check_transitive_effects(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    contrato: Contrato,
    imports: dict[str, str],
    index: ContractIndex,
    nombre_funcion: str,
    archivo: str,
    modulo_actual: str,
    clase_actual: Optional[str] = None,
) -> list[ErrorParser]:
    """Verifica que las llamadas a otras funciones no violen la declaración de side_effects.

    Si la función declara `side_effects: ninguno`, pero llama a otra función/método
    cuyo contrato declara side_effects reales, arroja un error.
    """
    errores: list[ErrorParser] = []
    llamadas = _extraer_llamadas(node)

    efectos_declarados = {s.descripcion.lower().strip() for s in contrato.side_effects}
    # service_delegation = 'I delegate, trust my callees' — skip transitive check
    if "service_delegation" in efectos_declarados:
        return []
    # Si declaró side_effects o heredó explícitamente, los metemos en un conjunto.
    # Si está vacío, representa "ninguno"

    # Mapear llamadas a sus efectos secundarios detectados en el índice
    llamadas_con_efectos: dict[str, list[str]] = {}

    for llamada in llamadas:
        # Resolver a través del índice
        contrato_idx = index.lookup(
            llamada,
            imports=imports,
            modulo_actual=modulo_actual,
            clase_contexto=clase_actual,
        )

        if contrato_idx and contrato_idx.side_effects:
            # Filtrar si tienen efectos que no sean "ninguno"
            efectos_callee = [e for e in contrato_idx.side_effects if e not in ("ninguno", "service_delegation")]
            if efectos_callee:
                llamadas_con_efectos[llamada] = efectos_callee

    # Si la función origen declara "ninguno" (sin efectos declarados)
    if not efectos_declarados:
        for llamada, efectos in llamadas_con_efectos.items():
            cats = ", ".join(efectos)
            errores.append(
                ErrorParser(
                    "side_effects",
                    f"'{nombre_funcion}' declara side_effects: ninguno, "
                    f"pero llama a '{llamada}' que produce side_effects: {cats}",
                    sugerencia=f"Agrega 'side_effects: {cats}' al CONTRATO de '{nombre_funcion}', "
                    f"o elimina/modifica la llamada a '{llamada}'",
                )
            )
    else:
        # Si la función origen declara efectos, verificar que los de sus callees estén cubiertos semánticamente
        for llamada, efectos in llamadas_con_efectos.items():
            for e in efectos:
                if not _satisface_efecto(efectos_declarados, e):
                    errores.append(
                        ErrorParser(
                            "side_effects",
                            f"'{nombre_funcion}' declara side_effects: {', '.join(efectos_declarados)}, "
                            f"pero llama a '{llamada}' que requiere la cobertura del efecto técnico: '{e}'",
                            sugerencia=f"Agrega '{e}' o una descripción en español que lo contenga (ej: 'guarda en bd' o 'envía email') al CONTRATO de '{nombre_funcion}'",
                        )
                    )

    return errores

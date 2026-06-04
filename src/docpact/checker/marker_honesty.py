"""Detector de markers # RN-XXX "decorativos" o "de delegación".

PROBLEMA
========
Un marker `# RN-XXX` en el body de una función solo indica presencia,
no que la función realmente implemente la regla. Esto crea falsa
seguridad: docpact reporta ✅ cuando la regla NO se implementa.

DETECCIÓN
=========
Usando `ast` de stdlib (sin dependencias nuevas), analizamos la
línea donde está cada marker. Si la línea es una delegación
(`return Service.method(...)` o `x = Service.method(...)`)
y la función destino no está en el scope de la función
analizada, emitimos un WARN.

DRY+SOLID+LEAN+KISS
===================
- Un solo archivo, una sola responsabilidad: "es marker honesto o no"
- Usa AST nativo de Python (no reinventa el parsing)
- No ejecuta código, solo análisis estático
- WARN, no ERROR: el agente decide si es válido o no
- Configurable en docpact.toml (puede desactivarse)

NO REINVENTA
============
- ruff ya valida estilo/complejidad → no hacemos eso
- pytest ya valida comportamiento → no ejecutamos tests
- bandit ya valida seguridad → no hacemos eso
"""
from __future__ import annotations

import ast
import re
from typing import Optional

from docpact.models.contrato import ErrorParser


# Prefijo de markers RN. Configurable pero default a "RN-".
_DEFAULT_RN_PREFIX = "RN-"


def _es_linea_delegacion(stmt: ast.stmt) -> bool:
    """Detecta si un statement es una delegación simple.

    Una delegación simple es:
    - `return Service.method(...)`  → ast.Return con ast.Call
    - `x = Service.method(...)`      → ast.Assign con ast.Call
    - `x: T = Service.method(...)`   → ast.AnnAssign con ast.Call

    NO se considera delegación:
    - `x = 1` (sin call)
    - `x = func()` donde func es local (definida arriba en el cuerpo)
    - Bloques `if/while/try` con lógica dentro

    KISS: no intentamos inferir si el call es a un service externo o
    a una función local. Eso requeriría resolución de símbolos
    (out of scope). Asumimos que si la línea es SOLO una llamada
    a un atributo (X.y), probablemente es delegación.
    """
    if isinstance(stmt, ast.Return) and stmt.value is not None:
        return _es_call_externo(stmt.value)

    if isinstance(stmt, ast.Assign):
        return len(stmt.targets) == 1 and _es_call_externo(stmt.value)

    if isinstance(stmt, ast.AnnAssign):
        return stmt.value is not None and _es_call_externo(stmt.value)

    return False


def _es_call_externo(expr: ast.expr) -> bool:
    """Detecta si una expresión es una llamada a un atributo (X.y())."""
    if not isinstance(expr, ast.Call):
        return False
    # X.y() → func es ast.Attribute
    if isinstance(expr.func, ast.Attribute):
        return True
    # func() directo (no X.y) → probablemente local
    return False


def _linea_tiene_marker_rn(
    linea: str,
    prefijo: str = _DEFAULT_RN_PREFIX,
) -> Optional[str]:
    """Extrae el primer ID RN-XXX de una línea. None si no hay."""
    match = re.search(rf"#\s*({re.escape(prefijo)}[\w-]+)", linea)
    return match.group(1) if match else None


def check_marker_honesty(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    contrato_rn_ids: list[str],
    fuente: str,
    nombre_funcion: str = "",
    prefijo: str = _DEFAULT_RN_PREFIX,
    enabled: bool = True,
) -> list[ErrorParser]:
    """Detecta markers # RN-XXX en líneas de delegación.

    Args:
        node: Nodo AST de la función.
        contrato_rn_ids: IDs RN declarados en el CONTRATO de esta función.
        fuente: Código fuente completo del archivo (necesario para acceder
                a las líneas exactas con sus comments).
        nombre_funcion: Nombre de la función (para mensajes).
        prefijo: Prefijo de RN (default "RN-").
        enabled: Si False, retorna lista vacía (check desactivado).

    Returns:
        Lista de WARNs. Lista vacía si todos los markers son honestos.
    """
    if not enabled:
        return []

    if not contrato_rn_ids:
        return []

    if not hasattr(node, "end_lineno") or node.end_lineno is None:
        return []

    lineas = fuente.split("\n")
    inicio = node.lineno  # 1-based: la firma está en lineno
    fin = node.end_lineno

    warnings: list[ErrorParser] = []

    for stmt in node.body:
        # Saltar el docstring (primer statement si es Expr con Constant str)
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            if isinstance(stmt.value.value, str):
                continue

        stmt_line = stmt.lineno  # 1-based
        if stmt_line < inicio or stmt_line > fin:
            continue

        linea_texto = lineas[stmt_line - 1] if stmt_line - 1 < len(lineas) else ""
        rn_id = _linea_tiene_marker_rn(linea_texto, prefijo)

        if rn_id is None:
            continue

        # ¿Este marker está en el CONTRATO?
        if rn_id not in contrato_rn_ids:
            continue

        if _es_linea_delegacion(stmt):
            warnings.append(
                ErrorParser(
                    campo="rn",
                    mensaje=(
                        f"'{nombre_funcion}': {rn_id} marcada en línea de "
                        f"delegación (línea {stmt_line}). La función no "
                        f"parece implementar la lógica de la regla, solo "
                        f"delega a otro método. Verificar manualmente."
                    ),
                    linea=stmt_line,
                    sugerencia=(
                        f"Si la regla se implementa en el método llamado, "
                        f"mover {rn_id} al CONTRATO de ese método. Si se "
                        f"implementa aquí, agregar la lógica y mantener "
                        f"el marker en una línea con código de la regla."
                    ),
                )
            )

    return warnings


def check_marcador_concentrado(
    contrato_rn_ids: list[str],
    nombre_funcion: str = "",
    umbral: int = 5,
    enabled: bool = True,
) -> Optional[ErrorParser]:
    """Detecta funciones con demasiadas RNs declaradas (sospechoso).

    Una función con >umbral RNs es un red flag: probable AI slop o
    responsabilidad mal asignada. Cada RN debería estar donde
    realmente se implementa.

    Args:
        contrato_rn_ids: IDs RN declarados en el CONTRATO.
        nombre_funcion: Nombre de la función (para mensajes).
        umbral: Máximo de RNs antes de emitir WARN. Default 5.
        enabled: Si False, retorna None (check desactivado).

    Returns:
        WARN si se excede el umbral, None en caso contrario.
    """
    if not enabled:
        return None

    if len(contrato_rn_ids) <= umbral:
        return None

    return ErrorParser(
        campo="rn",
        mensaje=(
            f"'{nombre_funcion}' declara {len(contrato_rn_ids)} RNs "
            f"(umbral: {umbral}). Sospechoso: probable responsabilidad "
            f"mal asignada o comments decorativos. Verificar que cada "
            f"RN realmente se implemente en esta función."
        ),
        sugerencia=(
            "Dividir en funciones más pequeñas, cada una con 1-3 RNs "
            "claramente implementadas. Las RNs de delegación deben "
            "estar en el método destino, no en el caller."
        ),
    )

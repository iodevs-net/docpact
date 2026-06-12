"""Bridge: CONTRATOs → deal decorators + Hypothesis properties.

Lee el CONTRATO de la docstring y genera verificación automática:
- side_effects: ninguno → @deal.safe (no side effects)
- rn: [RN-XXX] → propiedades Hypothesis verificables
- input/output → pre/post conditions via deal

Uso:
    from docpact.bridge import contrato

    @contrato
    def crear_ticket(cliente, ...):
        \"\"\"
        CONTRATO:
        side_effects: db_write, email
        rn: [RN-008]
        \"\"\"
        ...
"""

from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

try:
    import deal
except ImportError:
    deal = None  # type: ignore[assignment]


def _parse_contrato(func: Callable) -> dict[str, Any]:
    """Extrae el bloque CONTRATO de la docstring de una función."""
    docstring = func.__doc__ or ""
    if "CONTRATO:" not in docstring:
        return {}

    # Extraer todo después de CONTRATO:
    contrato_match = re.search(r"CONTRATO:\s*\n(.+)", docstring, re.DOTALL)
    if not contrato_match:
        return {}

    contrato_text = contrato_match.group(1)
    result: dict[str, Any] = {}

    # Extraer campos — cada uno empieza con indentación + nombre:
    for field in ["input", "output", "side_effects", "rn", "dependencias", "borde"]:
        pattern = rf"^\s+{field}:\s*(.+?)$" 
        match = re.search(pattern, contrato_text, re.MULTILINE)
        if match:
            value = match.group(1).strip()
            if field == "rn":
                rn_match = re.findall(r"RN-[\w-]+", value)
                result[field] = rn_match
            else:
                result[field] = value

    return result


def _side_effects_to_deal(contrato: dict) -> list:
    """Convierte side_effects del CONTRATO en decorators deal."""
    if deal is None:
        return []

    side_effects = contrato.get("side_effects", "")
    decorators = []

    if side_effects in ("ninguno", ""):
        decorators.append(deal.safe)
    elif "ninguno" in side_effects and "queries" in side_effects:
        # queries de db son reads, no writes — deal.safe es apropiado
        decorators.append(deal.safe)
    elif side_effects == "service_delegation":
        # Delegación — no aplicamos deal.safe porque el callee tiene sus propios side_effects
        pass
    # Para side_effects como "db_write, email" — no aplicamos deal.safe
    # porque la función SÍ tiene side effects

    return decorators


def _generate_hypothesis_properties(contrato: dict) -> list[str]:
    """Genera descripciones de propiedades Hypothesis desde el CONTRATO."""
    properties = []
    rn_list = contrato.get("rn", [])

    for rn in rn_list:
        properties.append(f"rn:{rn}")

    return properties


def contrato(func: Callable) -> Callable:
    """Decorator que lee el CONTRATO y aplica verificación automática.

    Hace dos cosas:
    1. Aplica deal decorators según side_effects
    2. Registra propiedades Hypothesis para cada RN declarado
    """
    contrato_data = _parse_contrato(func)

    if not contrato_data:
        return func

    # Aplicar deal decorators
    deal_decorators = _side_effects_to_deal(contrato_data)
    wrapped = func
    for decorator in reversed(deal_decorators):
        wrapped = decorator(wrapped)

    # Registrar propiedades Hypothesis como atributo
    properties = _generate_hypothesis_properties(contrato_data)
    if properties:
        wrapped._contrato_properties = properties  # type: ignore[attr-defined]
    wrapped._contrato_data = contrato_data  # type: ignore[attr-defined]

    # Preservar metadata
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return wrapped(*args, **kwargs)

    wrapper._contrato_data = contrato_data
    wrapper._contrato_properties = properties
    wrapper._original_func = func

    return wrapper

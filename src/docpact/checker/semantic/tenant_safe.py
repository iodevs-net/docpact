"""Validador: tenant_safe — detecta usos inseguros de modelos sin tenant."""

from __future__ import annotations

import ast

from docpact.models.contrato import ErrorParser


def validar_tenant_safe(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict,
) -> list[ErrorParser]:
    """Detecta usos inseguros de modelos multi-tenant.

    Spec esperado:
        type = "tenant_safe"
        forbid = ["unfiltered_objects", ".objects.all()", ".objects.filter()"]
            # substrings prohibidos (default: ["unfiltered_objects"])

    Estrategia: busca usos directos de managers sin `para_usuario()` o
    escapes inseguros. Es heurístico — el agente debe declarar
    explícitamente cuándo un escape es legítimo.
    """
    forbid = spec.get("forbid", ["unfiltered_objects", ".objects.all", ".objects.filter"])
    errores: list[ErrorParser] = []

    try:
        tree = ast.parse(codigo_fuente)
    except SyntaxError:
        return []

    # Deduplicar por (linea, token) — ast.walk recorre padres e hijos,
    # y muchos nodos contienen la misma substring prohibida.
    vistos: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            continue
        # Match por nombre de atributo (ej: unfiltered_objects)
        if isinstance(node, ast.Attribute) and node.attr in forbid:
            key = (node.lineno, node.attr)
            if key in vistos:
                continue
            vistos.add(key)
            errores.append(
                ErrorParser(
                    "rn_semantica",
                    f"RN {rn_id}: uso de '{node.attr}' detectado (posible escape multi-tenant)",
                    linea=node.lineno,
                    sugerencia="Si es legítimo, agrega comentario '# docpact: tenant-escape'",
                )
            )
            continue
        # Match por substring del código unparseado (ej: ".raw(")
        try:
            rendered = ast.unparse(node)
        except Exception:
            continue
        for token in forbid:
            if token in rendered and not isinstance(node, ast.Attribute):
                lineno = getattr(node, "lineno", 0)
                key = (lineno, token)
                if key in vistos:
                    continue
                vistos.add(key)
                errores.append(
                    ErrorParser(
                        "rn_semantica",
                        f"RN {rn_id}: uso de '{token}' detectado (escape multi-tenant)",
                        linea=lineno,
                        sugerencia="Si es legítimo, agrega comentario '# docpact: tenant-escape'",
                    )
                )
                break

    return errores

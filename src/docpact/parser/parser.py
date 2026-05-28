"""Parser de tokens CONTRATO a modelo Contrato.

Convierte la lista de tokens producida por el lexer en una instancia
de Contrato con sus campos estructurados.
"""

from __future__ import annotations

from docpact.models.contrato import (
    CampoInput,
    CasoBorde,
    Contrato,
    Dependencia,
    ErrorParser,
    ReglaNegocio,
    SideEffect,
)
from typing import Any

from docpact.parser.lexer import TipoToken, Token


def parsear(tokens: list[Token]) -> tuple[Contrato, list[ErrorParser]]:
    """Convierte tokens de un bloque CONTRATO en un modelo Contrato.

    Construye el Contrato al final para respetar frozen=True.

    Args:
        tokens: Lista de tokens del lexer.

    Returns:
        Tupla (Contrato, errores) donde errores contiene advertencias
        o errores de parseo (parseo parcial).
    """
    errores: list[ErrorParser] = []

    if not tokens:
        return Contrato(), [
            ErrorParser("general", "No se encontró bloque CONTRATO en el docstring")
        ]

    # Mutable accumulators
    input_fields: dict[str, CampoInput] = {}
    output: str | None = None
    output_desc: str = ""
    side_effects: list[SideEffect] = []
    rn_list: list[ReglaNegocio] = []
    borde_list: list[CasoBorde] = []
    deps_list: list[Dependencia] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.tipo == TipoToken.MARCA_CONTRATO:
            i += 1
            continue

        if token.tipo == TipoToken.CAMPO_COMPUESTO:
            campo = token.valor
            i, nuevos = _parsear_campo_compuesto(tokens, i + 1, campo, errores)
            _fusionar_resultados(
                campo, nuevos, input_fields, rn_list, borde_list, deps_list
            )
            continue

        if token.tipo == TipoToken.CAMPO_SIMPLE:
            n, side, out_type, out_desc, datos_extra = _parsear_campo_simple(
                token, i, errores
            )
            i = n
            if side is not None:
                side_effects = side
            if out_type is not None:
                output = out_type
                output_desc = out_desc
            if datos_extra:
                if datos_extra["campo"] == "rn":
                    for item in datos_extra["items"]:
                        rn_list.append(ReglaNegocio(id=str(item)))
                elif datos_extra["campo"] == "borde":
                    for item in datos_extra["items"]:
                        borde_list.append(
                            CasoBorde(
                                condicion=str(item),
                                comportamiento=""
                                if isinstance(item, str)
                                else str(item.get("comportamiento", "")),
                            )
                        )
                elif datos_extra["campo"] == "dependencias":
                    for item in datos_extra["items"]:
                        deps_list.append(Dependencia(ref=str(item)))
            continue

        i += 1

    contrato = Contrato(
        input=input_fields,
        output=output,
        output_descripcion=output_desc,
        side_effects=side_effects,
        rn=rn_list,
        borde=borde_list,
        dependencias=deps_list,
    )
    return contrato, errores


def _parsear_campo_simple(
    token: Token,
    idx: int,
    errores: list[ErrorParser],
) -> tuple[int, list[SideEffect] | None, str | None, str, dict[str, Any] | None]:
    """Parsea 'side_effects: valor', 'output: type — desc', o arrays JSON inline.

    Arrays JSON inline: rn: [RN-001], dependencias: ["a.py::X"]

    Returns:
        (idx_siguiente, side_effects_list, output_type, output_desc, datos_extra)
    """
    import json

    partes = token.valor.split(":", 1)
    if len(partes) < 2:
        errores.append(
            ErrorParser(
                "general", f"Campo simple mal formado: {token.valor}", token.linea
            )
        )
        return idx + 1, None, None, "", None

    nombre = partes[0].strip()
    valor = partes[1].strip()

    if nombre == "side_effects":
        if valor.lower() == "ninguno":
            return idx + 1, [], None, "", None
        items = [v.strip() for v in valor.split(",")]
        se_list = [SideEffect(descripcion=item) for item in items if item]
        return idx + 1, se_list, None, "", None

    elif nombre == "output":
        if " — " in valor:
            tipo, desc = valor.split(" — ", 1)
            return idx + 1, None, tipo.strip(), desc.strip(), None
        return idx + 1, None, valor, "", None

    # JSON array inline: rn: [RN-001], dependencias: ["a.py::X"]
    if valor.startswith("[") and valor.endswith("]"):
        try:
            raw = json.loads(valor)
            if isinstance(raw, list):
                return idx + 1, None, None, "", {"campo": nombre, "items": raw}
        except json.JSONDecodeError:
            inner = valor[1:-1].strip()
            if inner:
                raw_items = [item.strip() for item in inner.split(",") if item.strip()]
                if raw_items:
                    return (
                        idx + 1,
                        None,
                        None,
                        "",
                        {"campo": nombre, "items": raw_items},
                    )

    return idx + 1, None, None, "", None


def _parsear_campo_compuesto(
    tokens: list[Token],
    idx: int,
    campo: str,
    errores: list[ErrorParser],
) -> tuple[int, dict[str, Any]]:
    """Parsea un campo compuesto (input, rn, borde, dependencias).

    Returns:
        (idx_siguiente, dict_resultado)
    """
    resultado: dict[str, Any] = {
        "input": [],
        "rn": [],
        "borde": [],
        "dependencias": [],
    }

    while idx < len(tokens):
        token = tokens[idx]

        # Salir si encontramos otro campo raíz
        if token.tipo in (TipoToken.CAMPO_COMPUESTO, TipoToken.CAMPO_SIMPLE):
            break

        if token.tipo == TipoToken.SUB_CAMPO:
            if campo == "input":
                _procesar_input(token, resultado, errores)
            elif campo == "borde":
                partes = token.valor.split(":", 1)
                if len(partes) >= 2:
                    resultado["borde"].append(
                        CasoBorde(
                            condicion=partes[0].strip(),
                            comportamiento=partes[1].strip(),
                        )
                    )
            idx += 1
            continue

        if token.tipo == TipoToken.ITEM_LISTA:
            _procesar_item_lista(campo, token, resultado, errores)
            idx += 1
            continue

        idx += 1

    return idx, resultado


def _procesar_input(
    token: Token,
    resultado: dict[str, Any],
    errores: list[ErrorParser],
) -> None:
    """Procesa 'param_name: type — description'."""
    linea = token.valor
    partes = linea.split(":", 1)
    if len(partes) >= 2:
        nombre = partes[0].strip()
        resto = partes[1].strip()
        if "—" in resto:
            tipo, desc = resto.split("—", 1)
            resultado["input"].append(
                CampoInput(
                    nombre=nombre,
                    tipo=tipo.strip(),
                    descripcion=desc.strip(),
                )
            )
        else:
            resultado["input"].append(CampoInput(nombre=nombre, tipo=resto))
    else:
        errores.append(
            ErrorParser(
                "input",
                f"Formato inválido: '{linea}'",
                token.linea,
                sugerencia="Usa 'nombre: tipo — descripción'",
            )
        )


def _procesar_item_lista(
    campo: str,
    token: Token,
    resultado: dict[str, Any],
    errores: list[ErrorParser],
) -> None:
    """Procesa '- item' dentro de rn, borde, dependencias."""
    linea = token.valor.lstrip("- ").strip()

    if campo in ("rn", "reglas"):
        if ":" in linea:
            rid, desc = linea.split(":", 1)
            resultado["rn"].append(
                ReglaNegocio(
                    id=rid.strip(),
                    descripcion=desc.strip(),
                )
            )
        else:
            resultado["rn"].append(ReglaNegocio(id=linea))

    elif campo == "borde":
        if ":" in linea:
            cond, comp = linea.split(":", 1)
            resultado["borde"].append(
                CasoBorde(
                    condicion=cond.strip(),
                    comportamiento=comp.strip(),
                )
            )
        else:
            errores.append(
                ErrorParser(
                    "borde",
                    f"Caso borde sin ':' separador: '{linea}'",
                    token.linea,
                    sugerencia="Usa 'condición: comportamiento esperado'",
                )
            )

    elif campo == "dependencias":
        resultado["dependencias"].append(Dependencia(ref=linea))


def _fusionar_resultados(
    campo: str,
    datos: dict[str, Any],
    input_fields: dict[str, CampoInput],
    rn_list: list[ReglaNegocio],
    borde_list: list[CasoBorde],
    deps_list: list[Dependencia],
) -> None:
    """Fusiona resultados de un campo compuesto en los acumuladores."""
    if campo == "input":
        for ci in datos["input"]:
            input_fields[ci.nombre] = ci
    elif campo in ("rn", "reglas"):
        rn_list.extend(datos["rn"])
    elif campo == "borde":
        borde_list.extend(datos["borde"])
    elif campo == "dependencias":
        deps_list.extend(datos["dependencias"])

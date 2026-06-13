"""Validador: state_transition — matrices de transición de estado."""

from __future__ import annotations

import ast
from pathlib import Path

from docpact.models.contrato import ErrorParser

from ._common import extraer_dict_ast


def validar_state_transition(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict,
) -> list[ErrorParser]:
    """Valida que una matriz de transiciones contenga la transicion esperada.

    Soporta dos fuentes (mutuamente excluyentes):
    - YAML: yaml_source + yaml_estados_key (lee directo del YAML, sin duplicacion)
    - AST: modulo + matriz_attr (busca dict literal en codigo Python)

    Spec YAML:
        type = "state_transition"
        from_estado = "suspendido"
        to_cualquiera = ["asignado", "en_traslado"]
        yaml_source = "soporte/state_machine/tickets.yaml"
        yaml_estados_key = "estados"  # default: "estados"

    Spec AST (legacy):
        type = "state_transition"
        from_estado = "suspendido"
        to_cualquiera = ["asignado"]
        matriz_attr = "TRANSICIONES_PERMITIDAS"
        modulo = "soporte/state_machine/builder.py"
    """
    from_estado = spec.get("from_estado")
    to_estado = spec.get("to_estado")
    to_cualquiera = spec.get("to_cualquiera", [])
    yaml_source = spec.get("yaml_source")

    if not from_estado or (not to_estado and not to_cualquiera):
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: state_transition sin 'from_estado' o 'to_estado/to_cualquiera'",
                sugerencia="Verifica el spec en docpact.toml",
            )
        ]

    # Dispatch: YAML o AST
    if yaml_source:
        matriz = extraer_yaml(yaml_source, spec, contexto, rn_id)
    else:
        matriz = extraer_ast(spec, contexto, rn_id)

    if isinstance(matriz, list):  # Es una lista de errores
        return matriz

    # Validar transiciones contra la matriz
    return validar_transiciones(matriz, from_estado, to_estado, to_cualquiera, rn_id)


def validar_transiciones(
    matriz: dict,
    from_estado: str,
    to_estado: str | None,
    to_cualquiera: list[str],
    rn_id: str,
) -> list[ErrorParser]:
    """Valida que la transicion exista en la matriz."""
    matriz_lower = {k.lower(): v for k, v in matriz.items()}
    from_estado_lower = from_estado.lower()

    transiciones = matriz_lower.get(from_estado_lower, [])
    if not transiciones:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: estado origen '{from_estado}' no existe en la matriz",
                sugerencia=f"Estados disponibles: {sorted(matriz.keys())}",
            )
        ]

    destinos_esperados = [to_estado] if to_estado else to_cualquiera
    destinos_lower = {d.lower() for d in transiciones}
    destinos_match = [d for d in destinos_esperados if d.lower() in destinos_lower]

    if not destinos_match:
        destinos_str = ", ".join(transiciones)
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: transicion '{from_estado}' -> {destinos_esperados} no encontrada. "
                f"Permitidos desde '{from_estado}': {destinos_str}",
                sugerencia=f"Agrega {destinos_esperados} a la matriz de transiciones",
            )
        ]

    return []


def extraer_yaml(
    yaml_source: str,
    spec: dict,
    contexto: dict,
    rn_id: str,
) -> dict | list[ErrorParser]:
    """Extrae la matriz de transiciones desde un archivo YAML.

    Formato esperado del YAML:
        estados:
          suspendido:
            transiciones: [asignado, en_traslado, ...]
    """
    try:
        import yaml
    except ImportError:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: yaml_source requiere PyYAML instalado (pip install pyyaml)",
                sugerencia="Instala PyYAML o usa el path AST (modulo + matriz_attr)",
            )
        ]

    yaml_path = Path(yaml_source)
    if not yaml_path.is_absolute():
        proyecto_root = contexto.get("proyecto_root")
        if proyecto_root:
            yaml_path = Path(proyecto_root) / yaml_source

    if not yaml_path.exists():
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: yaml_source '{yaml_source}' no encontrado",
                sugerencia=f"Verifica: {yaml_path}",
            )
        ]

    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as e:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: no se pudo parsear YAML: {e}",
            )
        ]

    if not isinstance(data, dict):
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: YAML no es un dict (tipo: {type(data).__name__})",
            )
        ]

    estados_key = spec.get("yaml_estados_key", "estados")
    estados = data.get(estados_key)
    if not isinstance(estados, dict):
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: YAML no tiene '{estados_key}' como dict",
                sugerencia=f"Keys disponibles: {sorted(data.keys())}",
            )
        ]

    matriz = {}
    for estado, config in estados.items():
        if isinstance(config, dict):
            matriz[estado] = config.get("transiciones", [])
    return matriz


def extraer_ast(
    spec: dict,
    contexto: dict,
    rn_id: str,
) -> dict | list[ErrorParser]:
    """Extrae la matriz de transiciones desde un dict literal en codigo Python (legacy)."""
    matriz_attr = spec.get("matriz_attr", "TRANSICIONES_PERMITIDAS")
    modulo_path = spec.get("modulo")

    if not modulo_path:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: state_transition sin 'modulo' ni 'yaml_source'",
                sugerencia="Agrega 'modulo' o 'yaml_source' al spec",
            )
        ]

    modulo = Path(modulo_path)
    if not modulo.is_absolute():
        proyecto_root = contexto.get("proyecto_root")
        if proyecto_root:
            modulo = Path(proyecto_root) / modulo_path

    if not modulo.exists():
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: modulo '{modulo_path}' no encontrado",
                sugerencia=f"Verifica que el archivo existe: {modulo}",
            )
        ]

    try:
        fuente_modulo = modulo.read_text(encoding="utf-8")
        tree = ast.parse(fuente_modulo, filename=str(modulo))
    except (SyntaxError, UnicodeDecodeError) as e:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: no se pudo parsear {modulo_path}: {e}",
            )
        ]

    matriz = extraer_dict_ast(tree, matriz_attr)
    if matriz is None:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: no se encontro dict '{matriz_attr}' en {modulo_path}",
                sugerencia=f"Verifica que '{matriz_attr}' esta definido como dict literal",
            )
        ]

    return matriz

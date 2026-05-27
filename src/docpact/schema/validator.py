"""Validador de CONTRATOS contra JSON Schema.

Usa jsonschema si está disponible; si no, hace validación básica.
"""

from __future__ import annotations

from docpact.models.contrato import Contrato, ErrorParser


def validar(
    contrato: Contrato,
    types_allowlist: set[str] | None = None,
) -> list[ErrorParser]:
    """Valida un Contrato contra el schema y reglas del protocolo.

    No requiere jsonschema — hace validación estructural directa.

    Args:
        contrato: Instancia de Contrato a validar.
        types_allowlist: Tipos que nunca deben generar warning (ej: "Any", "str").

    Returns:
        Lista de errores de validación. Vacía si es válido.
    """
    errores: list[ErrorParser] = []

    _validar_side_effects(contrato, errores)
    _validar_rn(contrato, errores)
    _validar_input(contrato, errores, types_allowlist)
    _validar_dependencias(contrato, errores)

    return errores


def _validar_side_effects(contrato: Contrato, errores: list[ErrorParser]) -> None:
    """side_effects: verifica que las descripciones no estén vacías."""
    for se in contrato.side_effects:
        if len(se.descripcion) < 2:
            errores.append(
                ErrorParser(
                    "side_effects",
                    f"Side effect demasiado corto: '{se.descripcion}'",
                    sugerencia="Usa descripciones más descriptivas (>2 caracteres)",
                )
            )


def _validar_rn(contrato: Contrato, errores: list[ErrorParser]) -> None:
    """Los IDs de reglas de negocio deben seguir el patrón RN-XXX."""
    import re

    patron = re.compile(r"^RN-\d{3,}$")
    for rn in contrato.rn:
        if not patron.match(rn.id):
            errores.append(
                ErrorParser(
                    "rn",
                    f"ID de regla de negocio inválido: '{rn.id}'",
                    sugerencia="Usa formato RN-XXX (ej: RN-010, RN-042)",
                )
            )


def _validar_input(
    contrato: Contrato,
    errores: list[ErrorParser],
    types_allowlist: set[str] | None = None,
) -> None:
    """Los inputs deben tener tipo no vacío. Tipos en allowlist se omiten."""
    types_allowlist = types_allowlist or set()
    for nombre, campo in contrato.input.items():
        if campo.tipo in types_allowlist:
            continue  # Tipo permitido, no validar
        if not campo.tipo:
            errores.append(
                ErrorParser(
                    "input",
                    f"Input '{nombre}' sin tipo declarado",
                    sugerencia="Agrega el tipo: 'nombre: type — descripción'",
                )
            )


def _validar_dependencias(contrato: Contrato, errores: list[ErrorParser]) -> None:
    """Las dependencias deben tener formato válido y no contener '..' (path traversal)."""
    import re

    # Permite: alfanumérico, _, /, -, . (solo para extensiones de archivo)
    # Prohíbe: .. (path traversal)
    # Formato: ruta/archivo.py::Simbolo o ruta/archivo.py
    patron = re.compile(r"^[a-zA-Z0-9_/.\-]+(::[a-zA-Z_][a-zA-Z0-9_.]*)?$")
    for dep in contrato.dependencias:
        if not patron.match(dep.ref):
            errores.append(
                ErrorParser(
                    "dependencias",
                    f"Dependencia con formato inválido: '{dep.ref}'",
                    sugerencia="Usa 'ruta/archivo.py::Simbolo' o 'ruta/archivo.py'",
                )
            )
        elif ".." in dep.ref:
            errores.append(
                ErrorParser(
                    "dependencias",
                    f"Dependencia contiene '..' (path traversal no permitido): '{dep.ref}'",
                    sugerencia="Usa rutas absolutas relativas al proyecto, no '..'",
                )
            )

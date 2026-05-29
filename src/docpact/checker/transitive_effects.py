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
            efectos_callee = [e for e in contrato_idx.side_effects if e != "ninguno"]
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
        # Si la función origen declara efectos, verificar que los de sus callees estén incluidos
        for llamada, efectos in llamadas_con_efectos.items():
            for e in efectos:
                if e not in efectos_declarados:
                    errores.append(
                        ErrorParser(
                            "side_effects",
                            f"'{nombre_funcion}' declara side_effects: {', '.join(efectos_declarados)}, "
                            f"pero llama a '{llamada}' que también produce: '{e}'",
                            sugerencia=f"Agrega '{e}' al CONTRATO de '{nombre_funcion}'",
                        )
                    )

    return errores

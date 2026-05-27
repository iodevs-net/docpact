"""Verificador de tests de RN (reglas de negocio).

Para cada RN-XXX declarada en un CONTRATO, debe existir un archivo
`tests/rn/test_rn_XXX.py` en la raíz del proyecto.

Esto cierra el gap: un agente puede escribir `# RN-XXX` en un comentario
(lo que ya verifica rn_checker.py), pero si la regla no está implementada
como test, docpact lo detecta como error.

SRP: El CONTRATO documenta la RN, el test verifica, docpact conecta ambos.
"""

from __future__ import annotations

from pathlib import Path

from docpact.models.contrato import ErrorParser


def check_rn_tests(
    rn_ids: list[str],
    proyecto_root: Path | None,
    nombre_funcion: str = "",
    prefijo: str = "RN-",
) -> list[ErrorParser]:
    """Verifica que exista un archivo tests/rn/test_rn_{XXX}.py para cada RN.

    Args:
        rn_ids: Lista de IDs de reglas de negocio (ej: ["RN-010", "RN-005"]).
        proyecto_root: Raíz del proyecto donde buscar tests/rn/.
        nombre_funcion: Nombre de la función (para errores).
        prefijo: Prefijo de reglas (default: RN-).

    Returns:
        Lista de errores para RNs sin test correspondiente.
    """
    if not rn_ids or proyecto_root is None:
        return []

    test_dir = proyecto_root / "tests" / "rn"
    if not test_dir.is_dir():
        return [
            ErrorParser(
                "rn_tests",
                f"Directorio 'tests/rn/' no encontrado en {proyecto_root}. "
                "Crea tests/rn/test_rn_XXX.py para cada RN declarada.",
                sugerencia="Ejecuta: mkdir -p tests/rn/",
            )
        ]

    errores: list[ErrorParser] = []
    for rn_id in rn_ids:
        rn_id = rn_id.strip()
        if not rn_id:
            continue
        # Extraer el número después del prefijo: RN-010 → 010
        if rn_id.startswith(prefijo):
            numero = rn_id[len(prefijo):]
        else:
            # IDs sin prefijo estándar se omiten (pueden ser RN-SEG-005, etc.)
            continue

        test_file = test_dir / f"test_rn_{numero}.py"
        if not test_file.exists():
            errores.append(ErrorParser(
                "rn_tests",
                f"'{nombre_funcion}': RN '{rn_id}' declarada en CONTRATO "
                f"pero no existe test en {test_file}",
                sugerencia=f"Crea {test_file} con Hypothesis PBT "
                          f"y escribe # {rn_id} en el docstring del test.",
            ))

    return errores

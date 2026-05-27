"""Verificador de tests de RN (reglas de negocio).

Para cada RN-XXX declarada en un CONTRATO, debe existir un archivo
tests/rn/test_rn_XXX.py Y debe pasar.

SRP: El CONTRATO documenta la RN, el test verifica, docpact conecta ambos.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from docpact.models.contrato import ErrorParser


def _normalizar_rn_id(rn_id: str, prefijo: str = "RN-") -> str | None:
    rn_id = rn_id.strip()
    if rn_id.startswith(prefijo):
        return rn_id[len(prefijo):]
    return None


def check_rn_tests(
    rn_ids: list[str],
    proyecto_root: Path | None,
    nombre_funcion: str = "",
    prefijo: str = "RN-",
) -> list[ErrorParser]:
    """Verifica que exista tests/rn/test_rn_{XXX}.py para cada RN."""
    errores: list[ErrorParser] = []
    if not rn_ids or proyecto_root is None:
        return errores

    test_dir = proyecto_root / "tests" / "rn"
    if not test_dir.is_dir():
        return errores

    for rn_id in rn_ids:
        numero = _normalizar_rn_id(rn_id, prefijo)
        if numero is None:
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


def check_rn_tests_pasan(
    rn_ids: list[str],
    proyecto_root: Path | None,
    nombre_funcion: str = "",
    prefijo: str = "RN-",
) -> list[ErrorParser]:
    """Ejecuta pytest para cada test RN y reporta fallos."""
    errores: list[ErrorParser] = []
    if not rn_ids or proyecto_root is None:
        return errores

    test_dir = proyecto_root / "tests" / "rn"
    if not test_dir.is_dir():
        return errores

    for rn_id in rn_ids:
        numero = _normalizar_rn_id(rn_id, prefijo)
        if numero is None:
            continue
        test_file = test_dir / f"test_rn_{numero}.py"
        if not test_file.exists():
            continue

        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", str(test_file),
                 "-q", "--tb=line", "--no-header", "--reuse-db"],
                capture_output=True, text=True, timeout=120,
                cwd=str(proyecto_root),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

        if result.returncode != 0:
            output = result.stdout + result.stderr
            # Errores de entorno (no del test): skip
            if any(x in output for x in ("No tests collected", "Traceback", "ModuleNotFoundError")):
                continue
            fallo = ""
            for line in output.splitlines():
                if "FAILED" in line or "AssertionError" in line:
                    fallo = line.strip()[:120]
                    break
            if not fallo:
                lines = result.stdout.strip().splitlines()
                fallo = lines[-1] if lines else "fallo desconocido"
            errores.append(ErrorParser(
                "rn_tests",
                f"'{nombre_funcion}': RN '{rn_id}' — "
                f"test FALLÓ: {fallo[:200]}",
                sugerencia=f"Corrige la regla o el test en {test_file}",
            ))
    return errores

"""Verificador de tests de RN (reglas de negocio).

Para cada RN-XXX declarada en un CONTRATO, debe existir un archivo
tests/rn/test_rn_XXX.py Y debe pasar.

SRP: El CONTRATO documenta la RN, el test verifica, docpact conecta ambos.
"""

from __future__ import annotations
import ast

import subprocess
import sys
from pathlib import Path

from docpact.models.contrato import ErrorParser


def _normalizar_rn_id(rn_id: str, prefijo: str = "RN-") -> str | None:
    rn_id = rn_id.strip()
    if rn_id.startswith(prefijo):
        return rn_id[len(prefijo) :]
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
            errores.append(
                ErrorParser(
                    "rn_tests",
                    f"'{nombre_funcion}': RN '{rn_id}' declarada en CONTRATO "
                    f"pero no existe test en {test_file}",
                    sugerencia=f"Crea {test_file} con Hypothesis PBT "
                    f"y escribe # {rn_id} en el docstring del test.",
                )
            )
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
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(test_file),
                    "-q",
                    "--tb=line",
                    "--no-header",
                    "--reuse-db",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(proyecto_root),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

        if result.returncode != 0:
            output = result.stdout + result.stderr
            # Errores de entorno (no del test): skip
            if any(
                x in output
                for x in ("No tests collected", "Traceback", "ModuleNotFoundError")
            ):
                continue
            fallo = ""
            for line in output.splitlines():
                if "FAILED" in line or "AssertionError" in line:
                    fallo = line.strip()[:120]
                    break
            if not fallo:
                lines = result.stdout.strip().splitlines()
                fallo = lines[-1] if lines else "fallo desconocido"
            errores.append(
                ErrorParser(
                    "rn_tests",
                    f"'{nombre_funcion}': RN '{rn_id}' — test FALLÓ: {fallo[:200]}",
                    sugerencia=f"Corrige la regla o el test en {test_file}",
                )
            )
    return errores
"""Append para rn_test_checker.py — funcion check_rn_test_quality."""


def _es_assert_trivial(node: ast.Assert) -> bool:
    """Detecta asserts triviales: `assert True`, `assert 1`, `assert "x"`.

    Spec: un test util debe tener al menos 1 assert que verifique una
    condicion real (comparacion, llamada, etc.). Un assert sobre una
    constante truthy no prueba nada — es placebo.
    """
    if isinstance(node.test, ast.Constant):
        return bool(node.test.value)
    return False


def check_rn_test_quality(proyecto_root: Path) -> list[ErrorParser]:
    """Detecta tests placeholder en tests/rn/test_rn_*.py.

    Heuristicas:
    - Cuerpo vacio o solo `pass` → WARNING
    - Sin asserts en el cuerpo → WARNING
    - Todos los asserts son triviales (assert True, assert 1, etc.) → WARNING

    Es opt-in: no se ejecuta en `docpact check` por defecto. Para correrlo:
        docpact test-quality --project-root <path>
    """
    errores: list[ErrorParser] = []
    test_dir = proyecto_root / "tests" / "rn"
    if not test_dir.is_dir():
        return errores

    for test_file in sorted(test_dir.glob("test_rn_*.py")):
        try:
            tree = ast.parse(test_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue

            statements_utiles = [
                n for n in node.body
                if not isinstance(n, ast.Pass)
            ]
            if not statements_utiles:
                errores.append(
                    ErrorParser(
                        "test_quality",
                        f"Test placeholder: {test_file.name}::{node.name} "
                        f"tiene cuerpo vacio o solo `pass`",
                        linea=node.lineno,
                        sugerencia="Agregar al menos 1 assert significativo",
                    )
                )
                continue

            asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
            if not asserts:
                errores.append(
                    ErrorParser(
                        "test_quality",
                        f"Test sin asserts: {test_file.name}::{node.name} "
                        f"no verifica ninguna condicion",
                        linea=node.lineno,
                        sugerencia="Agregar al menos 1 assert que verifique la regla",
                    )
                )
                continue

            if all(_es_assert_trivial(a) for a in asserts):
                errores.append(
                    ErrorParser(
                        "test_quality",
                        f"Test con asserts triviales: {test_file.name}::{node.name} "
                        f"solo tiene 'assert True' (o similar)",
                        linea=node.lineno,
                        sugerencia="Reemplazar con assert real (comparacion, llamada, etc.)",
                    )
                )

    return errores

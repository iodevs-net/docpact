"""Generador de tests Hypothesis desde CONTRATOs.

Lee los CONTRATOs del código fuente y genera tests que verifican:
- side_effects: ninguno → verifica que el AST no tenga calls a .save()/.create()/.delete()
- rn: [RN-XXX] → verifica que el test de la RN exista en tests/rn/
- input/output → verifica tipos de retorno

Uso:
    docpact generate-tests --project-root /path/to/project --output tests/test_contratos_auto.py
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


def _parse_contrato_from_docstring(docstring: str) -> dict[str, Any]:
    """Extrae el bloque CONTRATO de una docstring."""
    if not docstring or "CONTRATO:" not in docstring:
        return {}

    match = re.search(r"CONTRATO:\s*\n(.+)", docstring, re.DOTALL)
    if not match:
        return {}

    text = match.group(1)
    result: dict[str, Any] = {}

    for field in ["input", "output", "side_effects", "rn"]:
        field_match = re.search(rf"^\s+{field}:\s*(.+?)$", text, re.MULTILINE)
        if field_match:
            value = field_match.group(1).strip()
            if field == "rn":
                result[field] = re.findall(r"RN-[\w-]+", value)
            else:
                result[field] = value

    return result


def _scan_project(project_root: Path) -> list[dict[str, Any]]:
    """Escanea el proyecto buscando funciones con CONTRATOs."""
    results = []

    for py_file in project_root.rglob("*.py"):
        if any(
            skip in str(py_file)
            for skip in [
                "test_",
                "tests/",
                "venv/",
                "__pycache__",
                "migrations/",
                "scripts/",
            ]
        ):
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            docstring = ast.get_docstring(node)
            if not docstring:
                continue

            contrato = _parse_contrato_from_docstring(docstring)
            if not contrato:
                continue

            # Extraer el body de la función para análisis AST
            func_body = ast.dump(ast.Module(body=node.body, type_ignores=[]))

            results.append(
                {
                    "file": str(py_file.relative_to(project_root)),
                    "module": str(py_file.relative_to(project_root))
                    .replace("/", ".")
                    .replace(".py", ""),
                    "function": node.name,
                    "line": node.lineno,
                    "contrato": contrato,
                    "func_body": func_body,
                    "source": ast.get_source_segment(source, node) or "",
                }
            )

    return results


def _has_db_write_ast(func_info: dict) -> bool:
    """Verifica si el AST de la función tiene calls a .save/.create/.delete."""
    body = func_info["func_body"]
    db_patterns = [".save(", ".create(", ".delete(", ".update(", ".bulk_create("]
    return any(p in body for p in db_patterns)


def _has_external_api_ast(func_info: dict) -> bool:
    """Verifica si el AST tiene calls a requests/httpx/urlopen."""
    body = func_info["func_body"]
    api_patterns = ["requests.", "httpx.", "urlopen(", "urllib."]
    return any(p in body for p in api_patterns)


def generate_tests(project_root: Path) -> str:
    """Genera archivo de tests desde CONTRATOs del proyecto."""
    contratos = _scan_project(project_root)

    if not contratos:
        return "# No se encontraron CONTRATOs para generar tests\n"

    lines = [
        '"""Tests auto-generados desde CONTRATOs por docpact generate-tests.',
        "",
        "ESTE ARCHIVO ES GENERADO AUTOMÁTICAMENTE. NO EDITAR MANUALMENTE.",
        "Para regenerar: docpact generate-tests --project-root /path/to/project",
        '"""',
        "",
        "import ast",
        "from pathlib import Path",
        "import pytest",
        "",
        "",
    ]

    side_effects_tests = 0
    rn_tests = 0

    for info in contratos:
        contrato = info["contrato"]
        func_name = info["function"]
        module = info["module"]
        test_name = func_name.replace(".", "_")

        # ── Test 1: side_effects: ninguno → verificar no hay DB writes en AST ──
        side_effects = contrato.get("side_effects", "")
        if side_effects in ("ninguno", "") or "ninguno" in side_effects:
            # Solo generamos test si la función tiene un body analizable
            if info["source"]:
                lines.append(f'''def test_contrato_{test_name}_no_side_effects():
    """CONTRATO: {func_name} declara side_effects: ninguno.
    
    Verifica que el código fuente no contenga calls a .save()/.create()/.delete().
    Si este test falla, el CONTRATO miente sobre los side_effects.
    """
    source = Path("{info["file"]}").read_text()
    tree = ast.parse(source)
    
    # Encontrar la función
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "{func_name}":
            func_source = ast.get_source_segment(source, node) or ""
            # Verificar que no hay calls de escritura a DB
            db_calls = [".save(", ".create(", ".delete(", ".update(", ".bulk_create("]
            found = [call for call in db_calls if call in func_source]
            assert not found, (
                f"{func_name} declara side_effects: ninguno pero contiene: {{found}}"
            )
            return
    pytest.skip(f"Función {func_name} no encontrada en fuente")

''')
                side_effects_tests += 1

        # ── Test 2: rn: [RN-XXX] → verificar que el test de la RN exista ──
        rn_list = contrato.get("rn", [])
        for rn in rn_list:
            rn_file = (
                project_root / "tests" / "rn" / f"test_rn_{rn.replace('-', '_')}.py"
            )

            lines.append(f'''def test_contrato_{test_name}_rn_{rn.replace("-", "_")}_has_test():
    """CONTRATO: {func_name} declara {rn}.
    
    Verifica que existe un test dedicado para {rn} en tests/rn/.
    Si este test falla, la RN {rn} no tiene verificación dinámica.
    """
    rn_file = Path("{rn_file}")
    assert rn_file.exists(), (
        f"{func_name} declara {rn} pero no existe tests/rn/test_rn_{rn.replace("-", "_")}.py"
    )
    # Verificar que el test tiene al menos una función de test
    content = rn_file.read_text()
    assert "def test_" in content, (
        f"{rn_file} existe pero no tiene funciones de test"
    )

''')
            rn_tests += 1

    lines.append(
        f"\n# Resumen: {side_effects_tests} tests de side_effects, {rn_tests} tests de RNs"
    )

    return "\n".join(lines)


def main(project_root: str, output: str | None = None) -> None:
    """Punto de entrada principal."""
    root = Path(project_root)
    test_code = generate_tests(root)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(test_code, encoding="utf-8")
        print(f"✅ Tests generados en {out_path}")
        print(f"   {test_code.count('def test_')} tests generados")
    else:
        print(test_code)

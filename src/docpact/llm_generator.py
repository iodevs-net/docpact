"""Generador de tests Hypothesis usando LLM (OpenRouter).

Lee CONTRATOs del código fuente y genera tests que verifican:
- side_effects: ninguno → verifica no hay DB writes
- rn: [RN-XXX] → genera property test que valida la RN
- input/output → verifica tipos

Usa OpenRouter (Nemotron 3 Ultra free) para generar tests de calidad.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"


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
            tree = __import__("ast").parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in __import__("ast").walk(tree):
            if not isinstance(
                node,
                (__import__("ast").FunctionDef, __import__("ast").AsyncFunctionDef),
            ):
                continue

            docstring = __import__("ast").get_docstring(node)
            if not docstring:
                continue

            contrato = _parse_contrato_from_docstring(docstring)
            if not contrato:
                continue

            # Get function source for context
            source_lines = source.split("\n")
            func_start = node.lineno - 1
            func_end = min(func_start + 30, len(source_lines))
            func_source = "\n".join(source_lines[func_start:func_end])

            results.append(
                {
                    "file": str(py_file.relative_to(project_root)),
                    "module": str(py_file.relative_to(project_root))
                    .replace("/", ".")
                    .replace(".py", ""),
                    "function": node.name,
                    "line": node.lineno,
                    "contrato": contrato,
                    "source_preview": func_source,
                }
            )

    return results


def _build_prompt(contratos: list[dict]) -> str:
    """Build the prompt for the LLM."""
    contratos_text = "\n\n".join(
        [
            f"## {c['module']}::{c['function']} (line {c['line']})\n"
            f"File: {c['file']}\n"
            f"CONTRATO:\n{json.dumps(c['contrato'], indent=2, ensure_ascii=False)}\n"
            f"Source preview:\n```python\n{c['source_preview']}\n```"
            for c in contratos
        ]
    )

    return f"""You are a Python test generator. Generate Hypothesis-based tests for these Django functions with CONTRATOs (business rule contracts).

{contratos_text}

Generate a single Python test file with these rules:
1. For side_effects: ninguno → test that function source doesn't contain .save()/.create()/.delete()
2. For rn: [RN-XXX] → test that a test file tests/rn/test_rn_XXX.py exists
3. Import only stdlib (ast, pathlib, pytest) — no Django imports in generated tests
4. Each test function name: test_contrato_{{function_name}}_{{check_type}}
5. Tests must be self-contained and runnable with: pytest tests/test_contratos_auto.py

Output ONLY the Python code, no explanations. Start with the file docstring."""


def call_openrouter(prompt: str, api_key: str, model: str = DEFAULT_MODEL) -> str:
    """Call OpenRouter API."""
    if httpx is None:
        raise ImportError("httpx required: pip install httpx")

    response = httpx.post(
        OPENROUTER_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8000,
            "temperature": 0.1,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def generate_tests_llm(
    project_root: Path, api_key: str | None = None, model: str = DEFAULT_MODEL
) -> str:
    """Generate tests using LLM."""
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError(
            "OPENROUTER_API_KEY required. Set env var or pass api_key parameter."
        )

    contratos = _scan_project(project_root)
    if not contratos:
        return "# No se encontraron CONTRATOs\n"

    # Batch contratos to fit in one prompt (max ~50 per batch)
    all_tests = []
    batch_size = 40

    for i in range(0, len(contratos), batch_size):
        batch = contratos[i : i + batch_size]
        prompt = _build_prompt(batch)
        tests = call_openrouter(prompt, api_key=key, model=model)
        all_tests.append(tests)

    return "\n\n".join(all_tests)


def main(
    project_root: str, output: str | None = None, api_key: str | None = None
) -> None:
    """Entry point."""
    root = Path(project_root)
    test_code = generate_tests_llm(root, api_key=api_key)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(test_code, encoding="utf-8")
        print(f"✅ Tests generados en {out_path}")
        print(f"   {test_code.count('def test_')} tests generados")
    else:
        print(test_code)

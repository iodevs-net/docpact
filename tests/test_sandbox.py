"""Tests del sandbox de ejecución (runner.run_sandbox)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from docpact.runner import run_sandbox


def test_code_passes(tmp_path: Path) -> None:
    """Código correcto debe pasar con exit code 0."""
    code = tmp_path / "code.py"
    code.write_text("def add(a, b): return a + b")

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_code.py").write_text(
        "from code import add\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "PASSED\n", "")

    result = run_sandbox(code, tests, _run=fake_run)
    assert result.returncode == 0
    assert "PASSED" in result.stdout


def test_hardcoding_fails(tmp_path: Path) -> None:
    """Código que hardcodea respuestas debe fallar (usa Hypothesis)."""
    code = tmp_path / "code.py"
    code.write_text("def reverse(s): return 'olleh'")  # hardcoded!

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_hardcode.py").write_text(
        "from hypothesis import given, strategies as st\n"
        "from code import reverse\n"
        "@given(st.text())\n"
        "def test_reverse(s):\n"
        "    assert reverse(s) == s[::-1]\n"
    )

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 1,
            "FAILED\n",
            "/workspace/tests/test_hardcode.py Falsifying example: "
            "test_reverse(s='hello')\n",
        )

    result = run_sandbox(code, tests, _run=fake_run)
    assert result.returncode != 0


def test_tamper_detected(tmp_path: Path) -> None:
    """Modificación de tests durante ejecución debe detectarse."""
    code = tmp_path / "code.py"
    code.write_text("def add(a, b): return a + b")

    tests = tmp_path / "tests"
    tests.mkdir()
    test_file = tests / "test_code.py"
    test_file.write_text(
        "from code import add\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )

    def fake_run(cmd, **kwargs):
        test_file.write_text(
            "def test_add():\n"
            "    assert True  # bypass\n"
        )
        return subprocess.CompletedProcess(cmd, 0, "PASSED\n", "")

    result = run_sandbox(code, tests, _run=fake_run)
    assert getattr(result, "tamper_detected", False)


def test_stderr_filtro_sandbox_paths(tmp_path: Path) -> None:
    """Lineas de stderr con /workspace/tests deben filtrarse."""
    code = tmp_path / "code.py"
    code.write_text("def add(a, b): return a + b")

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_code.py").write_text(
        "from code import add\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0,
            "PASSED\n",
            "INFO  /workspace/tests/test_code.py:3 - setup\n"
            "ERROR internal error on line 42\n"
            "/workspace/tests/test_code.py:5 UserWarning\n",
        )

    result = run_sandbox(code, tests, _run=fake_run)
    assert "/workspace/tests" not in result.stderr
    assert "internal error on line 42" in result.stderr

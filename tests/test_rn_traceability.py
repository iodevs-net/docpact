"""Tests de la matriz de trazabilidad RN.

Verifica build_traceability y print_traceability usando un directorio
temporal con archivos stub que simulan CONTRATOs, tests, y docpact.toml.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from docpact.checker.rn_traceability import (
    CoverageStatus,
    _determine_status,
    _extract_test_functions,
    _is_test_trivial,
    _load_toml_registered_rns,
    _scan_contrato_rn_references,
    _scan_test_files,
    build_traceability,
    print_traceability,
)


# ─── Helpers ────────────────────────────────────────────────────────────────


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a minimal project skeleton with .py files and tests/rn/."""
    # Source files
    (tmp_path / "src").mkdir()
    return tmp_path


def _write_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


# ─── _load_toml_registered_rns ─────────────────────────────────────────────


class TestLoadTomlRegisteredRns:
    def test_no_toml(self, project: Path) -> None:
        """No docpact.toml → empty dict."""
        assert _load_toml_registered_rns(project) == {}

    def test_empty_toml(self, project: Path) -> None:
        """docpact.toml without rn_patrones → empty dict."""
        _write_file(project / "docpact.toml", '[docpact]\nversion = "1"\n')
        assert _load_toml_registered_rns(project) == {}

    def test_parses_rn_patrones(self, project: Path) -> None:
        """docpact.toml with rn_patrones → maps RN-IDs to config."""
        _write_file(
            project / "docpact.toml",
            """\
            [docpact.rn_patrones.RN-001]
            patron = "validar_ticket"
            type = "business"
            """,
        )
        result = _load_toml_registered_rns(project)
        assert "RN-001" in result
        assert result["RN-001"]["patron"] == "validar_ticket"


# ─── _scan_contrato_rn_references ───────────────────────────────────────────


class TestScanContratoRnReferences:
    def test_finds_rn_in_docstring(self, project: Path) -> None:
        """Detects rn: [RN-001] in a CONTRATO docstring."""
        _write_file(
            project / "src" / "app.py",
            """\
            def validar_ticket(ticket):
                \"\"\"
                CONTRATO:
                rn: [RN-001]
                descripcion: valida un ticket
                \"\"\"
                pass
            """,
        )
        result = _scan_contrato_rn_references(project)
        assert "RN-001" in result
        assert result["RN-001"][0]["function"] == "validar_ticket"
        assert result["RN-001"][0]["file"] == "src/app.py"

    def test_multiple_rns_in_one_function(self, project: Path) -> None:
        """Detects multiple RNs in a single docstring."""
        _write_file(
            project / "src" / "app.py",
            """\
            def procesar(ticket):
                \"\"\"
                CONTRATO:
                rn: [RN-001, RN-002]
                \"\"\"
                pass
            """,
        )
        result = _scan_contrato_rn_references(project)
        assert "RN-001" in result
        assert "RN-002" in result

    def test_no_rn_no_match(self, project: Path) -> None:
        """Docstring without rn: → no match."""
        _write_file(
            project / "src" / "app.py",
            """\
            def normal():
                \"\"\"
                Just a regular docstring.
                \"\"\"
                pass
            """,
        )
        result = _scan_contrato_rn_references(project)
        assert result == {}

    def test_skips_excluded_dirs(self, project: Path) -> None:
        """Files in __pycache__ or .venv are skipped."""
        _write_file(
            project / "__pycache__" / "cached.py",
            'def foo():\n    """CONTRATO:\n    rn: [RN-999]\n    """\n    pass',
        )
        result = _scan_contrato_rn_references(project)
        assert "RN-999" not in result

    def test_syntax_error_skipped(self, project: Path) -> None:
        """Files with syntax errors are silently skipped."""
        _write_file(project / "src" / "bad.py", "def (\n")
        result = _scan_contrato_rn_references(project)
        assert result == {}


# ─── _scan_test_files ────────────────────────────────────────────────────────


class TestScanTestFiles:
    def test_finds_test_by_filename(self, project: Path) -> None:
        """test_rn_001.py maps to RN-001."""
        _write_file(
            project / "tests" / "rn" / "test_rn_001.py",
            """\
            def test_validar():
                assert True
            """,
        )
        result = _scan_test_files(project)
        assert "RN-001" in result
        assert len(result["RN-001"]) == 1
        assert "test_validar" in result["RN-001"][0]["functions"]

    def test_no_rn_dir(self, project: Path) -> None:
        """No tests/rn/ → empty dict."""
        result = _scan_test_files(project)
        assert result == {}

    def test_cross_references_other_rn(self, project: Path) -> None:
        """test_rn_001.py referencing RN-002 also adds to RN-002."""
        _write_file(
            project / "tests" / "rn" / "test_rn_001.py",
            """\
            def test_cross():
                # Uses RN-002 indirectly
                pass
            """,
        )
        result = _scan_test_files(project)
        assert "RN-002" in result

    def test_multiple_functions_extracted(self, project: Path) -> None:
        """All test_ functions are extracted."""
        _write_file(
            project / "tests" / "rn" / "test_rn_005.py",
            """\
            def test_one():
                pass

            def test_two():
                pass
            """,
        )
        result = _scan_test_files(project)
        assert "RN-005" in result
        fns = result["RN-005"][0]["functions"]
        assert "test_one" in fns
        assert "test_two" in fns


# ─── _extract_test_functions ─────────────────────────────────────────────────


class TestExtractTestFunctions:
    def test_extracts_test_names(self) -> None:
        src = "def test_foo(): pass\ndef test_bar(): pass\ndef helper(): pass"
        fns = _extract_test_functions(src)
        assert "test_foo" in fns
        assert "test_bar" in fns
        assert "helper" not in fns

    def test_syntax_error_returns_empty(self) -> None:
        assert _extract_test_functions("def (") == []


# ─── _is_test_trivial ────────────────────────────────────────────────────────


class TestIsTestTrivial:
    def test_empty_body(self) -> None:
        """Function with only a docstring (empty after docstring skip) → trivial."""
        src = 'def test_foo():\n    """docstring."""'
        assert _is_test_trivial(src, "test_foo") is True

    def test_assert_true(self) -> None:
        assert _is_test_trivial("def test_foo():\n    assert True", "test_foo") is True

    def test_assert_one(self) -> None:
        assert _is_test_trivial("def test_foo():\n    assert 1", "test_foo") is True

    def test_real_assertion(self) -> None:
        src = "def test_foo():\n    assert 1 + 1 == 2"
        assert _is_test_trivial(src, "test_foo") is False

    def test_pass_is_trivial(self) -> None:
        """'pass' is a no-op — trivial test."""
        assert _is_test_trivial("def test_foo(): pass", "test_foo") is True

    def test_docstring_then_pass_is_trivial(self) -> None:
        """Docstring + pass → trivial."""
        src = 'def test_foo():\n    """docstring."""\n    pass'
        assert _is_test_trivial(src, "test_foo") is True

    def test_nonexistent_function(self) -> None:
        """If the function doesn't exist in source, returns True (trivial)."""
        assert _is_test_trivial("def test_bar(): pass", "test_foo") is True


# ─── _determine_status ───────────────────────────────────────────────────────


class TestDetermineStatus:
    def test_full(self) -> None:
        """Has declarations + non-trivial tests → FULL."""
        status = _determine_status(
            "RN-001",
            [{"file": "src/app.py", "line": 1, "function": "foo"}],
            [{"file": "tests/rn/test_rn_001.py", "functions": ["test_foo"]}],
            toml_registered=True,
        )
        # Cannot determine triviality with relative paths, so it will be FULL
        # when paths aren't absolute (the code sets all_trivial=False for relative)
        assert status == CoverageStatus.FULL

    def test_declared_only(self) -> None:
        """Has declarations but no tests → DECLARED_ONLY."""
        status = _determine_status(
            "RN-002",
            [{"file": "src/app.py", "line": 1, "function": "bar"}],
            [],
            toml_registered=False,
        )
        assert status == CoverageStatus.DECLARED_ONLY

    def test_test_only(self) -> None:
        """Has tests but no declarations → TEST_ONLY."""
        status = _determine_status(
            "RN-003",
            [],
            [{"file": "tests/rn/test_rn_003.py", "functions": ["test_baz"]}],
            toml_registered=False,
        )
        assert status == CoverageStatus.TEST_ONLY

    def test_orphan_from_toml(self) -> None:
        """Registered in toml but no declarations or tests → ORPHAN."""
        status = _determine_status("RN-004", [], [], toml_registered=True)
        assert status == CoverageStatus.ORPHAN

    def test_orphan_nothing(self) -> None:
        """Not in any source → ORPHAN."""
        status = _determine_status("RN-005", [], [], toml_registered=False)
        assert status == CoverageStatus.ORPHAN


# ─── build_traceability (integration) ────────────────────────────────────────


class TestBuildTraceability:
    def test_empty_project(self, project: Path) -> None:
        """Empty project → empty matrix."""
        matrix = build_traceability(project)
        assert matrix == {}

    def test_full_coverage(self, project: Path) -> None:
        """RN declared in code + test file → FULL."""
        _write_file(
            project / "docpact.toml",
            """\
            [docpact.rn_patrones.RN-001]
            patron = "test"
            """,
        )
        _write_file(
            project / "src" / "app.py",
            """\
            def validar():
                \"\"\"
                CONTRATO:
                rn: [RN-001]
                \"\"\"
                pass
            """,
        )
        _write_file(
            project / "tests" / "rn" / "test_rn_001.py",
            "def test_validar():\n    assert 1 + 1 == 2\n",
        )
        matrix = build_traceability(project)
        assert "RN-001" in matrix
        assert matrix["RN-001"]["status"] == "FULL"
        assert matrix["RN-001"]["toml_registered"] is True

    def test_declared_only(self, project: Path) -> None:
        """RN in code but no test file → DECLARED_ONLY."""
        _write_file(
            project / "src" / "app.py",
            """\
            def foo():
                \"\"\"
                CONTRATO:
                rn: [RN-010]
                \"\"\"
                pass
            """,
        )
        matrix = build_traceability(project)
        assert "RN-010" in matrix
        assert matrix["RN-010"]["status"] == "DECLARED_ONLY"

    def test_test_only(self, project: Path) -> None:
        """Test file exists but no CONTRATO declaration → TEST_ONLY."""
        _write_file(
            project / "tests" / "rn" / "test_rn_020.py",
            "def test_something():\n    pass\n",
        )
        matrix = build_traceability(project)
        assert "RN-020" in matrix
        assert matrix["RN-020"]["status"] == "TEST_ONLY"

    def test_orphan(self, project: Path) -> None:
        """RN in toml only → ORPHAN."""
        _write_file(
            project / "docpact.toml",
            """\
            [docpact.rn_patrones.RN-030]
            patron = "orphan_test"
            """,
        )
        matrix = build_traceability(project)
        assert "RN-030" in matrix
        assert matrix["RN-030"]["status"] == "ORPHAN"


# ─── print_traceability ──────────────────────────────────────────────────────


class TestPrintTraceability:
    def test_empty(self, capsys: pytest.CaptureFixture) -> None:
        """Empty matrix → helpful message."""
        print_traceability({})
        captured = capsys.readouterr()
        assert "No RNs found" in captured.out

    def test_prints_summary(self, capsys: pytest.CaptureFixture) -> None:
        """Matrix prints with header and summary."""
        matrix = {
            "RN-001": {
                "status": "FULL",
                "declarations": [{"file": "src/app.py", "function": "foo"}],
                "test_files": [{"file": "tests/rn/test_rn_001.py"}],
                "toml_registered": True,
            },
            "RN-002": {
                "status": "DECLARED_ONLY",
                "declarations": [{"file": "src/app.py", "function": "bar"}],
                "test_files": [],
                "toml_registered": False,
            },
        }
        print_traceability(matrix)
        captured = capsys.readouterr()
        assert "RN TRACEABILITY MATRIX" in captured.out
        assert "RN-001" in captured.out
        assert "RN-002" in captured.out
        assert "FULL: 1" in captured.out
        assert "DECLARED_ONLY: 1" in captured.out
        assert "Coverage: 50%" in captured.out

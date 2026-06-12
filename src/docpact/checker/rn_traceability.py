"""RN Traceability Matrix — cross-references declarations, implementations, and tests.

For each RN in the project, shows:
- Where declared (CONTRATO in code)
- Where tested (tests/rn/ files)
- Coverage status: FULL | PARTIAL | DECLARED_ONLY | TEST_ONLY | ORPHAN

CONTRATO:
input:
  project_root: Path — Raíz del proyecto docpact.
output: dict[str, dict] — Matriz de trazabilidad por RN.
side_effects: ninguno
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CoverageStatus(Enum):
    """Estado de cobertura de una RN."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    DECLARED_ONLY = "DECLARED_ONLY"
    TEST_ONLY = "TEST_ONLY"
    ORPHAN = "ORPHAN"


@dataclass
class RNTraceEntry:
    """Entrada de trazabilidad para una RN."""

    rn_id: str
    status: CoverageStatus
    declarations: list[dict] = field(default_factory=list)
    test_files: list[dict] = field(default_factory=list)
    toml_registered: bool = False


def _load_toml_registered_rns(project_root: Path) -> dict[str, dict]:
    """Parse docpact.toml for [docpact.rn_patrones] to find registered RNs.

    Returns dict mapping RN-ID to its config spec (e.g. patron, type, archivos).
    """
    toml_path = project_root / "docpact.toml"
    if not toml_path.exists():
        return {}

    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return {}

    docpact_cfg = data.get("docpact", {})
    rn_patrones = docpact_cfg.get("rn_patrones", {})

    result: dict[str, dict] = {}
    for rn_id, cfg in rn_patrones.items():
        if isinstance(cfg, dict):
            result[rn_id] = cfg
        else:
            result[rn_id] = {}
    return result


def _scan_contrato_rn_references(project_root: Path) -> dict[str, list[dict]]:
    """Scan all .py files for `rn: [RN-XXX]` in docstrings to find CONTRATO declarations.

    Returns dict mapping RN-ID to list of {file, line, function}.
    """
    result: dict[str, list[dict]] = {}
    exclude_dirs = {
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".git",
        "migrations",
        ".pytest_cache",
    }

    for py_file in project_root.rglob("*.py"):
        # Skip excluded directories
        parts = py_file.relative_to(project_root).parts
        if any(p in exclude_dirs for p in parts):
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Quick pre-filter: skip files with no rn: references at all
        if "rn:" not in source:
            continue

        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            docstring = ast.get_docstring(node)
            if not docstring:
                continue
            if "rn:" not in docstring:
                continue

            # Extract RN IDs from the docstring's rn: line
            for line in docstring.split("\n"):
                stripped = line.strip()
                if not stripped.startswith("rn:"):
                    continue
                # Match rn: [RN-001, RN-002] or rn: RN-001
                ids = re.findall(r"RN-[\w-]+", stripped)
                for rn_id in ids:
                    entry = {
                        "file": str(py_file.relative_to(project_root)),
                        "line": node.lineno,
                        "function": node.name,
                    }
                    result.setdefault(rn_id, []).append(entry)

    return result


def _scan_test_files(project_root: Path) -> dict[str, list[dict]]:
    """Scan tests/rn/ directory for test files referencing each RN.

    Returns dict mapping RN-ID to list of {file, functions}.
    Tests are in files named test_rn_XXX.py and/or contain RN-XXX references.
    """
    result: dict[str, list[dict]] = {}
    rn_dir = project_root / "tests" / "rn"
    if not rn_dir.is_dir():
        return result

    # Pattern 1: match filename test_rn_XXX.py
    rn_file_pattern = re.compile(r"test_rn_(.+)\.py$")

    for test_file in sorted(rn_dir.glob("test_rn_*.py")):
        match = rn_file_pattern.match(test_file.name)
        if not match:
            continue

        rn_number = match.group(1)
        rn_id = f"RN-{rn_number}"

        try:
            source = test_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Extract test function names
        test_functions = _extract_test_functions(source)

        entry = {
            "file": f"tests/rn/{test_file.name}",
            "functions": test_functions,
        }
        result.setdefault(rn_id, []).append(entry)

        # Also check for inline RN references in the test file content
        for ref_rn in re.findall(r"RN-[\w-]+", source):
            if ref_rn != rn_id:
                ref_entry = {
                    "file": f"tests/rn/{test_file.name}",
                    "functions": test_functions,
                }
                result.setdefault(ref_rn, []).append(ref_entry)

    return result


def _extract_test_functions(source: str) -> list[str]:
    """Extract test function names from source code."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                functions.append(node.name)
    return functions


def _is_test_trivial(source: str, function_name: str) -> bool:
    """Check if a test function is trivial (assert True, empty, etc.)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return True

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue

        # Check if the function body is trivial
        body = node.body
        # Skip docstring
        start = 0
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
        ):
            start = 1

        remaining = body[start:]
        if not remaining:
            return True

        if len(remaining) == 1:
            stmt = remaining[0]
            if isinstance(stmt, ast.Pass):
                return True
            if isinstance(stmt, ast.Assert):
                val = stmt.test
                if isinstance(val, ast.Constant):
                    return val.value is True or val.value == 1
                if isinstance(val, ast.Name) and val.id in ("True", "1"):
                    return True

        return False

    return True


def _determine_status(
    rn_id: str,
    declarations: list[dict],
    test_files: list[dict],
    toml_registered: bool,
) -> CoverageStatus:
    """Determine the coverage status of an RN."""
    has_declaration = bool(declarations)
    has_tests = bool(test_files)

    if has_declaration and has_tests:
        # Check if tests are trivial
        all_trivial = True
        for tf in test_files:
            try:
                full_path = Path(tf["file"])
                if not full_path.is_absolute():
                    # Relative to project root — caller should handle this
                    # For now, assume non-trivial if we can't check
                    all_trivial = False
                    break
                source = full_path.read_text(encoding="utf-8")
                for fn in tf.get("functions", []):
                    if not _is_test_trivial(source, fn):
                        all_trivial = False
                        break
                if not all_trivial:
                    break
            except (OSError, UnicodeDecodeError):
                all_trivial = False
                break

        return CoverageStatus.FULL if not all_trivial else CoverageStatus.PARTIAL

    if has_declaration and not has_tests:
        return CoverageStatus.DECLARED_ONLY

    if not has_declaration and has_tests:
        return CoverageStatus.TEST_ONLY

    # Not in declarations, not in tests
    if toml_registered:
        return CoverageStatus.ORPHAN

    # This shouldn't happen for RNs that reach us, but be defensive
    return CoverageStatus.ORPHAN


def build_traceability(project_root: Path) -> dict[str, dict]:
    """Build traceability matrix for all RNs found in the project.

    Collects RNs from three sources:
    1. docpact.toml [docpact.rn_patrones] — registered RNs
    2. Python source files — rn: [RN-XXX] in CONTRATO docstrings
    3. tests/rn/ directory — test_rn_XXX.py files

    Cross-references to determine coverage status per RN.

    Returns dict mapping RN-ID to traceability info dict with keys:
        status, declarations, test_files, toml_registered
    """
    # 1. Registered RNs from docpact.toml
    toml_rns = _load_toml_registered_rns(project_root)

    # 2. CONTRATO declarations in code
    code_declarations = _scan_contrato_rn_references(project_root)

    # 3. Test files in tests/rn/
    test_refs = _scan_test_files(project_root)

    # Collect all known RN IDs
    all_rn_ids: set[str] = set()
    all_rn_ids.update(toml_rns.keys())
    all_rn_ids.update(code_declarations.keys())
    all_rn_ids.update(test_refs.keys())

    # Build matrix
    matrix: dict[str, dict] = {}
    for rn_id in sorted(all_rn_ids):
        declarations = code_declarations.get(rn_id, [])
        test_files = test_refs.get(rn_id, [])
        toml_registered = rn_id in toml_rns

        status = _determine_status(rn_id, declarations, test_files, toml_registered)

        matrix[rn_id] = {
            "status": status.value,
            "declarations": declarations,
            "test_files": test_files,
            "toml_registered": toml_registered,
        }

    return matrix


def print_traceability(matrix: dict[str, dict]) -> None:
    """Print traceability matrix to stdout in a readable table format."""
    if not matrix:
        print("No RNs found in the project.")
        return

    # Summary counts
    counts: dict[str, int] = {}
    for entry in matrix.values():
        status = entry["status"]
        counts[status] = counts.get(status, 0) + 1

    # Header
    print("=" * 72)
    print("  RN TRACEABILITY MATRIX")
    print("=" * 72)
    print()
    print(f"  {'RN':<12} {'Status':<16} {'Declarations':<30} {'Tests'}")
    print(f"  {'─' * 12} {'─' * 16} {'─' * 30} {'─' * 20}")

    for rn_id in sorted(matrix.keys()):
        entry = matrix[rn_id]
        status = entry["status"]

        # Declarations: file:function format
        decls = entry["declarations"]
        if decls:
            decl_strs = [f"{d['file']}:{d['function']}" for d in decls]
            decl_display = decl_strs[0]
            if len(decl_strs) > 1:
                decl_display += f" (+{len(decl_strs) - 1})"
        else:
            decl_display = "—"

        # Tests: file names
        tests = entry["test_files"]
        if tests:
            test_strs = [t["file"] for t in tests]
            test_display = test_strs[0]
            if len(test_strs) > 1:
                test_display += f" (+{len(test_strs) - 1})"
        else:
            test_display = "—"

        # TOML indicator
        toml_mark = " [T]" if entry["toml_registered"] else ""

        print(
            f"  {rn_id:<12} {status:<16} {decl_display:<30} {test_display}{toml_mark}"
        )

    print()
    print("─" * 72)
    print("  Summary:")
    for status in ["FULL", "PARTIAL", "DECLARED_ONLY", "TEST_ONLY", "ORPHAN"]:
        count = counts.get(status, 0)
        if count > 0:
            print(f"    {status}: {count}")
    total = len(matrix)
    full_count = counts.get("FULL", 0)
    coverage_pct = (full_count / total * 100) if total > 0 else 0
    print(f"    Total RNs: {total}  |  Coverage: {coverage_pct:.0f}%")
    print("=" * 72)

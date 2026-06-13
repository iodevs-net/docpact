"""Tests para complexity-based bug prediction en bug_predictor.

Cubre:
- _calcular_cognitive_complexity (SonarSource cognitive complexity con nesting penalty)
- _calcular_method_length (LOC count)
- _check_high_complexity (cognitive complexity > 15)
- _check_long_method (> 30 LOC)
- _check_deep_nesting (nesting depth > 3)
- Integración con predecir_bugs dispatcher
- BugPredicho.metrica y BugPredicho.valor fields
"""
from __future__ import annotations

import ast
import textwrap

from docpact.checker.bug_predictor import (
    BugPredicho,
    _calcular_cognitive_complexity,
    _calcular_method_length,
    _check_deep_nesting,
    _check_high_complexity,
    _check_long_method,
    _max_nesting_depth,
    predecir_bugs,
    predecir_bugs_archivo,
)


def _parse_func(source: str) -> ast.FunctionDef:
    """Parse a function definition from source string."""
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise ValueError("No function found in source")


# ── Cognitive complexity ──


class TestCalcularCognitiveComplexity:
    """Tests for _calcular_cognitive_complexity."""

    def test_simple_function_returns_zero(self):
        """A function with no branches has complexity 0."""
        node = _parse_func("def f():\n    return 1")
        assert _calcular_cognitive_complexity(node) == 0

    def test_single_if_complexity_1(self):
        """Single if: +1 (no nesting)."""
        node = _parse_func("""\
            def f(x):
                if x:
                    return 1
                return 0
        """)
        assert _calcular_cognitive_complexity(node) == 1

    def test_if_elif_else_complexity_2(self):
        """if + elif: each is +1 at nesting 0, total 2."""
        node = _parse_func("""\
            def f(x):
                if x > 0:
                    return 1
                elif x < 0:
                    return -1
                else:
                    return 0
        """)
        # if: +1, elif (nested If in orelse): +1. else: not a branch.
        assert _calcular_cognitive_complexity(node) == 2

    def test_for_loop_complexity_1(self):
        """Single for: +1."""
        node = _parse_func("""\
            def f(items):
                for i in items:
                    print(i)
        """)
        assert _calcular_cognitive_complexity(node) == 1

    def test_while_loop_complexity_1(self):
        """Single while: +1."""
        node = _parse_func("""\
            def f():
                while True:
                    break
        """)
        assert _calcular_cognitive_complexity(node) == 1

    def test_nested_if_in_if_complexity_3(self):
        """if(0) + nested if(+2): 1 + 2 = 3."""
        node = _parse_func("""\
            def f(a, b):
                if a:
                    if b:
                        return True
                return False
        """)
        assert _calcular_cognitive_complexity(node) == 3

    def test_nested_if_in_for_complexity_3(self):
        """for(+1) + if nested inside for(+2): 1 + 2 = 3."""
        node = _parse_func("""\
            def f(items):
                for i in items:
                    if i > 0:
                        print(i)
        """)
        assert _calcular_cognitive_complexity(node) == 3

    def test_deeply_nested_branches(self):
        """if -> for -> while -> if: tracks nesting penalties."""
        node = _parse_func("""\
            def f(data):
                if data:
                    for x in data:
                        while x > 0:
                            if x % 2 == 0:
                                x -= 1
                            x -= 1
        """)
        # if: +1, for: +2(nesting 1), while: +3(nesting 2), if: +4(nesting 3)
        assert _calcular_cognitive_complexity(node) == 10

    def test_many_sequential_ifs(self):
        """Multiple sequential ifs at same nesting: each +1."""
        node = _parse_func("""\
            def f(a, b, c, d, e, f_):
                if a:
                    pass
                if b:
                    pass
                if c:
                    pass
                if d:
                    pass
                if e:
                    pass
                if f_:
                    pass
        """)
        assert _calcular_cognitive_complexity(node) == 6

    def test_complexity_with_try(self):
        """try does not add +1 itself but increases nesting for its body."""
        node = _parse_func("""\
            def f():
                try:
                    if True:
                        pass
                except Exception:
                    pass
        """)
        # try: nesting+1. if: +1 + 1(nesting) = 2
        assert _calcular_cognitive_complexity(node) == 2

    def test_complexity_with_with(self):
        """with does not add +1 itself but increases nesting for its body."""
        node = _parse_func("""\
            def f():
                with open('x') as fh:
                    if True:
                        pass
        """)
        # with: nesting+1. if: +1 + 1(nesting) = 2
        assert _calcular_cognitive_complexity(node) == 2


# ── Method length ──


class TestCalcularMethodLength:
    """Tests for _calcular_method_length."""

    def test_one_line_function(self):
        """def + return on next line = 2 lines."""
        node = _parse_func("def f():\n    return 1")
        assert _calcular_method_length(node) == 2

    def test_multiline_function(self):
        """Count all lines including def."""
        node = _parse_func("""\
            def f(x):
                if x:
                    return 1
                return 0
        """)
        assert _calcular_method_length(node) == 4

    def test_empty_body_function(self):
        """def + pass = 2 lines."""
        node = _parse_func("def f():\n    pass")
        assert _calcular_method_length(node) == 2

    def test_31_line_function(self):
        """A function just over 30 LOC threshold."""
        lines = ["def f():"]
        for i in range(30):
            lines.append(f"    x{i} = {i}")
        source = "\n".join(lines)
        node = _parse_func(source)
        assert _calcular_method_length(node) == 31


# ── Nesting depth ──


class TestMaxNestingDepth:
    """Tests for _max_nesting_depth."""

    def test_no_nesting(self):
        """Flat function: depth 0."""
        node = _parse_func("def f():\n    return 1")
        assert _max_nesting_depth(node) == 0

    def test_single_if(self):
        """Single if: depth 1."""
        node = _parse_func("""\
            def f(x):
                if x:
                    return 1
                return 0
        """)
        assert _max_nesting_depth(node) == 1

    def test_nested_if_depth_2(self):
        """if inside if: depth 2."""
        node = _parse_func("""\
            def f(a, b):
                if a:
                    if b:
                        return True
                return False
        """)
        assert _max_nesting_depth(node) == 2

    def test_for_inside_if_depth_2(self):
        """for inside if: depth 2."""
        node = _parse_func("""\
            def f(items, flag):
                if flag:
                    for x in items:
                        print(x)
        """)
        assert _max_nesting_depth(node) == 2

    def test_depth_4(self):
        """if -> for -> while -> if: depth 4."""
        node = _parse_func("""\
            def f(data):
                if data:
                    for x in data:
                        while x > 0:
                            if x % 2 == 0:
                                x -= 1
                            x -= 1
        """)
        assert _max_nesting_depth(node) == 4


# ── Check: high complexity ──


class TestCheckHighComplexity:
    """Tests for _check_high_complexity."""

    def test_low_complexity_no_bug(self):
        """Complexity <= 15 produces no bug."""
        node = _parse_func("def f():\n    return 1")
        assert _check_high_complexity(node) == []

    def test_complexity_exactly_15_no_bug(self):
        """Complexity exactly at threshold produces no bug."""
        # 15 sequential ifs = complexity 15
        lines = ["def f():"]
        for i in range(15):
            lines.append(f"    if x{i}:")
            lines.append(f"        pass")
        source = "\n".join(lines)
        node = _parse_func(source)
        assert _calcular_cognitive_complexity(node) == 15
        assert _check_high_complexity(node) == []

    def test_complexity_16_flags_bug(self):
        """Complexity > 15 produces a bug."""
        lines = ["def f():"]
        for i in range(16):
            lines.append(f"    if x{i}:")
            lines.append(f"        pass")
        source = "\n".join(lines)
        node = _parse_func(source)
        bugs = _check_high_complexity(node)
        assert len(bugs) == 1
        assert bugs[0].tipo == "high_complexity"
        assert bugs[0].severidad == "warning"
        assert bugs[0].metrica == "cognitive_complexity"
        assert bugs[0].valor == 16.0

    def test_high_complexity_bug_fields(self):
        """Bug carries correct metrica and valor."""
        # Build a function with complexity 20 (20 sequential ifs)
        lines = ["def complexo():"]
        for i in range(20):
            lines.append(f"    if v{i}:")
            lines.append(f"        pass")
        source = "\n".join(lines)
        node = _parse_func(source)
        bugs = _check_high_complexity(node)
        assert len(bugs) == 1
        b = bugs[0]
        assert b.funcion == "complexo"
        assert b.metrica == "cognitive_complexity"
        assert b.valor == 20.0
        assert "20" in b.mensaje


# ── Check: long method ──


class TestCheckLongMethod:
    """Tests for _check_long_method."""

    def test_short_method_no_bug(self):
        """Method <= 30 LOC produces no bug."""
        node = _parse_func("def f():\n    return 1")
        assert _check_long_method(node) == []

    def test_exactly_30_no_bug(self):
        """Method exactly 30 LOC produces no bug."""
        lines = ["def f():"]
        for i in range(29):
            lines.append(f"    x{i} = {i}")
        source = "\n".join(lines)
        node = _parse_func(source)
        assert _calcular_method_length(node) == 30
        assert _check_long_method(node) == []

    def test_31_lines_flags_bug(self):
        """Method > 30 LOC produces a bug."""
        lines = ["def f():"]
        for i in range(30):
            lines.append(f"    x{i} = {i}")
        source = "\n".join(lines)
        node = _parse_func(source)
        bugs = _check_long_method(node)
        assert len(bugs) == 1
        assert bugs[0].tipo == "long_method"
        assert bugs[0].metrica == "loc"
        assert bugs[0].valor == 31.0

    def test_long_method_bug_fields(self):
        """Bug carries correct metrica and valor."""
        lines = ["def longo():"]
        for i in range(50):
            lines.append(f"    x{i} = {i}")
        source = "\n".join(lines)
        node = _parse_func(source)
        bugs = _check_long_method(node)
        assert len(bugs) == 1
        b = bugs[0]
        assert b.funcion == "longo"
        assert b.metrica == "loc"
        assert b.valor == 51.0
        assert "51" in b.mensaje


# ── Check: deep nesting ──


class TestCheckDeepNesting:
    """Tests for _check_deep_nesting."""

    def test_shallow_nesting_no_bug(self):
        """Nesting <= 3 produces no bug."""
        node = _parse_func("""\
            def f(a, b, c):
                if a:
                    for x in b:
                        if c:
                            pass
        """)
        assert _check_deep_nesting(node) == []

    def test_depth_exactly_3_no_bug(self):
        """Nesting exactly 3 produces no bug."""
        node = _parse_func("""\
            def f(a, b, c):
                if a:
                    for x in b:
                        if c:
                            pass
        """)
        assert _max_nesting_depth(node) == 3
        assert _check_deep_nesting(node) == []

    def test_depth_4_flags_bug(self):
        """Nesting > 3 produces a bug."""
        node = _parse_func("""\
            def f(data):
                if data:
                    for x in data:
                        while x > 0:
                            if x % 2 == 0:
                                x -= 1
                            x -= 1
        """)
        bugs = _check_deep_nesting(node)
        assert len(bugs) == 1
        assert bugs[0].tipo == "deep_nesting"
        assert bugs[0].metrica == "nesting_depth"
        assert bugs[0].valor == 4.0

    def test_deep_nesting_bug_fields(self):
        """Bug carries correct metrica and valor."""
        node = _parse_func("""\
            def anidado(a):
                if a:
                    for x in range(10):
                        while x > 0:
                            if x % 2 == 0:
                                for y in range(x):
                                    print(y)
                                x -= 1
                            x -= 1
        """)
        bugs = _check_deep_nesting(node)
        assert len(bugs) == 1
        b = bugs[0]
        assert b.funcion == "anidado"
        assert b.metrica == "nesting_depth"
        assert b.valor == 5.0
        assert "5" in b.mensaje


# ── Integration with predecir_bugs ──


class TestPredecirBugsIntegration:
    """Tests for complexity checks integrated in predecir_bugs dispatcher."""

    def test_high_complexity_appears_in_dispatcher(self):
        """predecir_bugs includes high_complexity check."""
        lines = ["def f():"]
        for i in range(16):
            lines.append(f"    if x{i}:")
            lines.append(f"        pass")
        source = "\n".join(lines)
        node = _parse_func(source)
        bugs = predecir_bugs(node)
        types = {b.tipo for b in bugs}
        assert "high_complexity" in types

    def test_long_method_appears_in_dispatcher(self):
        """predecir_bugs includes long_method check."""
        lines = ["def f():"]
        for i in range(31):
            lines.append(f"    x{i} = {i}")
        source = "\n".join(lines)
        node = _parse_func(source)
        bugs = predecir_bugs(node)
        types = {b.tipo for b in bugs}
        assert "long_method" in types

    def test_deep_nesting_appears_in_dispatcher(self):
        """predecir_bugs includes deep_nesting check."""
        node = _parse_func("""\
            def f(data):
                if data:
                    for x in data:
                        while x > 0:
                            if x % 2 == 0:
                                x -= 1
                            x -= 1
        """)
        bugs = predecir_bugs(node)
        types = {b.tipo for b in bugs}
        assert "deep_nesting" in types

    def test_simple_function_no_complexity_bugs(self):
        """Simple function produces no complexity-related bugs."""
        node = _parse_func("def f():\n    return 1")
        bugs = predecir_bugs(node)
        types = {b.tipo for b in bugs}
        assert "high_complexity" not in types
        assert "long_method" not in types
        assert "deep_nesting" not in types

    def test_existing_checks_still_work(self):
        """Existing checks (mutable_default etc.) still fire."""
        node = _parse_func("def f(x=[]):\n    return x")
        bugs = predecir_bugs(node)
        types = {b.tipo for b in bugs}
        assert "mutable_default" in types


# ── BugPredicho fields ──


class TestBugPredichoFields:
    """Tests for new metrica and valor fields."""

    def test_metrica_valor_defaults_to_none(self):
        """Existing BugPredicho usage has metrica=None, valor=None."""
        b = BugPredicho(
            tipo="test",
            severidad="info",
            mensaje="msg",
            sugerencia="sug",
            archivo="",
            linea=1,
            funcion="f",
        )
        assert b.metrica is None
        assert b.valor is None

    def test_metrica_valor_can_be_set(self):
        """metrica and valor can be explicitly set."""
        b = BugPredicho(
            tipo="test",
            severidad="info",
            mensaje="msg",
            sugerencia="sug",
            archivo="",
            linea=1,
            funcion="f",
            metrica="cognitive_complexity",
            valor=16.0,
        )
        assert b.metrica == "cognitive_complexity"
        assert b.valor == 16.0

    def test_complexity_bugs_have_metrica_valor(self):
        """All three complexity checkers produce bugs with metrica and valor."""
        # High complexity
        lines = ["def f():"]
        for i in range(16):
            lines.append(f"    if x{i}: pass")
        source = "\n".join(lines)
        node = _parse_func(source)
        bugs = _check_high_complexity(node)
        assert len(bugs) == 1
        assert bugs[0].metrica is not None
        assert bugs[0].valor is not None

        # Long method
        lines = ["def g():"]
        for i in range(31):
            lines.append(f"    x{i} = {i}")
        source = "\n".join(lines)
        node = _parse_func(source)
        bugs = _check_long_method(node)
        assert len(bugs) == 1
        assert bugs[0].metrica is not None
        assert bugs[0].valor is not None

        # Deep nesting
        node = _parse_func("""\
            def h(data):
                if data:
                    for x in data:
                        while x > 0:
                            if x % 2 == 0:
                                x -= 1
                            x -= 1
        """)
        bugs = _check_deep_nesting(node)
        assert len(bugs) == 1
        assert bugs[0].metrica is not None
        assert bugs[0].valor is not None


# ── File-level integration ──


class TestPredecirBugsArchivoIntegration:
    """Tests for predecir_bugs_archivo with complexity checks."""

    def test_archivo_detects_complexity_bugs(self, tmp_path):
        """predecir_bugs_archivo detects complexity issues in a file."""
        lines = ["def mega_function():"]
        for i in range(20):
            lines.append(f"    if x{i}:")
            lines.append(f"        y{i} = {i}")
        source = "\n".join(lines)
        archivo = tmp_path / "complex.py"
        archivo.write_text(source)

        bugs = predecir_bugs_archivo(str(archivo))
        types = {b.tipo for b in bugs}
        assert "high_complexity" in types
        # Check file path is populated
        for b in bugs:
            if b.tipo == "high_complexity":
                assert b.archivo == str(archivo)

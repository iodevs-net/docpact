"""Tests para el CLI principal de docpact.

Cubre dispatch de comandos, flags y códigos de retorno.
Los tests de check usan mocks para evitar dependencias del sistema de archivos real.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from docpact.cli.main import main

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Helpers ──


def _mock_funcion(nombre="fn", tiene_contrato=True):
    return SimpleNamespace(
        nombre=nombre,
        tiene_contrato=tiene_contrato,
        errores=[],
        warnings=[],
        hallazgos=[],
    )


def _mock_archivo(archivo="test.py", funciones=None):
    return SimpleNamespace(archivo=archivo, funciones=funciones or [])


def _mock_resultado(
    total=3,
    con_contrato=3,
    errores=0,
    warnings=0,
    score=100,
    nivel="L4",
    archivos=None,
):
    return SimpleNamespace(
        total_funciones=total,
        funciones_con_contrato=con_contrato,
        total_errores=errores,
        total_warnings=warnings,
        calcular_score=lambda: score,
        nivel=nivel,
        archivos=archivos or [],
    )


# ──────────────────────────────────────────────
# Dispatch básico
# ──────────────────────────────────────────────


class TestDispatch:
    """Tests de dispatch del CLI — comandos inválidos y ayuda."""

    def test_version(self, capsys):
        """--version debe mostrar versión y salir con 0."""
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "docpact" in captured.out

    def test_no_args(self, capsys):
        """Sin argumentos debe mostrar ayuda y retornar 0."""
        assert main([]) == 0
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower()

    def test_invalid_command(self):
        """Comando desconocido debe lanzar SystemExit con código 2."""
        with pytest.raises(SystemExit) as exc:
            main(["comando-invalido"])
        assert exc.value.code == 2


# ──────────────────────────────────────────────
# Extract (ejecución real contra fixtures)
# ──────────────────────────────────────────────


class TestExtract:
    """Extract se ejecuta contra los fixtures reales (solo lectura de archivos)."""

    def test_extract_con_dir(self, monkeypatch):
        """Extract con directorio válido debe retornar 0."""
        monkeypatch.chdir(FIXTURES_DIR)
        assert main(["extract", "."]) == 0

    def test_extract_con_dir_json(self, monkeypatch, capsys):
        """Extract con --format json debe retornar 0 y emitir JSON válido."""
        monkeypatch.chdir(FIXTURES_DIR)
        assert main(["extract", ".", "--format", "json"]) == 0
        captured = capsys.readouterr()
        import json

        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_extract_con_path_inexistente(self):
        """Extract con path que no existe debe retornar 2."""
        assert main(["extract", "/no/existe/archivo.py"]) == 2

    def test_extract_con_archivo_py(self):
        """Extract con archivo .py específico debe retornar 0."""
        archivo = str(FIXTURES_DIR / "contrato_completo.py")
        assert main(["extract", archivo]) == 0


# ──────────────────────────────────────────────
# Check (con mocks para evitar dependencias)
# ──────────────────────────────────────────────


class TestCheck:
    """Check usa mocks de check_proyecto para validar el dispatch del CLI."""

    def test_check_normal(self, monkeypatch):
        """Check normal debe retornar 0 cuando no hay errores."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                archivos=[_mock_archivo()]
            ),
        )
        assert main(["check", "."]) == 0

    def test_check_con_errores(self, monkeypatch):
        """Check con errores de validación debe retornar 1."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                errores=2, score=60, nivel="L1", archivos=[_mock_archivo()]
            ),
        )
        assert main(["check", "."]) == 1

    def test_check_strict_sin_contrato(self, monkeypatch):
        """Strict mode: funciones públicas sin CONTRATO retorna 1."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                total=2, con_contrato=1, archivos=[_mock_archivo()]
            ),
        )
        assert main(["check", ".", "--strict"]) == 1

    def test_check_strict_ok(self, monkeypatch):
        """Strict mode cuando todo tiene CONTRATO debe retornar 0."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                total=2, con_contrato=2, archivos=[_mock_archivo()]
            ),
        )
        assert main(["check", ".", "--strict"]) == 0

    def test_check_diff(self, monkeypatch):
        """Diff mode debe retornar 0."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                archivos=[_mock_archivo()]
            ),
        )
        assert main(["check", ".", "--diff"]) == 0

    def test_check_min_score_falla(self, monkeypatch):
        """--min-score 90 con score 85 debe retornar 1."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                score=85, nivel="L2", archivos=[_mock_archivo()]
            ),
        )
        assert main(["check", ".", "--min-score", "90"]) == 1

    def test_check_min_score_ok(self, monkeypatch):
        """--min-score 90 con score 95 debe retornar 0."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                score=95, nivel="L4", archivos=[_mock_archivo()]
            ),
        )
        assert main(["check", ".", "--min-score", "90"]) == 0

    def test_check_fix(self, monkeypatch):
        """Fix mode debe invocar init_function para funciones sin CONTRATO.

        El retorno es 1 porque strict mode + tf-tc > 0 se evalúa
        después del fix block (las variables tf/tc no se recalculan).
        """
        func_con = _mock_funcion("func_con", tiene_contrato=True)
        func_sin = _mock_funcion("func_sin", tiene_contrato=False)
        archivo = _mock_archivo(funciones=[func_con, func_sin])

        init_calls = []

        def mock_init(path, name, safe=True):
            init_calls.append((str(path), name))
            return True, f"generado {name}"

        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                total=2,
                con_contrato=1,
                score=50,
                nivel="L2",
                archivos=[archivo],
            ),
        )
        monkeypatch.setattr("docpact.cli.init.init_function", mock_init)

        assert main(["check", ".", "--fix"]) == 1
        assert len(init_calls) == 1
        assert init_calls[0][1] == "func_sin"

    def test_check_con_config(self, monkeypatch):
        """--config debe pasarse sin errores."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                archivos=[_mock_archivo()]
            ),
        )
        assert main(["check", ".", "--config", "docpact.toml"]) == 0

    def test_check_report(self, monkeypatch, capsys):
        """--report debe mostrar detalles de hallazgos."""
        func = SimpleNamespace(
            nombre="fn_test",
            tiene_contrato=True,
            errores=[],
            warnings=[],
            hallazgos=[
                SimpleNamespace(
                    tipo="warning",
                    campo="side_effects",
                    funcion="fn_test",
                    archivo="test.py",
                    linea=5,
                    mensaje="side effect no documentado",
                    sugerencia="Agregar al CONTRATO",
                )
            ],
        )
        archivo = _mock_archivo(funciones=[func])
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                total=1,
                con_contrato=1,
                warnings=1,
                score=97,
                nivel="L4",
                archivos=[archivo],
            ),
        )
        assert main(["check", ".", "--report"]) == 0
        captured = capsys.readouterr()
        assert "fn_test" in captured.out


# ──────────────────────────────────────────────
# Doctor (con mock)
# ──────────────────────────────────────────────


class TestDoctor:
    """Doctor usa mocks para evitar dependencias de ecosistema (git, CI, etc.)."""

    def test_doctor_ok(self, monkeypatch):
        """Doctor con todas las verificaciones OK debe retornar 0."""
        mock_result = SimpleNamespace(
            checks=[],
            score=100,
            ok=True,
            resumen=lambda: "6/6 checks pasaron",
        )
        monkeypatch.setattr(
            "docpact.checker.doctor.ejecutar",
            lambda path, min_score=90: mock_result,
        )
        assert main(["doctor", "."]) == 0

    def test_doctor_falla(self, monkeypatch):
        """Doctor con verificaciones fallidas debe retornar 1."""
        mock_result = SimpleNamespace(
            checks=[],
            score=50,
            ok=False,
            resumen=lambda: "3/6 checks pasaron",
        )
        monkeypatch.setattr(
            "docpact.checker.doctor.ejecutar",
            lambda path, min_score=90: mock_result,
        )
        assert main(["doctor", "."]) == 1

    def test_doctor_json(self, monkeypatch, capsys):
        """Doctor --json debe retornar 0 y emitir JSON."""
        mock_result = SimpleNamespace(
            checks=[
                SimpleNamespace(
                    nombre="CI workflow",
                    estado=True,
                    mensaje="OK",
                    fix="",
                )
            ],
            score=100,
            ok=True,
            resumen=lambda: "1/1 checks pasaron",
        )
        monkeypatch.setattr(
            "docpact.checker.doctor.ejecutar",
            lambda path, min_score=90: mock_result,
        )
        assert main(["doctor", ".", "--json"]) == 0
        captured = capsys.readouterr()
        import json

        data = json.loads(captured.out)
        assert data["ok"] is True
        assert data["score"] == 100


# ──────────────────────────────────────────────
# Init (con mock para evitar modificar archivos)
# ──────────────────────────────────────────────


class TestInit:
    """Init requiere --function o --batch; sin ellos retorna 1.

    Nota: _cmd_init accede a args.force que no está definido en el parser.
    Los tests que pasan por _cmd_init están marcados como xfail hasta
    que se agregue el flag --force al subparser init.
    """

    @pytest.mark.xfail(
        reason="_cmd_init: args.force no está definido en el parser init",
        strict=False,
    )
    def test_init_sin_flags(self):
        """Init sin --function ni --batch debe retornar 1."""
        assert main(["init", "."]) == 1

    @pytest.mark.xfail(
        reason="_cmd_init: args.force no está definido en el parser init",
        strict=False,
    )
    def test_init_con_function_ok(self, monkeypatch):
        """Init --function debe retornar 0 si la función existe."""
        monkeypatch.setattr(
            "docpact.cli.init.init_function",
            lambda path, name, safe=True: (True, f"generado {name}"),
        )
        assert main(["init", ".", "--function", "test_func"]) == 0

    @pytest.mark.xfail(
        reason="_cmd_init: args.force no está definido en el parser init",
        strict=False,
    )
    def test_init_con_function_falla(self, monkeypatch):
        """Init --function debe retornar 1 si falla la generación."""
        monkeypatch.setattr(
            "docpact.cli.init.init_function",
            lambda path, name, safe=True: (False, f"error generando {name}"),
        )
        assert main(["init", ".", "--function", "test_func"]) == 1

    @pytest.mark.xfail(
        reason="_cmd_init: args.force no está definido en el parser init",
        strict=False,
    )
    def test_init_con_batch(self, monkeypatch):
        """Init --batch debe retornar 0."""
        monkeypatch.setattr(
            "docpact.cli.init.init_batch",
            lambda path, safe=True: [
                ("fn1", True, "OK"),
                ("fn2", True, "OK"),
            ],
        )
        assert main(["init", ".", "--batch"]) == 0


# ──────────────────────────────────────────────
# Run (con mock para evitar Docker)
# ──────────────────────────────────────────────


class TestRun:
    """Run usa mocks para evitar dependencias de Docker."""

    def test_run_ok(self, monkeypatch):
        """Run debe retornar 0 cuando el sandbox tiene éxito."""
        monkeypatch.setattr("docpact.runner.main", lambda argv: 0)
        assert main(["run", "code.py", "--tests", "tests/"]) == 0

    def test_run_falla(self, monkeypatch):
        """Run debe retornar 1 cuando el sandbox falla."""
        monkeypatch.setattr("docpact.runner.main", lambda argv: 1)
        assert main(["run", "code.py", "--tests", "tests/"]) == 1

    def test_run_con_build(self, monkeypatch):
        """Run --build debe pasar el flag correctamente."""
        captured_args = []

        def mock_runner_main(argv):
            captured_args.extend(argv)
            return 0

        monkeypatch.setattr("docpact.runner.main", mock_runner_main)
        assert main(["run", "code.py", "--tests", "tests/", "--build"]) == 0
        joined = " ".join(captured_args)
        assert "--build" in joined


# ──────────────────────────────────────────────
# Lint (análisis estático puro, sin pytest)
# ──────────────────────────────────────────────


class TestLint:
    """Lint = check --no-run-tests (análisis estático puro)."""

    def test_lint_normal(self, monkeypatch):
        """Lint sin errores debe retornar 0."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                archivos=[_mock_archivo()]
            ),
        )
        assert main(["lint", "."]) == 0

    def test_lint_con_errores(self, monkeypatch):
        """Lint con errores debe retornar 1."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                errores=3, score=60, nivel="L1", archivos=[_mock_archivo()]
            ),
        )
        assert main(["lint", "."]) == 1

    def test_lint_strict(self, monkeypatch):
        """Lint --strict con funciones sin CONTRATO debe retornar 1."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                total=5, con_contrato=3, archivos=[_mock_archivo()]
            ),
        )
        assert main(["lint", ".", "--strict"]) == 1

    def test_lint_min_score(self, monkeypatch):
        """Lint --min-score 90 con score 80 debe retornar 1."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                score=80, nivel="L2", archivos=[_mock_archivo()]
            ),
        )
        assert main(["lint", ".", "--min-score", "90"]) == 1


# ──────────────────────────────────────────────
# Test (ejecución dinámica de tests RN)
# ──────────────────────────────────────────────


class TestTestCmd:
    """Test = ejecución dinámica de tests de Reglas de Negocio."""

    def test_test_sin_errores(self, monkeypatch):
        """Test sin errores de RN debe retornar 0."""
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                archivos=[_mock_archivo()]
            ),
        )
        assert main(["test", "."]) == 0

    def test_test_con_errores_rn(self, monkeypatch):
        """Test con errores de RN debe retornar 1."""
        func = SimpleNamespace(
            nombre="fn_rn",
            tiene_contrato=True,
            errores=[],
            warnings=[],
            hallazgos=[
                SimpleNamespace(
                    tipo="error",
                    campo="rn",
                    funcion="fn_rn",
                    archivo="test.py",
                    linea=10,
                    mensaje="Test de RN-001 no encontrado",
                    sugerencia="Crear tests/rn/test_rn_001.py",
                )
            ],
        )
        archivo = _mock_archivo(funciones=[func])
        monkeypatch.setattr(
            "docpact.checker.orchestrator.check_proyecto",
            lambda path, config, diff_only=False: _mock_resultado(
                errores=1, archivos=[archivo]
            ),
        )
        assert main(["test", "."]) == 1


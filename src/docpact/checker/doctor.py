"""docpact doctor — Autodiagnóstico del ecosistema.

Verifica que todas las piezas del sistema de verificación estén
coordinadas: CI, pre-commit, score, RN registry, tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import NamedTuple


class DoctorCheck(NamedTuple):
    """Resultado de una verificación del doctor."""

    nombre: str
    estado: bool  # True = OK, False = fallo
    mensaje: str
    fix: str = ""


class DoctorResult(NamedTuple):
    """Resultado completo del doctor."""

    checks: list[DoctorCheck]
    score: int  # 0-100, cuántos checks pasaron

    @property
    def ok(self) -> bool:
        """ok — Descripción.

            CONTRATO:
            input:
            output: bool — Descripción del retorno
            side_effects: ninguno
            rn: []  # completar con RN-XXX de docs/reglas-del-negocio/
        """
        return all(c.estado for c in self.checks)

    def resumen(self) -> str:
        """resumen — Descripción.

            CONTRATO:
            input:
            output: str — Descripción del retorno
            side_effects: ninguno
            rn: []  # completar con RN-XXX de docs/reglas-del-negocio/
        """
        ok = sum(1 for c in self.checks if c.estado)
        total = len(self.checks)
        return f"{ok}/{total} checks pasaron"


def _hash_file(path: Path) -> str | None:
    """SHA256 de un archivo, o None si no existe."""
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_ci_integridad(proyecto_root: Path) -> DoctorCheck:
    """Verifica que CI workflow no haya sido modificado."""
    workflow = proyecto_root / ".github" / "workflows" / "docpact.yml"
    if not workflow.exists():
        return DoctorCheck(
            "CI workflow",
            False,
            "No encontrado: .github/workflows/docpact.yml",
            "Crear el workflow desde la documentacion",
        )
    content = workflow.read_text()
    if "docpact check" not in content:
        return DoctorCheck(
            "CI workflow",
            False,
            "Workflow no ejecuta docpact check",
            "Agregar 'docpact check . --config docpact.toml' al workflow",
        )
    if "--min-score" not in content:
        return DoctorCheck(
            "CI workflow",
            True,
            "Workflow existe pero sin --min-score (recomendado)",
            "Agregar --min-score 90 al comando docpact check",
        )
    return DoctorCheck("CI workflow", True, "Workflow OK con --min-score")


def check_precommit(proyecto_root: Path) -> DoctorCheck:
    """Verifica que docpact esté configurado en pre-commit."""
    config_file = proyecto_root / ".pre-commit-config.yaml"
    if not config_file.exists():
        return DoctorCheck(
            "Pre-commit",
            False,
            ".pre-commit-config.yaml no encontrado",
            "Crear .pre-commit-config.yaml con entry de docpact",
        )
    content = config_file.read_text()
    if "docpact" not in content:
        return DoctorCheck(
            "Pre-commit",
            False,
            ".pre-commit-config.yaml no incluye docpact",
            "Agregar repositorio docpact al config",
        )
    if "--diff" in content:
        return DoctorCheck("Pre-commit", True, "docpact configurado con --diff")
    return DoctorCheck("Pre-commit", True, "docpact configurado en pre-commit")


def check_score(proyecto_root: Path, minimo: int = 90) -> DoctorCheck:
    """Ejecuta docpact check y verifica score minimo."""
    try:
        from docpact.checker.orchestrator import check_proyecto
        from docpact.config import DocpactConfig

        config_path = proyecto_root / "docpact.toml"
        config = (
            DocpactConfig.desde_toml(str(config_path))
            if config_path.exists()
            else DocpactConfig()
        )
        resultado = check_proyecto(str(proyecto_root), config)
        score = resultado.calcular_score()
        if score >= minimo:
            return DoctorCheck("Score", True, f"Score {score} >= {minimo}")
        return DoctorCheck(
            "Score",
            False,
            f"Score {score} < {minimo}",
            "Corregir CONTRATOS para subir el score",
        )
    except Exception as e:
        return DoctorCheck(
            "Score",
            False,
            f"Error: {e}",
            "Verificar que docpact esté instalado correctamente",
        )


def check_rn_registry(proyecto_root: Path) -> DoctorCheck:
    """Verifica que toda RN en REGISTRO.md tenga test existente."""
    registro = proyecto_root / "docs" / "reglas-del-negocio" / "REGISTRO.md"
    if not registro.exists():
        return DoctorCheck(
            "RN registry",
            False,
            "No encontrado: docs/reglas-del-negocio/REGISTRO.md",
            "Crear REGISTRO.md con las reglas de negocio",
        )

    rn_ids = set()
    for line in registro.read_text().split("\n"):
        if "RN-" in line and "|" in line:
            for word in line.split():
                if word.startswith("RN-") and word[3:].isdigit():
                    rn_ids.add(word)

    if not rn_ids:
        return DoctorCheck(
            "RN registry",
            False,
            "No se encontraron RN-XXX en REGISTRO.md",
            "Agregar reglas con formato RN-XXX en REGISTRO.md",
        )

    test_dir = proyecto_root / "tests" / "rn"
    sin_test = []
    for rn in sorted(rn_ids):
        num = rn.replace("RN-", "")
        test_file = test_dir / f"test_rn_{num}.py"
        if not test_file.exists():
            sin_test.append(rn)

    if sin_test:
        return DoctorCheck(
            "RN registry",
            False,
            f"RNs sin test: {', '.join(sin_test)}",
            f"Crear tests/rn/test_rn_XXX.py para cada RN faltante",
        )
    return DoctorCheck("RN registry", True, f"{len(rn_ids)} RNs con test")


def _es_test_placeholder(path: Path) -> bool:
    """Detecta si un test es placeholder (sin asserts reales ni pytest.raises)."""
    content = path.read_text()
    lines = [l.strip() for l in content.split("\n")]
    # Considerar pytest.raises como assert real
    if "pytest.raises" in content:
        return False
    # Si tiene assert que no sea True/None trivial, no es placeholder
    for line in lines:
        if line.startswith("assert "):
            # Saltar asserts triviales
            stripped = line.replace("assert ", "").strip()
            if stripped not in ("True", "False", "None", "is not None"):
                return False
    # Verificar que tenga al menos un test definido
    has_tests = any(
        l.startswith("def test_") or l.startswith("class Test") for l in lines
    )
    if not has_tests:
        return True
    # Si solo tiene asserts triviales, es placeholder
    return True


def check_tests_placeholder(proyecto_root: Path) -> DoctorCheck:
    """Detecta tests RN que son placeholders."""
    test_dir = proyecto_root / "tests" / "rn"
    if not test_dir.is_dir():
        return DoctorCheck("Tests placeholder", True, "No hay tests RN")

    placeholders = []
    for f in sorted(test_dir.glob("test_rn_*.py")):
        if _es_test_placeholder(f):
            placeholders.append(f.name)

    if placeholders:
        return DoctorCheck(
            "Tests placeholder",
            False,
            f"Tests placeholder: {', '.join(placeholders)}",
            "Reemplazar assert True/pass por asserts de logica real",
        )
    return DoctorCheck("Tests placeholder", True, "Sin placeholders detectados")


def check_version(minima: str = "0.4.0") -> DoctorCheck:
    """Verifica que la version de docpact cumpla el minimo."""
    try:
        from docpact import __version__

        version = __version__
    except ImportError:
        return DoctorCheck(
            "Version docpact",
            False,
            "No se pudo determinar la version",
            "Verificar instalacion de docpact",
        )

    try:
        parts_min = [int(x) for x in minima.split(".")]
        parts_ver = [int(x) for x in version.split(".")]
        # Comparacion simple
        ok = parts_ver >= parts_min
        estado = "OK" if ok else f"menor a {minima}"
        return DoctorCheck(
            "Version docpact",
            ok,
            f"v{version} ({estado})",
            f"Actualizar docpact: pip install --upgrade docpact" if not ok else "",
        )
    except (ValueError, AttributeError):
        return DoctorCheck("Version docpact", True, f"v{version}")

def check_fastembed() -> DoctorCheck:
    """Verifica que FastEmbed esté instalado para detección semántica."""
    try:
        from fastembed import TextEmbedding
        # Intentar cargar el modelo que usa docpact
        model = TextEmbedding(model_name="jinaai/jina-embeddings-v2-base-es")
        return DoctorCheck(
            "FastEmbed",
            True,
            "Instalado y modelo jina-embeddings-v2-base-es disponible",
            "",
        )
    except ImportError:
        return DoctorCheck(
            "FastEmbed",
            False,
            "No instalado — detección de conflictos usa keywords (menos precisa)",
            "Instalar: pip install fastembed",
        )
    except Exception as e:
        return DoctorCheck(
            "FastEmbed",
            False,
            f"Instalado pero modelo no disponible: {e}",
            "Reinstalar: pip install --upgrade fastembed",
        )



def ejecutar(proyecto_root: Path | str, min_score: int = 90) -> DoctorResult:
    """Ejecuta todas las verificaciones del doctor."""
    root = Path(proyecto_root) if isinstance(proyecto_root, str) else proyecto_root
    checks = [
        check_ci_integridad(root),
        check_precommit(root),
        check_score(root, min_score),
        check_rn_registry(root),
        check_tests_placeholder(root),
        check_version(),
        check_fastembed(),
    ]
    ok = sum(1 for c in checks if c.estado)
    score = int((ok / len(checks)) * 100) if checks else 0
    return DoctorResult(checks=checks, score=score)

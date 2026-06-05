"""Tests para marker-honesty en pre-commit (validate command)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def _escribir_index_minimo(proyecto: Path, rns: list[str]) -> None:
    """Helper: escribe un index mínimo con las RNs dadas."""
    rns_dict = {rn: {"tiene_test": False, "test": None} for rn in rns}
    import json
    (proyecto / ".docpact").mkdir(exist_ok=True)
    (proyecto / ".docpact" / "index.json").write_text(
        json.dumps({"funciones": {}, "rns": rns_dict})
    )


def test_validate_detecta_marker_en_delegacion():
    """docpact validate detecta marker en línea de delegación y falla."""
    with tempfile.TemporaryDirectory() as tmpdir:
        proyecto = Path(tmpdir)
        (proyecto / "docpact.toml").write_text("[docpact]\n")
        (proyecto / "soporte").mkdir()
        archivo_py = proyecto / "soporte" / "test.py"
        archivo_py.write_text(
            '''def mi_funcion():
    """CONTRATO:
    rn: [RN-001, RN-002, RN-003, RN-004, RN-005, RN-006]
    """
    return Service.process()  # RN-001, RN-002, RN-003, RN-004, RN-005, RN-006
'''
        )

        _escribir_index_minimo(
            proyecto,
            ["RN-001", "RN-002", "RN-003", "RN-004", "RN-005", "RN-006"],
        )

        result = subprocess.run(
            [sys.executable, "-m", "docpact.cli.main", "validate", str(archivo_py)],
            capture_output=True, text=True, cwd=str(proyecto),
        )

        # Debe fallar (return 1) por marker honesty (warnings bloquean)
        assert result.returncode == 1, (
            f"Esperaba fallo (1), obtuve {result.returncode}. "
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # Debe mencionar marker honesty
        assert "marker" in result.stdout.lower() or "delegación" in result.stdout.lower(), (
            f"Output no menciona marker honesty: {result.stdout}"
        )


def test_validate_NO_falla_sin_marker_decorativo():
    """docpact validate pasa si no hay markers en delegación."""
    with tempfile.TemporaryDirectory() as tmpdir:
        proyecto = Path(tmpdir)
        (proyecto / "docpact.toml").write_text("[docpact]\n")
        (proyecto / "soporte").mkdir()
        archivo_py = proyecto / "soporte" / "test.py"
        archivo_py.write_text(
            '''def mi_funcion():
    """CONTRATO:
    rn: [RN-001]
    """
    if True:  # RN-001
        return "ok"
'''
        )

        _escribir_index_minimo(proyecto, ["RN-001"])

        result = subprocess.run(
            [sys.executable, "-m", "docpact.cli.main", "validate", str(archivo_py)],
            capture_output=True, text=True, cwd=str(proyecto),
        )

        # Debe pasar (return 0)
        assert result.returncode == 0, (
            f"Esperaba éxito (0), obtuve {result.returncode}. "
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


def test_validate_puede_desactivarse_via_config():
    """marker_honesty.enabled = false desactiva el check."""
    with tempfile.TemporaryDirectory() as tmpdir:
        proyecto = Path(tmpdir)
        (proyecto / "docpact.toml").write_text(
            "[docpact.marker_honesty]\nenabled = false\n"
        )
        (proyecto / "soporte").mkdir()
        archivo_py = proyecto / "soporte" / "test.py"
        archivo_py.write_text(
            '''def mi_funcion():
    """CONTRATO:
    rn: [RN-001, RN-002, RN-003, RN-004, RN-005, RN-006]
    """
    return Service.process()  # RN-001, RN-002, RN-003, RN-004, RN-005, RN-006
'''
        )

        _escribir_index_minimo(
            proyecto,
            ["RN-001", "RN-002", "RN-003", "RN-004", "RN-005", "RN-006"],
        )

        result = subprocess.run(
            [sys.executable, "-m", "docpact.cli.main", "validate", str(archivo_py)],
            capture_output=True, text=True, cwd=str(proyecto),
        )

        # Debe pasar (return 0) porque está desactivado
        assert result.returncode == 0, (
            f"Esperaba éxito (0) con check desactivado, obtuve {result.returncode}. "
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

"""Test de integración: orquestador con validadores semánticos (T02 Fase A)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from docpact.checker.orchestrator import check_file
from docpact.config import DocpactConfig


@pytest.fixture
def proyecto_con_docpact_toml(tmp_path: Path) -> Path:
    """Crea proyecto con docpact.toml + módulo de ejemplo."""
    modulo = tmp_path / "ticket_estados.py"
    modulo.write_text(
        '''"""Máquina de estados de tickets."""
TRANSICIONES_PERMITIDAS = {
    "suspendido": ["asignado", "atender", "remoto"],
    "atender": ["asignado", "remoto"],
}
''',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("")
    return tmp_path


def test_orquestador_dispatch_state_transition_pasa(proyecto_con_docpact_toml):
    config = DocpactConfig(
        rn_patrones={
            "RN-005": {
                "type": "state_transition",
                "from_estado": "suspendido",
                "to_estado": "atender",
                "modulo": "ticket_estados.py",
            }
        }
    )
    archivo = proyecto_con_docpact_toml / "ticket_estados.py"
    # forzar la línea con el CONTRATO en un archivo separado
    otro = proyecto_con_docpact_toml / "service.py"
    otro.write_text(
        '''"""Servicios."""
def mi_fn():
    """Función de prueba.

    CONTRATO:
    input: ninguno
    output: str
    side_effects: ninguno
    rn: [RN-005]
    """
    return "ok"
'''
    )
    res = check_file(otro, config)
    # Buscar el hallazgo de la RN
    hallazgos_rn = [
        h
        for f in res.funciones
        for h in f.hallazgos
        if h.campo in ("rn_semantica", "rn")
    ]
    # RN-005 está bien configurada y la transición existe → no debe haber error
    errores = [h for h in hallazgos_rn if h.tipo == "error"]
    assert errores == [], f"Errores inesperados: {errores}"


def test_orquestador_info_para_rn_sin_validador(proyecto_con_docpact_toml):
    config = DocpactConfig(rn_patrones={})  # ningún validador configurado
    archivo = proyecto_con_docpact_toml / "service.py"
    archivo.write_text(
        '''"""Servicios."""
def mi_fn():
    """Función de prueba.

    CONTRATO:
    input: ninguno
    output: str
    side_effects: ninguno
    rn: [RN-DEV-003]
    """
    return "ok"
'''
    )
    res = check_file(archivo, config)
    hallazgos_info = [
        h
        for f in res.funciones
        for h in f.hallazgos
        if h.tipo == "info" and "sin validador" in h.mensaje
    ]
    assert len(hallazgos_info) == 1
    assert "RN-DEV-003" in hallazgos_info[0].mensaje

"""Tests para docpact.reporter."""

from pathlib import Path

import pytest

from docpact.reporter import (
    RNStatus,
    generar_reporte,
    generar_tabla,
    generar_json,
    validar_ci,
    _parsear_registro,
)


class TestParsearRegistro:
    """_parsear_registro — parsea tabla de REGISTRO.md."""

    def test_parsea_rns_basicas(self, tmp_path):
        """Parsea RNs con formato estándar."""
        registro = tmp_path / "REGISTRO.md"
        registro.write_text(
            "| RN-001 | Estados base del ticket | `soporte/models/ticket.py` | ✓ | ✅ |\n"
            "| RN-002 | Descuenta horas | `soporte/services/sesiones.py` | ✓ | ✅ |\n"
            "| RN-SEG-002 | Solo supervisión asigna | — | ✗ | ⏳ |\n"
        )
        rns = _parsear_registro(registro)
        assert len(rns) == 3
        assert rns[0]["id"] == "RN-001"
        assert rns[0]["estado"] == "✅"
        assert rns[2]["id"] == "RN-SEG-002"
        assert rns[2]["estado"] == "⏳"

    def test_archivo_no_existe(self, tmp_path):
        """Retorna lista vacía si el archivo no existe."""
        rns = _parsear_registro(tmp_path / "no_existe.md")
        assert rns == []


class TestValidarCI:
    """validar_ci — validaciones para CI."""

    def test_rn_con_marcador_sin_test_falla(self):
        """RN con marcador pero sin test debe fallar CI."""
        resultados = [
            RNStatus(
                id="RN-001",
                descripcion="Test",
                estado_registro="✅",
                tiene_marcador=True,
                tiene_test=False,
            )
        ]
        pass_ci, errores = validar_ci(resultados)
        assert pass_ci is False
        assert len(errores) == 1
        assert "RN-001" in errores[0]

    def test_rn_con_marcador_y_test_pasa(self):
        """RN con marcador y test debe pasar CI."""
        resultados = [
            RNStatus(
                id="RN-001",
                descripcion="Test",
                estado_registro="✅",
                tiene_marcador=True,
                tiene_test=True,
            )
        ]
        pass_ci, errores = validar_ci(resultados)
        assert pass_ci is True
        assert errores == []

    def test_rn_sin_marcador_ni_test_pasa(self):
        """RN sin marcador ni test es pendiente legítima, no falla CI."""
        resultados = [
            RNStatus(
                id="RN-001",
                descripcion="Test",
                estado_registro="⏳",
                tiene_marcador=False,
                tiene_test=False,
            )
        ]
        pass_ci, errores = validar_ci(resultados)
        assert pass_ci is True
        assert errores == []

    def test_multiple_rns_mezcladas(self):
        """Mix de RNs: algunas fallan, algunas pasan."""
        resultados = [
            RNStatus(
                id="RN-001",
                descripcion="OK",
                estado_registro="✅",
                tiene_marcador=True,
                tiene_test=True,
            ),
            RNStatus(
                id="RN-002",
                descripcion="Sin test",
                estado_registro="✅",
                tiene_marcador=True,
                tiene_test=False,
            ),
            RNStatus(
                id="RN-003",
                descripcion="Pendiente",
                estado_registro="⏳",
                tiene_marcador=False,
                tiene_test=False,
            ),
        ]
        pass_ci, errores = validar_ci(resultados)
        assert pass_ci is False
        assert len(errores) == 1
        assert "RN-002" in errores[0]


class TestGenerarJson:
    """generar_json — output JSON."""

    def test_json_es_valido(self):
        """JSON output es válido."""
        resultados = [
            RNStatus(
                id="RN-001",
                descripcion="Test",
                estado_registro="✅",
                tiene_validador=True,
                tiene_marcador=True,
                tiene_test=True,
                implementacion="✅ IMPLEMENTADA",
            )
        ]
        import json

        output = generar_json(resultados)
        data = json.loads(output)
        assert data["resumen"]["total"] == 1
        assert data["resumen"]["implementadas"] == 1
        assert len(data["rns"]) == 1


class TestGenerarTabla:
    """generar_tabla — output humano."""

    def test_tabla_no_vacia(self):
        """Tabla tiene contenido."""
        resultados = [
            RNStatus(
                id="RN-001",
                descripcion="Test",
                estado_registro="✅",
                tiene_validador=True,
                tiene_marcador=True,
                tiene_test=True,
                implementacion="✅ IMPLEMENTADA",
            )
        ]
        tabla = generar_tabla(resultados)
        assert "RN-001" in tabla
        assert "IMPLEMENTADA" in tabla

    def test_lista_vacia(self):
        """Lista vacía retorna mensaje."""
        assert "No se encontraron" in generar_tabla([])

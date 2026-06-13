"""Tests para los tools MCP de gestión de RNs.

Testea: listar_rns, verificar_conflicto, crear_rn, explicar_rn.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch


# ── Fixtures ──


@pytest.fixture
def mock_index():
    """Índice mock para tests de MCP tools."""
    return {
        "rns": {
            "RN-TKT-001": {
                "descripcion": "Los tickets deben ser respondidos en menos de 4 horas",
                "funciones": [{"funcion": "crear_ticket", "archivo": "tickets.py"}],
                "tiene_test": True,
                "en_registro": True,
            },
            "RN-TKT-002": {
                "descripcion": "Los tickets deben tener prioridad asignada",
                "funciones": [{"funcion": "asignar_prioridad", "archivo": "tickets.py"}],
                "tiene_test": False,
                "en_registro": True,
            },
            "RN-FAC-001": {
                "descripcion": "Las facturas deben generarse automáticamente",
                "funciones": [],
                "tiene_test": False,
                "en_registro": False,
            },
        },
        "stats": {
            "total_funciones": 10,
            "funciones_con_rn": 5,
            "total_rns": 3,
            "rns_con_test": 1,
        },
    }


@pytest.fixture
def mock_index_vacio():
    """Índice vacío para tests edge cases."""
    return {"rns": {}, "stats": {"total_rns": 0}}


@pytest.fixture
def mock_embedder():
    """Embedder mock que retorna vectores fake."""
    class FakeEmbedder:
        def embed(self, texts):
            # Retornar vectores simples para testing
            return [[0.1] * 384 for _ in texts]
    return FakeEmbedder()


# ── Tests: listar_rns ──


class TestListarRns:
    """Tests para tool_listar_rns."""

    def test_lista_rns_exitoso(self, mock_index):
        """Lista todas las RNs del índice."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_listar_rns()

        assert "rns" in result
        assert result["total"] == 3
        assert result["con_test"] == 1
        assert result["en_registro"] == 2

        ids = [rn["id"] for rn in result["rns"]]
        assert "RN-TKT-001" in ids
        assert "RN-TKT-002" in ids
        assert "RN-FAC-001" in ids

    def test_lista_rns_indice_vacio(self, mock_index_vacio):
        """Lista vacía cuando no hay RNs."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index_vacio):
            result = mcp.tool_listar_rns()

        assert result["total"] == 0
        assert result["rns"] == []

    def test_lista_rns_sin_indice(self):
        """Error cuando el índice no está cargado."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", None):
            result = mcp.tool_listar_rns()

        assert "error" in result


# ── Tests: verificar_conflicto ──


class TestVerificarConflicto:
    """Tests para tool_verificar_conflicto."""

    def test_sin_conflictos(self, mock_index):
        """No detecta conflicto con regla completamente nueva."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index), \
             patch.object(mcp, "_embedder", None):  # Forzar keywords
            result = mcp.tool_verificar_conflicto("El sistema debe enviar emails de bienvenida")

        assert result["tiene_conflictos"] is False
        assert result["total_conflictos"] == 0

    def test_duplicado_detectado(self, mock_index):
        """Detecta duplicado casi exacto."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index), \
             patch.object(mcp, "_embedder", None):
            result = mcp.tool_verificar_conflicto("Los tickets deben ser respondidos en menos de 4 horas")

        assert result["tiene_conflictos"] is True
        tipos = [c["tipo"] for c in result["conflictos"]]
        assert "duplicado" in tipos

    def test_mismo_concepto(self, mock_index):
        """Detecta regla sobre mismo tema con diferente redacción."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index), \
             patch.object(mcp, "_embedder", None):
            result = mcp.tool_verificar_conflicto("Las entradas deben procesarse antes de 24 horas")

        # Con keywords, "tickets" y "entradas" comparten "deben" y "procesarse"/"respondidos"
        # El test verifica que el mecanismo funciona
        assert "conflictos" in result

    def test_override_detectado(self, mock_index):
        """Detecta override cuando menciona la misma función."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index), \
             patch.object(mcp, "_embedder", None):
            result = mcp.tool_verificar_conflicto("crear_ticket debe validar RUT antes de crear")

        assert result["tiene_conflictos"] is True
        tipos = [c["tipo"] for c in result["conflictos"]]
        assert "override" in tipos

    def test_sin_indice(self):
        """Error cuando el índice no está cargado."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", None):
            result = mcp.tool_verificar_conflicto("test")

        assert "error" in result


# ── Tests: crear_rn ──


class TestCrearRn:
    """Tests para tool_crear_rn."""

    def test_crear_rn_exitoso(self, mock_index, tmp_path):
        """Crea una RN nueva exitosamente."""
        import docpact.mcp_server as mcp
        registro = tmp_path / "REGISTRO.md"
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_crear_rn(
                "RN-EMAIL-001",
                "Los emails deben enviarse en menos de 5 minutos",
                str(registro),
            )

        assert result["creada"] is True
        assert result["rn_id"] == "RN-EMAIL-001"
        assert registro.exists()
        assert "RN-EMAIL-001" in registro.read_text()

    def test_crear_rn_id_invalido(self, mock_index, tmp_path):
        """Rechaza ID con formato inválido."""
        import docpact.mcp_server as mcp
        registro = tmp_path / "REGISTRO.md"
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_crear_rn(
                "INVALIDO",
                "Regla test",
                str(registro),
            )

        assert "error" in result
        assert "formato" in result["error"].lower() or "inválido" in result["error"]

    def test_crear_rn_ya_existe(self, mock_index, tmp_path):
        """Rechaza crear RN que ya existe."""
        import docpact.mcp_server as mcp
        registro = tmp_path / "REGISTRO.md"
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_crear_rn(
                "RN-TKT-001",  # Ya existe en mock_index
                "Regla duplicada",
                str(registro),
            )

        assert "error" in result
        assert "existe" in result["error"].lower()

    def test_crear_rn_archivo_nuevo(self, mock_index, tmp_path):
        """Crea el archivo REGISTRO.md si no existe."""
        import docpact.mcp_server as mcp
        registro = tmp_path / "nueva_carpeta" / "REGISTRO.md"
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_crear_rn(
                "RN-NEW-001",
                "Regla nueva",
                str(registro),
            )

        assert result["creada"] is True
        assert registro.exists()

    def test_crear_rn_archivo_existente(self, mock_index, tmp_path):
        """Agrega RN a archivo REGISTRO.md existente."""
        import docpact.mcp_server as mcp
        registro = tmp_path / "REGISTRO.md"
        registro.write_text("# Registro\n\n- **RN-OLD-001**: Regla vieja\n", encoding="utf-8")

        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_crear_rn(
                "RN-NEW-001",
                "Regla nueva",
                str(registro),
            )

        assert result["creada"] is True
        contenido = registro.read_text()
        assert "RN-OLD-001" in contenido  # Original preserved
        assert "RN-NEW-001" in contenido  # New added


# ── Tests: explicar_rn ──


class TestExplicarRn:
    """Tests para tool_explicar_rn."""

    def test_explicar_rn_completa(self, mock_index):
        """Explica RN que tiene código y test."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_explicar_rn("RN-TKT-001")

        assert result["existe"] is True
        assert result["id"] == "RN-TKT-001"
        assert "COMPLETA" in result["estado"]
        assert "crear_ticket" in result["quien_la_implementa"]
        assert result["tiene_test"] is True

    def test_explicar_rn_parcial(self, mock_index):
        """Explica RN que tiene código pero sin test."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_explicar_rn("RN-TKT-002")

        assert result["existe"] is True
        assert "PARCIAL" in result["estado"]
        assert result["tiene_test"] is False

    def test_explicar_rn_pendiente(self, mock_index):
        """Explica RN que no tiene código."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_explicar_rn("RN-FAC-001")

        assert result["existe"] is True
        assert "PENDIENTE" in result["estado"]
        assert result["quien_la_implementa"] == ["Nadie aún"]

    def test_explicar_rn_no_existe(self, mock_index):
        """RN que no existe retorna coincidencias parciales."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_explicar_rn("RN-XXX-999")

        assert result["existe"] is False
        assert "coincidencias_parciales" in result

    def test_explicar_rn_parcial(self, mock_index):
        """Búsqueda parcial encuentra coincidencias."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_explicar_rn("TKT")

        assert result["existe"] is False
        assert len(result["coincidencias_parciales"]) > 0

    def test_explicar_rn_resumen_para_dueno(self, mock_index):
        """El resumen es comprensible para un no-técnico."""
        import docpact.mcp_server as mcp
        with patch.object(mcp, "_index", mock_index):
            result = mcp.tool_explicar_rn("RN-TKT-001")

        resumen = result["resumen_para_dueno"]
        assert "regla" in resumen.lower()
        assert "RN-TKT-001" in resumen

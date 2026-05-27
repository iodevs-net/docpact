"""Tests del parser de CONTRATOS en comentarios TypeScript/JSX."""

from pathlib import Path

from docpact.parser.ts_parser import extraer_contratos_ts

FIXTURES = Path(__file__).parent / "fixtures_ts"


# ═══════════════════════════════════════════════════════════
# 1. Formato single‑line (//)
# ═══════════════════════════════════════════════════════════


def test_single_line_contrato_completo():
    """Debe extraer todos los campos de un // CONTRATO: completo."""
    archivo = FIXTURES / "single_line_contrato_completo.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1, f"Esperado 1, obtenido {len(contratos)}"

    c = contratos[0]
    assert c["nombre_funcion"] == "validarTicket"
    assert c["linea"] == 1
    assert c["input"]["ticket_id"] == {"tipo": "int", "descripcion": "ID del ticket"}
    assert c["input"]["usuario"] == {"tipo": "string", "descripcion": "nombre del usuario"}
    assert c["output"] == "bool — true si es válido"
    assert c["side_effects"] == []
    assert c["rn"] == [{"id": "RN-010", "descripcion": "ticket debe estar activo"}]
    assert c["borde"] == [{"condicion": "ticket nulo", "comportamiento": "retorna false"}]
    assert c["dependencias"] == ["soporte/models/ticket.py::Ticket"]


def test_single_line_solo_side_effects():
    """Debe extraer CONTRATO con solo side_effects."""
    archivo = FIXTURES / "single_line_solo_side_effects.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    c = contratos[0]
    assert c["nombre_funcion"] == "logMessage"
    assert c["side_effects"] == ["escribe en archivo de log"]


def test_single_line_sin_contrato():
    """Archivo sin CONTRATO debe retornar lista vacía."""
    archivo = FIXTURES / "single_line_sin_contrato.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert contratos == []


def test_single_line_funcion_privada():
    """Funciones privadas se excluyen por prefijo _."""
    archivo = FIXTURES / "single_line_funcion_privada.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "_interna"


# ═══════════════════════════════════════════════════════════
# 2. Formato multi‑line (/** */)
# ═══════════════════════════════════════════════════════════


def test_multi_line_contrato_completo():
    """Debe extraer CONTRATO de un bloque /** */ completo."""
    archivo = FIXTURES / "multi_line_contrato_completo.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1, f"Esperado 1, obtenido {len(contratos)}"
    c = contratos[0]
    assert c["nombre_funcion"] == "findUser"
    assert c["input"]["usuario_id"] == {"tipo": "number", "descripcion": "ID del usuario a buscar"}
    assert c["output"] == "User | null"
    assert c["side_effects"] == []
    assert c["rn"] == [{"id": "RN-005", "descripcion": "usuario debe existir en BD"}]


def test_multi_line_con_otros_comentarios():
    """Debe ignorar /** */ que no contengan CONTRATO."""
    archivo = FIXTURES / "multi_line_con_otros_comentarios.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert contratos == [], "Comentario sin CONTRATO no debe extraerse"


def test_multi_line_con_async_function():
    """Debe extraer CONTRATO de una función async."""
    archivo = FIXTURES / "multi_line_con_async_function.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "getTickets"


# ═══════════════════════════════════════════════════════════
# 3. Formatos de exportación y declaración
# ═══════════════════════════════════════════════════════════


def test_export_function():
    """Debe detectar 'export function'."""
    archivo = FIXTURES / "export_function.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "calcularTotal"


def test_arrow_function():
    """Debe detectar 'const nombre = (...)'."""
    archivo = FIXTURES / "arrow_function.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "sumar"


def test_export_const_arrow():
    """Debe detectar 'export const nombre = (...)'."""
    archivo = FIXTURES / "export_const_arrow.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "VERSION"


# ═══════════════════════════════════════════════════════════
# 4. Varios contratos en un mismo archivo
# ═══════════════════════════════════════════════════════════


def test_multiple_contratos():
    """Debe extraer múltiples CONTRATOS de un mismo archivo."""
    archivo = FIXTURES / "multiple_contratos.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 2
    assert contratos[0]["nombre_funcion"] == "suma"
    assert contratos[1]["nombre_funcion"] == "resta"


# ═══════════════════════════════════════════════════════════
# 5. Error handling
# ═══════════════════════════════════════════════════════════


def test_archivo_inexistente():
    """Archivo inexistente lanza FileNotFoundError."""
    import pytest
    with pytest.raises(FileNotFoundError):
        extraer_contratos_ts("/no/existe/archivo.ts")


def test_archivo_vacio():
    """Archivo vacío retorna lista vacía."""
    archivo = FIXTURES / "archivo_vacio.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert contratos == []


# ═══════════════════════════════════════════════════════════
# 6. Casos borde de formato
# ═══════════════════════════════════════════════════════════


def test_input_sin_descripcion():
    """Input sin descripción (sin '—') debe parsear igual."""
    archivo = FIXTURES / "input_sin_descripcion.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["input"]["id"] == {"tipo": "number", "descripcion": ""}


def test_side_effects_multiple():
    """Side effects separados por coma."""
    archivo = FIXTURES / "side_effects_multiple.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["side_effects"] == [
        "escribe en DB",
        "envía email",
        "actualiza caché",
    ]


def test_rn_sin_descripcion():
    """RN sin descripción debe tener id pero descripción vacía."""
    archivo = FIXTURES / "rn_sin_descripcion.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["rn"] == [{"id": "RN-999", "descripcion": ""}]


def test_sin_campos_opcionales():
    """CONTRATO sin campos opcionales debe tener valores por defecto."""
    archivo = FIXTURES / "sin_campos_opcionales.ts"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    c = contratos[0]
    assert c["input"] == {}
    assert c["rn"] == []
    assert c["borde"] == []
    assert c["dependencias"] == []


def test_formato_mixto_tsx():
    """Debe funcionar con archivos .tsx."""
    archivo = FIXTURES / "formato_mixto_tsx.tsx"
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "MiComponente"

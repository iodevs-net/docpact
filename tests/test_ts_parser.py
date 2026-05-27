"""Tests del parser de CONTRATOS en comentarios TypeScript/JSX."""

from pathlib import Path

from docpact.parser.ts_parser import extraer_contratos_ts

FIXTURES = Path(__file__).parent / "fixtures_ts"


# ─── helpers ────────────────────────────────────────────────


def _crear_temporal(contenido: str, ext: str = ".ts") -> Path:
    """Crea un archivo temporal con el contenido dado."""
    tmp = FIXTURES / f"_test_{hash(contenido)}{ext}"
    tmp.parent.mkdir(exist_ok=True)
    if not tmp.exists():
        tmp.write_text(contenido, encoding="utf-8")
    return tmp


# ═══════════════════════════════════════════════════════════
# 1. Formato single‑line (//)
# ═══════════════════════════════════════════════════════════


def test_single_line_contrato_completo():
    """Debe extraer todos los campos de un // CONTRATO: completo."""
    src = """\
// CONTRATO:
//   input:
//     ticket_id: int — ID del ticket
//     usuario: string — nombre del usuario
//   output: bool — true si es válido
//   side_effects: ninguno
//   rn:
//     - RN-010: ticket debe estar activo
//   borde:
//     - ticket nulo: retorna false
//   dependencias:
//     - soporte/models/ticket.py::Ticket
function validarTicket(ticket_id: number, usuario: string): boolean {
    return true;
}
"""
    archivo = _crear_temporal(src)
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
    src = """\
// CONTRATO:
//   input:
//     msg: string — mensaje a loguear
//   output: void
//   side_effects: escribe en archivo de log
function logMessage(msg: string): void {
    fs.writeFileSync('/tmp/log', msg);
}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    c = contratos[0]
    assert c["nombre_funcion"] == "logMessage"
    assert c["side_effects"] == ["escribe en archivo de log"]


def test_single_line_sin_contrato():
    """Archivo sin CONTRATO debe retornar lista vacía."""
    src = """\
// Solo un comentario normal
function foo() {
    return 42;
}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert contratos == []


def test_single_line_funcion_privada():
    """Funciones privadas se excluyen por prefijo _."""
    src = """\
// CONTRATO:
//   input: ninguno
//   output: void
function _interna(): void {
    return;
}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "_interna"


# ═══════════════════════════════════════════════════════════
# 2. Formato multi‑line (/** */)
# ═══════════════════════════════════════════════════════════


def test_multi_line_contrato_completo():
    """Debe extraer CONTRATO de un bloque /** */ completo."""
    src = """\
/**
 * CONTRATO:
 *   input:
 *     usuario_id: number — ID del usuario a buscar
 *   output: User | null
 *   side_effects: ninguno
 *   rn:
 *     - RN-005: usuario debe existir en BD
 */
async function findUser(usuario_id: number): Promise<User | null> {
    return db.findUser(usuario_id);
}
"""
    archivo = _crear_temporal(src)
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
    src = """\
/**
 * Comentario de documentación normal.
 * No tiene CONTRATO.
 */
function simpleFunc(): void {}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert contratos == [], "Comentario sin CONTRATO no debe extraerse"


def test_multi_line_con_async_function():
    """Debe extraer CONTRATO de una función async."""
    src = """\
/**
 * CONTRATO:
 *   input:
 *     ids: number[] — lista de IDs
 *   output: Ticket[]
 *   side_effects: ninguno
 */
async function getTickets(ids: number[]): Promise<Ticket[]> {
    return await Ticket.findAll(ids);
}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "getTickets"


# ═══════════════════════════════════════════════════════════
# 3. Formatos de exportación y declaración
# ═══════════════════════════════════════════════════════════


def test_export_function():
    """Debe detectar 'export function'."""
    src = """\
// CONTRATO:
//   output: number
export function calcularTotal(): number {
    return 100;
}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "calcularTotal"


def test_arrow_function():
    """Debe detectar 'const nombre = (...)'."""
    src = """\
// CONTRATO:
//   input:
//     a: number
//   output: number
const sumar = (a: number, b: number): number => {
    return a + b;
}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "sumar"


def test_export_const_arrow():
    """Debe detectar 'export const nombre = (...)'."""
    src = """\
// CONTRATO:
//   input: ninguno
//   output: string
export const VERSION = "1.0.0";
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "VERSION"


# ═══════════════════════════════════════════════════════════
# 4. Varios contratos en un mismo archivo
# ═══════════════════════════════════════════════════════════


def test_multiple_contratos():
    """Debe extraer múltiples CONTRATOS de un mismo archivo."""
    src = """\
// CONTRATO:
//   input:
//     x: number
//   output: number
function suma(x: number, y: number): number {
    return x + y;
}

/**
 * CONTRATO:
 *   input:
 *     x: number
 *   output: number
 */
function resta(x: number, y: number): number {
    return x - y;
}
"""
    archivo = _crear_temporal(src)
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
    src = ""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert contratos == []


# ═══════════════════════════════════════════════════════════
# 6. Casos borde de formato
# ═══════════════════════════════════════════════════════════


def test_input_sin_descripcion():
    """Input sin descripción (sin '—') debe parsear igual."""
    src = """\
// CONTRATO:
//   input:
//     id: number
//   output: User
function getUser(id: number): User {
    return users[id];
}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["input"]["id"] == {"tipo": "number", "descripcion": ""}


def test_side_effects_multiple():
    """Side effects separados por coma."""
    src = """\
// CONTRATO:
//   output: void
//   side_effects: escribe en DB, envía email, actualiza caché
function processOrder(): void {
    db.save();
    email.send();
    cache.update();
}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["side_effects"] == [
        "escribe en DB",
        "envía email",
        "actualiza caché",
    ]


def test_rn_sin_descripcion():
    """RN sin descripción debe tener id pero descripción vacía."""
    src = """\
// CONTRATO:
//   rn:
//     - RN-999
function checkRn(): boolean {
    return true;
}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["rn"] == [{"id": "RN-999", "descripcion": ""}]


def test_sin_campos_opcionales():
    """CONTRATO sin campos opcionales debe tener valores por defecto."""
    src = """\
// CONTRATO:
//   output: void
//   side_effects: ninguno
function noop(): void {}
"""
    archivo = _crear_temporal(src)
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    c = contratos[0]
    assert c["input"] == {}
    assert c["rn"] == []
    assert c["borde"] == []
    assert c["dependencias"] == []


def test_formato_mixto_tsx():
    """Debe funcionar con archivos .tsx."""
    src = """\
// CONTRATO:
//   input:
//     props: object
//   output: JSX.Element
function MiComponente(props: { name: string }): JSX.Element {
    return <div>{props.name}</div>;
}
"""
    archivo = _crear_temporal(src, ext=".tsx")
    contratos = extraer_contratos_ts(str(archivo))
    assert len(contratos) == 1
    assert contratos[0]["nombre_funcion"] == "MiComponente"

# docpact — Spec Examples

> Practical, self-contained examples for every part of the Contrato Protocol.
> Each example can be copy-pasted into a test or used as a reference implementation.

---

## 1. CONTRATO Examples

### 1.1 Minimal CONTRATO

The smallest valid contract. Only `side_effects` is mandatory.

```python
def limpiar_cache() -> None:
    """CONTRATO:
    side_effects: ninguno
    """
    import shutil
    shutil.rmtree("/tmp/app_cache", ignore_errors=True)
```

**What the parser extracts:**

```python
Contrato(
    input={},
    output=None,
    side_effects=[],
    rn=[],
    borde=[],
    dependencias=[],
)
```

**Verification result:** PASS — function declares no side effects and the AST walker
finds no calls matching configured patterns (`.create`, `send_mail`, etc.).

---

### 1.2 Standard Function CONTRATO

A typical function contract with all core fields.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class HorasCalculadas:
    total_horas: float
    total_segundos: int


def sumar_sesiones(tickets: list) -> HorasCalculadas:
    """Calcula horas totales de sesiones de trabajo.

    CONTRATO:
      input:
        tickets: list[Ticket] — Tickets con sesiones precargadas.
      output: HorasCalculadas — Total de horas y segundos.
      side_effects: ninguno
      rn:
        - RN-002: solo sesiones completadas descuentan horas
      borde:
        - tickets vacío: retorna HorasCalculadas(0, 0)
        - sesión sin fin: se ignora
      dependencias:
        - soporte/models/ticket.py::Ticket
    """
    total = 0
    for ticket in (tickets or []):
        for sesion in getattr(ticket, 'sesiones', []):
            if sesion.get('fin'):  # RN-002
                total += (sesion['fin'] - sesion['inicio']).total_seconds()
    return HorasCalculadas(total_horas=total / 3600, total_segundos=int(total))
```

**Parsed Contrato:**

```python
Contrato(
    input={"tickets": CampoInput(nombre="tickets", tipo="list[Ticket]", descripcion="Tickets con sesiones precargadas.")},
    output="HorasCalculadas",
    output_descripcion="Total de horas y segundos.",
    side_effects=[],
    rn=[ReglaNegocio(id="RN-002", descripcion="solo sesiones completadas descuentan horas")],
    borde=[
        CasoBorde(condicion="tickets vacío", comportamiento="retorna HorasCalculadas(0, 0)"),
        CasoBorde(condicion="sesión sin fin", comportamiento="se ignora"),
    ],
    dependencias=[Dependencia(ref="soporte/models/ticket.py::Ticket")],
)
```

**Verification details:**

| Check | Result | Reason |
|-------|--------|--------|
| side_effects | ✅ PASS | No calls match db_write/email/external patterns |
| RN-002 | ✅ PASS | `# RN-002` comment found at line 14 in function body |
| dependencias | ⚠️ WARN | `soporte/models/ticket.py` — existence depends on project layout |

---

### 1.3 Full CONTRATO with Semantic Fields

Extended contract using the optional semantic fields (`comportamiento`, `asume`, `produce`).

```python
def crear_ticket(
    titulo: str,
    descripcion: str,
    solicitante_id: int,
    categoria: str,
) -> Ticket:
    """Crea un nuevo ticket de soporte con validación de negocio.

    CONTRATO:
      comportamiento: Crea un ticket en estado ABIERTO con los datos provistos.
        Valida que el solicitante exista y que la categoría sea válida.
        Asigna automáticamente un número de ticket secuencial.
      asume: solicitante_id existe en la tabla de usuarios.
        categoría es una de: 'INCIDENCIA', 'CONSULTA', 'REQUERIMIENTO'.
      produce: Inserta fila en tickets. Actualiza contador_secuencial_tickets.
      input:
        titulo: str — Título descriptivo del ticket (máx 200 chars)
        descripcion: str — Detalle del problema o solicitud
        solicitante_id: int — ID del usuario que solicita
        categoria: str — Tipo de ticket
      output: Ticket — Ticket creado con ID asignado
      side_effects: db_write, notificación_creación
      rn:
        - RN-TKT-001: todo ticket debe tener título no vacío
        - RN-TKT-003: ticket incorrecto puede ser anulado por supervisión
      borde:
        - titulo vacío: ValueError
        - solicitante inexistente: ValueError
        - categoría inválida: ValueError
      dependencias:
        - soporte/models/ticket.py::Ticket
        - soporte/models/contador.py::SecuencialTicket
    """
    # RN-TKT-001: validar título
    if not titulo or not titulo.strip():
        raise ValueError("El título no puede estar vacío")

    # Validar categoría
    categorias_validas = {"INCIDENCIA", "CONSULTA", "REQUERIMIENTO"}
    if categoria not in categorias_validas:
        raise ValueError(f"Categoría inválida: {categoria}")

    # Asignar número secuencial
    numero = SecuencialTicket.siguiente()  # side effect: actualiza contador

    # Crear el ticket en BD
    ticket = Ticket.objects.create(  # side effect: db_write
        titulo=titulo.strip(),
        descripcion=descripcion,
        solicitante_id=solicitante_id,
        categoria=categoria,
        numero=numero,
        estado="ABIERTO",
    )

    # Notificar
    notificar_creacion(ticket)  # side effect: notificación

    return ticket
```

**Parsed semantic fields:**

```python
assert contrato.comportamiento is not None
assert "Crea un ticket en estado ABIERTO" in contrato.comportamiento
assert contrato.asume is not None
assert "solicitante_id existe" in contrato.asume
assert contrato.produce is not None
assert "Inserta fila en tickets" in contrato.produce
assert contrato.tiene_campos_semanticos() is True
```

---

### 1.4 Delegation CONTRATO

When a function delegates to another service. The `marker_honesty` checker
flags this pattern — the `# RN-XXX` comment is on a delegation line.

```python
def cancelar_ticket(ticket_id: int, editor_id: int, motivo: str) -> None:
    """Cancela un ticket delegando al servicio de tickets.

    CONTRATO:
      input:
        ticket_id: int — ID del ticket a cancelar
        editor_id: int — ID del usuario que cancela
        motivo: str — Razón de la cancelación
      output: ninguno
      side_effects: db_write, notificación_cancelación
      rn:
        - RN-TKT-003: ticket incorrecto puede ser anulado por supervisión
    """
    # ⚠️ marker_honesty WARNING: RN-TKT-003 on delegation line
    TicketService.cancelar(ticket_id, editor_id, motivo)  # RN-TKT-003
```

**Marker honesty output:**

```
WARN: 'cancelar_ticket': RN-TKT-003 marcada en línea de delegación (línea 6).
La función no parece implementar la lógica de la regla, solo delega a
otro método. Verificar manualmente.
```

**Correct delegation — move the RN marker to where logic exists:**

```python
def cancelar_ticket(ticket_id: int, editor_id: int, motivo: str) -> None:
    """Cancela un ticket con validación de permisos.

    CONTRATO:
      input:
        ticket_id: int — ID del ticket a cancelar
        editor_id: int — ID del usuario que cancela
        motivo: str — Razón de la cancelación
      output: ninguno
      side_effects: db_write, notificación_cancelación
      rn:
        - RN-TKT-003: ticket incorrecto puede ser anulado por supervisión
    """
    ticket = Ticket.objects.get(id=ticket_id)
    # RN-TKT-003: solo supervisión puede cancelar
    if not _es_supervision(editor_id):
        raise PermissionError("Solo supervisión puede cancelar tickets")
    TicketService.cancelar(ticket, editor_id, motivo)
```

---

### 1.5 Class CONTRATO

Contracts work on classes and methods.

```python
class TicketService:
    """Servicio principal de gestión de tickets.

    CONTRATO:
      side_effects: db_write, email
      rn:
        - RN-TKT-001: todo ticket debe tener título no vacío
        - RN-TKT-004: no se permite saltar entre estados
    """

    def crear(self, titulo: str, solicitante_id: int) -> "Ticket":
        """Crea un ticket.

        CONTRATO:
          input:
            titulo: str — Título del ticket
            solicitante_id: int — ID del solicitante
          output: Ticket
          side_effects: db_write
          rn:
            - RN-TKT-001: todo ticket debe tener título no vacío
        """
        if not titulo.strip():  # RN-TKT-001
            raise ValueError("Título vacío")
        return Ticket.objects.create(titulo=titulo, solicitante_id=solicitante_id)

    def cambiar_estado(self, ticket_id: int, nuevo_estado: str) -> "Ticket":
        """Transiciona un ticket a un nuevo estado.

        CONTRATO:
          input:
            ticket_id: int
            nuevo_estado: str — Estado destino
          output: Ticket
          side_effects: db_write, notificación_cambio_estado
          rn:
            - RN-TKT-004: no se permite saltar entre estados
        """
        ticket = Ticket.objects.get(id=ticket_id)
        # RN-TKT-004: verificar transición permitida
        if not self._transicion_valida(ticket.estado, nuevo_estado):
            raise ValueError(f"No se puede ir de {ticket.estado} a {nuevo_estado}")
        ticket.estado = nuevo_estado
        ticket.save()
        return ticket
```

---

### 1.6 TypeScript CONTRATO

```typescript
/**
 * Calcula el total de horas facturables para un contrato.
 *
 * CONTRATO:
 *   input:
 *     contratoId: number — ID del contrato
 *     mes: string — Mes en formato YYYY-MM
 *   output: number — Total de horas facturables
 *   side_effects: ninguno
 *   rn:
 *     - RN-002: solo sesiones completadas descuentan horas
 *   dependencias:
 *     - src/services/sesiones.ts::getSesionesFacturables
 */
export function calcularHoras(contratoId: number, mes: string): number {
  const sesiones = getSesionesFacturables(contratoId, mes);
  return sesiones
    .filter((s) => s.completada) // RN-002
    .reduce((total, s) => total + s.horas, 0);
}
```

---

### 1.7 Go CONTRATO

```go
// CONTRATO:
//   input:
//     ticketID: int64 — ID del ticket
//     userID: int64 — ID del usuario
//   output: *Ticket — Ticket resuelto
//   side_effects: Actualiza estado, registra bitácora, envía notificación
//   rn:
//     - RN-010: solo administradores pueden resolver
//   dependencias:
//     - internal/store/ticket.go::ResolveTicket
func (s *TicketService) ResolveTicket(ctx context.Context, ticketID, userID int64) (*Ticket, error) {
    user, err := s.store.GetUser(ctx, userID)
    if err != nil {
        return nil, err
    }
    if !user.IsAdmin { // RN-010
        return nil, ErrForbidden
    }
    return s.store.ResolveTicket(ctx, ticketID, userID)
}
```

---

## 2. MCP Tool Call Examples

The docpact MCP server exposes tools via JSON-RPC 2.0 over stdio.
These examples show the tool inputs and expected outputs.

### 2.1 `obtener_contexto_funcion` — Get function context

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "obtener_contexto_funcion",
    "arguments": {
      "nombre_funcion": "sumar_sesiones"
    }
  }
}
```

**Response (single match):**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"existe\": true, \"funcion\": \"sumar_sesiones\", \"tipo\": \"function\", \"archivo\": \"soporte/services/horas.py\", \"linea\": 15, \"contrato\": {\"side_effects\": \"ninguno\", \"rn\": [\"RN-002\"], \"input\": [\"tickets: list[Ticket]\"], \"output\": \"HorasCalculadas\"}, \"rn_ids\": [\"RN-002\"], \"tests\": [\"tests/test_horas.py::test_sumar_sesiones_vacio\", \"tests/test_horas.py::test_sumar_sesiones_completas\"]}"
      }
    ]
  }
}
```

**Response (not found):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"existe\": false, \"busqueda\": \"funcion_inexistente\", \"sugerencia\": \"Intenta con un nombre más específico o usa buscar_por_intencion\"}"
      }
    ]
  }
}
```

**Response (multiple matches):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"existe\": true, \"multiples\": [{\"funcion\": \"crear_ticket\"}, {\"funcion\": \"crear_ticket_rapido\"}], \"count\": 2}"
      }
    ]
  }
}
```

---

### 2.2 `buscar_por_intencion` — Semantic search

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "buscar_por_intencion",
    "arguments": {
      "intencion": "validar RUT de cliente"
    }
  }
}
```

**Response (with embeddings):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"resultados\": [{\"funcion\": \"validar_rut\", \"archivo\": \"soporte/validators.py\", \"rn_ids\": [\"RN-RUT-001\"]}, {\"funcion\": \"validar_rut_empresa\", \"archivo\": \"soporte/validators.py\", \"rn_ids\": [\"RN-RUT-002\"]}], \"scores\": [0.9234, 0.7102], \"busqueda_tipo\": \"semantica\", \"count\": 2, \"total_en_indice\": 47}"
      }
    ]
  }
}
```

**Response (keyword-only fallback):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"resultados\": [{\"funcion\": \"validar_rut\", \"archivo\": \"soporte/validators.py\", \"rn_ids\": [\"RN-RUT-001\"]}], \"scores\": [2.5], \"busqueda_tipo\": \"keyword\", \"count\": 1, \"total_en_indice\": 47}"
      }
    ]
  }
}
```

---

### 2.3 `validar_cambio` — Validate diff before commit (ENFORCEMENT)

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "validar_cambio",
    "arguments": {
      "archivo": "soporte/views/portal.py",
      "diff": "def crear_ticket(request):\n    # RN-FAKE-999: nueva regla inventada\n    ticket = Ticket.objects.create(titulo=request.POST['titulo'])\n    return ticket",
      "ejecutar_tests": true
    }
  }
}
```

**Response (change rejected — fake RN):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"valido\": false, \"errores\": [{\"tipo\": \"rn_fake\", \"rn\": \"RN-FAKE-999\", \"mensaje\": \"RN 'RN-FAKE-999' no existe en REGISTRO.md\", \"accion\": \"Quita 'RN-FAKE-999' del CONTRATO o agrégala a docs/reglas-del-negocio/REGISTRO.md\"}], \"warnings\": [], \"test_results\": [], \"resumen\": \"1 error(es), 0 warning(s). Cambio INVÁLIDO.\"}"
      }
    ]
  }
}
```

**Response (change approved):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"valido\": true, \"errores\": [], \"warnings\": [{\"tipo\": \"rn_sin_test\", \"rn\": \"RN-TKT-001\", \"mensaje\": \"RN 'RN-TKT-001' no tiene test file\", \"accion\": \"Crea tests/rn/test_rn_TKT001.py con Hypothesis PBT\"}], \"test_results\": [{\"test\": \"tests/test_tickets.py\", \"status\": \"PASS\"}], \"resumen\": \"0 error(es), 1 warning(s). Cambio VÁLIDO.\"}"
      }
    ]
  }
}
```

---

### 2.4 `obtener_rn` — Get business rule context

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "obtener_rn",
    "arguments": {
      "rn_id": "RN-TKT-003"
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"existe\": true, \"id\": \"RN-TKT-003\", \"descripcion\": \"Ticket incorrecto puede ser anulado por supervisión\", \"funciones\": [{\"funcion\": \"cancelar_ticket\", \"archivo\": \"soporte/services/tickets.py\"}, {\"funcion\": \"anular_ticket\", \"archivo\": \"soporte/services/tickets.py\"}], \"tiene_test\": true, \"test\": \"tests/rn/test_rn_TKT003.py\", \"en_registro\": true}"
      }
    ]
  }
}
```

**Response (not found, with partial matches):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"existe\": false, \"busqueda\": \"RN-TKT-999\", \"coincidencias_parciales\": [\"RN-TKT-001\", \"RN-TKT-003\", \"RN-TKT-004\"]}"
      }
    ]
  }
}
```

---

### 2.5 `navegar_referencias` — Cross-reference navigation

**Request (by RN):**

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "navegar_referencias",
    "arguments": {
      "referencia": "RN-TKT-001"
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"existe\": true, \"tipo\": \"rn\", \"rn\": {\"id\": \"RN-TKT-001\", \"descripcion\": \"Todo ticket debe tener título no vacío\", \"funciones\": [{\"funcion\": \"crear_ticket\", \"archivo\": \"soporte/views/portal.py\"}]}, \"funciones_que_la_implementan\": [{\"funcion\": \"crear_ticket\", \"archivo\": \"soporte/views/portal.py\"}]}"
      }
    ]
  }
}
```

**Request (by file):**

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "tools/call",
  "params": {
    "name": "navegar_referencias",
    "arguments": {
      "referencia": "soporte/views/portal.py"
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"existe\": true, \"tipo\": \"archivo\", \"archivo\": \"soporte/views/portal.py\", \"funciones\": [{\"funcion\": \"crear_ticket\", \"linea\": 15, \"rn_ids\": [\"RN-TKT-001\"]}, {\"funcion\": \"listar_tickets\", \"linea\": 42, \"rn_ids\": []}], \"rns_usadas\": [\"RN-TKT-001\"]}"
      }
    ]
  }
}
```

**Request (by function):**

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "tools/call",
  "params": {
    "name": "navegar_referencias",
    "arguments": {
      "referencia": "crear_ticket"
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"existe\": true, \"tipo\": \"funcion\", \"funciones\": [{\"funcion\": \"crear_ticket\", \"archivo\": \"soporte/views/portal.py\", \"linea\": 15, \"tipo\": \"function\", \"rn_ids\": [\"RN-TKT-001\"]}]}"
      }
    ]
  }
}
```

---

### 2.6 `verificar_conflicto` — Check for RN conflicts before creating

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": 8,
  "method": "tools/call",
  "params": {
    "name": "verificar_conflicto",
    "arguments": {
      "rn_descripcion": "Los tickets deben tener título no vacío antes de ser creados"
    }
  }
}
```

**Response (duplicate detected):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"conflictos\": [{\"tipo\": \"duplicado\", \"rn_id\": \"RN-TKT-001\", \"descripcion\": \"Todo ticket debe tener título no vacío\", \"similitud\": 0.82, \"explicacion\": \"La RN propuesta es muy similar a RN-TKT-001. Podría ser un duplicado.\", \"accion\": \"Revisá si es la misma regla. Si lo es, usá RN-TKT-001 en lugar de crear una nueva.\"}], \"puede_crear\": false, \"sugerencia\": \"Revisá los conflictos antes de crear la RN.\"}"
      }
    ]
  }
}
```

**Response (no conflicts):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"conflictos\": [], \"puede_crear\": true, \"sugerencia\": \"No se detectaron conflictos. Podés crear la RN con crear_rn.\"}"
      }
    ]
  }
}
```

---

### 2.7 `modificar_archivo` — Guard validation before applying changes

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": 9,
  "method": "tools/call",
  "params": {
    "name": "modificar_archivo",
    "arguments": {
      "archivo": "soporte/services/tickets.py",
      "diff": "def crear_ticket(titulo, solicitante_id):\n    # Agregar email de confirmación\n    ticket = Ticket.objects.create(titulo=titulo)\n    send_mail('Ticket creado', '...', 'from@x.com', ['to@x.com'])\n    return ticket"
    }
  }
}
```

**Response (rejected — undeclared side effect):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"allowed\": false, \"message\": \"Cambio RECHAZADO: 1 violación(es) detectada(s)\", \"violations\": [{\"funcion\": \"crear_ticket\", \"tipo\": \"side_effect_undeclared\", \"mensaje\": \"Función 'crear_ticket' usa 'send_mail' (categoría: email) pero no lo declara en side_effects\", \"sugerencia\": \"Agregá 'email' al campo side_effects del CONTRATO de crear_ticket\"}]}"
      }
    ]
  }
}
```

**Response (approved):**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"allowed\": true, \"message\": \"Cambio seguro en 1 función(es)\", \"violations\": []}"
      }
    ]
  }
}
```

---

### 2.8 `listar_rns` — List all business rules

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "tools/call",
  "params": {
    "name": "listar_rns",
    "arguments": {}
  }
}
```

**Response:**

```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"rns\": [{\"id\": \"RN-TKT-001\", \"descripcion\": \"Todo ticket debe tener título no vacío\", \"funciones\": [\"crear_ticket\"], \"tiene_test\": true, \"en_registro\": true}, {\"id\": \"RN-TKT-003\", \"descripcion\": \"Ticket incorrecto puede ser anulado por supervisión\", \"funciones\": [\"cancelar_ticket\", \"anular_ticket\"], \"tiene_test\": true, \"en_registro\": true}, {\"id\": \"RN-TKT-004\", \"descripcion\": \"No se permite saltar entre estados\", \"funciones\": [\"cambiar_estado\"], \"tiene_test\": false, \"en_registro\": true}], \"total\": 3, \"con_test\": 2, \"en_registro\": 3}"
      }
    ]
  }
}
```

---

## 3. Verification Output Examples

### 3.1 `docpact check` — Clean project

```
$ docpact check .

docpact check — 12 archivos, 34 funciones
  Con CONTRATO: 28/34 (82%)
  Errores: 0
  Warnings: 2

Score: 87/100 — L3 — AI-Native

Warnings:
  ⚠ soporte/views/portal.py:45 listar_tickets — side_effects declarado pero no detectado en AST
  ⚠ soporte/services/horas.py:12 sumar_sesiones — dependencia soporte/models/ticket.py no encontrada
```

### 3.2 `docpact check --strict` — Functions without CONTRATO

```
$ docpact check . --strict

docpact check — 12 archivos, 34 funciones
  Con CONTRATO: 28/34 (82%)
  Errores: 6
  Warnings: 2

Score: 52/100 — L2 — AI-Friendly

Errores:
  ✗ soporte/utils.py:3 formatear_rut — función pública sin CONTRATO (--strict)
  ✗ soporte/utils.py:18 limpiar_texto — función pública sin CONTRATO (--strict)
  ✗ soporte/views/portal.py:89 _calcular_descuento — función pública sin CONTRATO (--strict)
  ... y 3 más
```

### 3.3 `docpact check` — RN not implemented

```
$ docpact check .

docpact check — 5 archivos, 15 funciones
  Con CONTRATO: 15/15 (100%)
  Errores: 1
  Warnings: 0

Score: 75/100 — L3 — AI-Native

Errores:
  ✗ soporte/services/tickets.py:30 crear_ticket — RN-TKT-001 declarada en CONTRATO pero
    comentario # RN-TKT-001 no encontrado en el cuerpo de la función
```

### 3.4 `docpact check --json` — Machine-readable output

```json
{
  "archivos": [
    {
      "archivo": "soporte/services/tickets.py",
      "funciones": [
        {
          "funcion": "crear_ticket",
          "linea": 15,
          "tiene_contrato": true,
          "errores": [],
          "warnings": [],
          "hallazgos": []
        },
        {
          "funcion": "_calcular_prioridad",
          "linea": 45,
          "tiene_contrato": false,
          "errores": [],
          "warnings": [],
          "hallazgos": []
        }
      ]
    }
  ],
  "total_funciones": 34,
  "funciones_con_contrato": 28,
  "total_errores": 0,
  "total_warnings": 2,
  "score": 87,
  "nivel": "L3 — AI-Native"
}
```

### 3.5 `docpact report` — RN delta report

```
$ docpact report

Reglas de Negocio — Delta REGISTRO.md vs Código

| RN         | Descripción                              | Implementación        | Test  |
|------------|------------------------------------------|-----------------------|-------|
| RN-TKT-001 | Todo ticket debe tener título no vacío    | ✅ crear_ticket       | ✅    |
| RN-TKT-003 | Ticket incorrecto puede ser anulado       | ✅ cancelar_ticket    | ✅    |
| RN-TKT-004 | No se permite saltar entre estados        | ✅ cambiar_estado     | ❌    |
| RN-FAC-001 | Factura requiere RUT válido               | ❌ NO IMPLEMENTADA    | ❌    |

Resumen: 3/4 implementadas (75%), 2/4 con test (50%)
```

---

## 4. Discovery Flow Examples

### 4.1 Agent starts work — reads briefing first

```
Agent: "Voy a modificar el servicio de tickets"

Step 1: Call obtener_briefing
  → Returns .docpact/briefing.md with:
    - 12 RNs activas
    - 3 zonas de riesgo (side effects declarados)
    - Funciones más referenciadas

Step 2: Call buscar_por_intencion("modificar estado ticket")
  → Returns: cambiar_estado() in soporte/services/tickets.py
  → Score: 0.91 (semantica)

Step 3: Call obtener_contexto_funcion("cambiar_estado")
  → Returns:
    - CONTRATO completo
    - RNs: [RN-TKT-004]
    - Tests: [tests/test_tickets.py::test_cambiar_estado_valido]
    - Side effects: db_write, notificación_cambio_estado

Step 4: Agent modifies code, respecting RN-TKT-004

Step 5: Call validar_cambio(archivo, diff)
  → {valido: true, errores: [], warnings: []}

Step 6: Agent commits
```

### 4.2 Agent discovers related rules via cross-references

```
Agent: "¿Qué funciones implementan RN-TKT-003?"

Step 1: Call navegar_referencias("RN-TKT-003")
  → {
      tipo: "rn",
      funciones_que_la_implementan: [
        {funcion: "cancelar_ticket", archivo: "soporte/services/tickets.py"},
        {funcion: "anular_ticket", archivo: "soporte/services/tickets.py"}
      ]
    }

Step 2: Call obtener_contexto_funcion("anular_ticket")
  → Agent sees anular_ticket has its own CONTRATO with RN-TKT-003

Step 3: Agent understands the full picture before making changes
```

### 4.3 Agent checks for conflicts before creating a new RN

```
Agent: "Quiero crear una nueva RN sobre prioridad de tickets"

Step 1: Call verificar_conflicto("Los tickets deben tener prioridad asignada")
  → {
      conflictos: [
        {
          tipo: "mismo_concepto",
          rn_id: "RN-TKT-005",
          descripcion: "Tickets de alta prioridad deben escalarse automáticamente",
          similitud: 0.45,
          explicacion: "La RN propuesta trata un tema similar a RN-TKT-005..."
        }
      ],
      puede_crear: true,
      sugerencia: "Revisá los conflictos antes de crear la RN."
    }

Step 2: Agent decides — different enough, proceeds to create_rn

Step 3: Call crear_rn("RN-TKT-006", "Los tickets deben tener prioridad asignada antes de 24 horas")
  → {creado: true, rn_id: "RN-TKT-006"}
```

### 4.4 Agent searches by intent (no exact function name)

```
Agent: "Necesito encontrar dónde se validan los RUTs"

Step 1: Call buscar_por_intencion("validar RUT")
  → {
      resultados: [
        {funcion: "validar_rut", archivo: "soporte/validators.py", rn_ids: ["RN-RUT-001"]},
        {funcion: "validar_rut_empresa", archivo: "soporte/validators.py", rn_ids: ["RN-RUT-002"]},
        {funcion: "formato_rut", archivo: "soporte/utils.py", rn_ids: []}
      ],
      scores: [0.92, 0.78, 0.34],
      busqueda_tipo: "semantica"
    }

Step 2: Agent picks validar_rut, gets full context
```

---

## 5. Migration Examples

### 5.1 Adding CONTRATO to existing function (narrative → structured)

**Before (narrative docstring):**

```python
def sumar_sesiones(tickets):
    """Calcula horas totales a partir de lista de tickets con sesiones prefetched."""
    total = 0.0
    for t in tickets:
        for s in t.sesiones.all():
            if s.fin:
                total += (s.fin - s.inicio).total_seconds()
    return round(total / 3600, 2)
```

**After (with CONTRATO):**

```python
def sumar_sesiones(tickets: list) -> HorasCalculadas:
    """Calcula horas totales de sesiones de trabajo.

    CONTRATO:
      input:
        tickets: list[Ticket] — Tickets con sesiones precargadas.
              Sin prefetch → N+1 queries
      output: HorasCalculadas — Total de horas y segundos.
      side_effects: ninguno
      rn:
        - RN-002: solo sesiones completadas descuentan horas
      borde:
        - tickets vacío: retorna HorasCalculadas(0, 0)
        - sesión sin fin: se ignora
      dependencias:
        - soporte/models/ticket.py::Ticket
    """
    total = 0
    for ticket in (tickets or []):
        for sesion in getattr(ticket, 'sesiones', []):
            if sesion.get('fin'):  # RN-002
                total += (sesion['fin'] - sesion['inicio']).total_seconds()
    return HorasCalculadas(total_horas=total / 3600, total_segundos=int(total))
```

**Migration checklist:**

1. ✅ Add type hints to signature
2. ✅ Add `CONTRATO:` block in docstring
3. ✅ Declare `side_effects` (mandatory)
4. ✅ Add `# RN-XXX` comments in body for each declared RN
5. ✅ Replace raw `dict` return with frozen dataclass
6. ✅ Run `docpact check .` — verify no errors

---

### 5.2 Adding RN markers to existing code

**Before (RN declared but not marked in code):**

```python
def suspender_ticket(ticket_id, editor, motivo):
    """
    CONTRATO:
      side_effects: db_write
      rn:
        - RN-TKT-004: no se permite saltar entre estados
    """
    ticket = Ticket.objects.get(id=ticket_id)
    if ticket.estado == "CERRADO":
        raise ValueError("No se puede suspender un ticket cerrado")
    ticket.estado = "SUSPENDIDO"
    ticket.save()
```

**After (RN marker added):**

```python
def suspender_ticket(ticket_id, editor, motivo):
    """
    CONTRATO:
      side_effects: db_write
      rn:
        - RN-TKT-004: no se permite saltar entre estados
    """
    ticket = Ticket.objects.get(id=ticket_id)
    # RN-TKT-004: verificar transición permitida
    if ticket.estado == "CERRADO":
        raise ValueError("No se puede suspender un ticket cerrado")
    ticket.estado = "SUSPENDIDO"
    ticket.save()
```

**Why:** The `rn` checker looks for `# RN-XXX` comments in the function body.
Without the marker, verification reports the RN as "declared but not found in code".

---

### 5.3 Migrating from `dict` returns to frozen DTOs

**Before:**

```python
def obtener_resumen(usuario_id):
    """CONTRATO:
      output: dict con keys total_horas, total_tickets
      side_effects: ninguno
    """
    horas = calcular_horas(usuario_id)
    tickets = contar_tickets(usuario_id)
    return {"total_horas": horas, "total_tickets": tickets}
```

**After:**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ResumenUsuario:
    """Contrato: esto es lo único que devuelve obtener_resumen()."""
    total_horas: float
    total_tickets: int


def obtener_resumen(usuario_id: int) -> ResumenUsuario:
    """Obtiene resumen de actividad del usuario.

    CONTRATO:
      input:
        usuario_id: int — ID del usuario
      output: ResumenUsuario — Resumen de horas y tickets
      side_effects: ninguno
    """
    horas = calcular_horas(usuario_id)
    tickets = contar_tickets(usuario_id)
    return ResumenUsuario(total_horas=horas, total_tickets=tickets)
```

**Why:** `dict` returns let agents invent fields. Frozen dataclasses fail at import
time if a caller tries to access a nonexistent field — the error surfaces immediately,
not in production.

---

### 5.4 Adding `docpact.toml` to existing project

```toml
# docpact.toml
[docpact]
strict = false
min_score = 75
exclude = ["tests/", "migrations/", "__pycache__/", "scripts/"]

[docpact.side_effects]
db_write = [".create", ".save", ".update", ".bulk_create", ".delete"]
email = ["send_mail", "EmailMessage", "send_mass_mail"]
external_http = ["requests.", "httpx.", "urllib.request"]
audit = ["registrar_evento_bitacora"]
notification = ["_notificar_", "notificar_"]

[docpact.rules]
rn_prefix = "RN-"

[docpact.marker_honesty]
enabled = true
max_rns_per_function = 5

[docpact.suppress]
patterns = ["No se encontró bloque CONTRATO"]
```

**Initialization commands:**

```bash
# Install docpact
pip install docpact

# Generate index for MCP server
docpact index .

# Run first check
docpact check .

# Generate briefing for agents
docpact briefing .
```

---

### 5.5 Adding to CI/CD pipeline

**GitHub Actions:**

```yaml
# .github/workflows/docpact.yml
name: docpact
on: [push, pull_request]
jobs:
  docpact:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install docpact
        run: pip install docpact
      - name: Check contracts
        run: docpact check . --config docpact.toml
```

**Pre-commit hook:**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: docpact
        name: docpact check
        entry: docpact check . --config docpact.toml
        language: system
        types: [python]
        stages: [pre-commit]
```

---

### 5.6 Incremental adoption — start with one module

**Phase 1:** Add CONTRATO to the most-modified file only.

```bash
# Check just one file
docpact check soporte/services/tickets.py
```

**Phase 2:** Add `strict = false` to config. No penalty for functions without CONTRATO.

**Phase 3:** As coverage grows, raise `min_score` gradually:
- Week 1: `min_score = 50`
- Week 4: `min_score = 75`
- Week 8: `min_score = 90`

**Phase 4:** Enable `strict = true` — every public function needs a CONTRATO.

---

## 6. Indentation Style Examples

The parser accepts two equivalent styles.

### Style A — Fields at CONTRATO level (recommended)

```python
def ejemplo():
    """CONTRATO:
    input:
      x: int
    side_effects: ninguno
    """
```

### Style B — Fields indented +2

```python
def ejemplo():
    """CONTRATO:
      input:
        x: int
      side_effects: ninguno
    """
```

Both parse to the same `Contrato` object. The parser auto-detects the style.

---

## 7. Error and Edge Case Examples

### 7.1 Missing side_effects field

```python
def broken():
    """CONTRATO:
    input:
      x: int
    """
```

**Parser output:**

```python
Contrato(
    input={"x": CampoInput(nombre="x", tipo="int")},
    side_effects=[],  # empty — triggers warning
)
# ErrorParser: [side_effects] L0: side_effects es obligatorio pero no se declaró
```

### 7.2 Malformed RN reference

```python
def broken_rn():
    """CONTRATO:
    side_effects: ninguno
    rn:
      - sin-prefijo: esto no es válido
    """
```

**Parser output:**

```python
# ErrorParser: [rn] L4: Formato de RN inválido 'sin-prefijo'. Se esperaba RN-XXX
```

### 7.3 RN declared but not in code body

```python
def crear_ticket(titulo: str) -> Ticket:
    """
    CONTRATO:
      side_effects: db_write
      rn:
        - RN-TKT-001: título no vacío
    """
    return Ticket.objects.create(titulo=titulo)  # Missing: # RN-TKT-001 comment
```

**Checker output:**

```
✗ crear_ticket — RN-TKT-001 declarada en CONTRATO pero comentario # RN-TKT-001
  no encontrado en el cuerpo de la función
```

### 7.4 Undeclared side effect

```python
def enviar_notificacion(usuario_id: int) -> None:
    """
    CONTRATO:
      side_effects: ninguno
    """
    send_mail("Notificación", "contenido", "from@x.com", ["to@x.com"])
```

**Checker output:**

```
✗ enviar_notificacion — side_effects declaró 'ninguno' pero se detectaron
  efectos reales: email
  Sugerencia: declarar 'email' en side_effects
```

---

## 8. Programmatic API Examples

### 8.1 Extract contracts from a file

```python
from docpact.parser.extractor import extraer_docstrings

# Extract all CONTRATO blocks from a file
resultados = extraer_docstrings("soporte/services/tickets.py")

for r in resultados:
    print(f"{r.funcion} ({r.tipo.value}) at line {r.linea}")
    if r.es_valido:
        print(f"  side_effects: {[s.descripcion for s in r.contrato.side_effects]}")
        print(f"  rns: {[rn.id for rn in r.contrato.rn]}")
    else:
        for err in r.errores:
            print(f"  ERROR: {err}")
```

### 8.2 Verify a project programmatically

```python
from docpact.config import DocpactConfig
from docpact.checker.orchestrator import check_proyecto

config = DocpactConfig.desde_toml("docpact.toml")
resultado = check_proyecto(".", config)

print(f"Functions: {resultado.total_funciones}")
print(f"With CONTRATO: {resultado.funciones_con_contrato}")
print(f"Errors: {resultado.total_errores}")
print(f"Score: {resultado.calcular_score()}")
print(f"Level: {resultado.nivel}")

# Honest metrics (preferred over score)
metricas = resultado.metricas_honestas()
print(f"Fake RNs: {metricas['rns_fake']}")
print(f"Orphan RNs: {metricas['rns_huerfanas']}")
print(f"Functions without CONTRATO: {metricas['funciones_sin_contrato']}")
```

### 8.3 Validate a change via guard

```python
from docpact.guard import validar_cambio

resultado = validar_cambio(
    archivo="soporte/services/tickets.py",
    diff="def crear_ticket(titulo):\n    send_mail('x','x','x',['x'])\n    return Ticket.objects.create(titulo=titulo)",
    project_root=".",
)

if not resultado.allowed:
    print("CHANGE REJECTED:")
    for v in resultado.violations:
        print(f"  [{v.tipo}] {v.funcion}: {v.mensaje}")
        print(f"    → {v.sugerencia}")
else:
    print(f"OK: {resultado.message}")
```

### 8.4 Generate and load index

```python
from docpact.index import generar_index, guardar_index, cargar_index

# Generate index
index = generar_index(".")

# Save for MCP server
path = guardar_index(index, ".")
print(f"Index saved to {path}")
print(f"Functions indexed: {len(index['funciones'])}")
print(f"RNs indexed: {len(index['rns'])}")

# Load existing index
cached = cargar_index(".")
if cached:
    print(f"Loaded {len(cached['funciones'])} functions from cache")
```

---

## 9. `docpact.toml` Configuration Reference

```toml
[docpact]
strict = false              # Require CONTRATO on all public functions
min_score = 75              # Minimum score for CI pass
exclude = [                 # Paths to skip
    "tests/",
    "migrations/",
    "__pycache__/",
    ".venv/",
]

[docpact.side_effects]      # Patterns for AST-based side effect detection
db_write = [".create", ".save", ".update", ".bulk_create", ".delete"]
email = ["send_mail", "EmailMessage", "send_mass_mail"]
external_http = ["requests.", "httpx.", "urllib.request"]
audit = ["registrar_evento_bitacora"]
notification = ["_notificar_", "notificar_"]

[docpact.rules]
rn_prefix = "RN-"           # Prefix for business rule IDs

[docpact.marker_honesty]    # Detect suspicious RN markers
enabled = true
max_rns_per_function = 5    # Functions with more RNs get a warning

[docpact.suppress]          # Suppress specific warning patterns
patterns = [
    "No se encontró bloque CONTRATO",
]
```

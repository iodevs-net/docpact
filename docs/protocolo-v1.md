# Protocolo CONTRATO v1 — Especificación

> **Versión:** 1.0
> **Schema:** `docs/schema/contrato-v1.json`
> **Estado:** Estable

---

## ¿Qué es un CONTRATO?

Un **CONTRATO** es un bloque estructurado dentro del docstring de una función
que declara, de forma verificable, lo que la función hace:

- **Qué recibe** (`input`)
- **Qué devuelve** (`output`)
- **Qué efectos produce** (`side_effects`)
- **Qué reglas de negocio implementa** (`rn`)
- **Qué casos borde maneja** (`borde`)
- **De qué depende** (`dependencias`)

A diferencia de un docstring narrativo, un CONTRATO es **parseable por máquina**
y **verificable estáticamente**. Un agente (o un humano) puede leerlo y saber
exactamente qué esperar de la función sin ejecutarla.

---

## Formato

El CONTRATO va dentro del docstring de la función, después de la descripción
narrativa (si existe). Usa indentación estilo YAML.

### Estructura general

```python
def mi_funcion(param1: str, param2: int) -> bool:
    """Descripción narrativa opcional.

    CONTRATO:
      input:
        param1: str — Descripción del parámetro
        param2: int — Descripción del parámetro
      output: bool — Descripción del retorno
      side_effects: ninguno
      rn:
        - RN-010: descripción de la regla
      borde:
        - param1 vacío: retorna False
      dependencias:
        - otro/modulo.py::OtraClase
    """
```

### Campos

| Campo | Obligatorio | Formato |
|-------|-------------|---------|
| `input` | No | Lista de `nombre: tipo — descripción` |
| `output` | No | `tipo — descripción` |
| `side_effects` | **Sí** | `ninguno` o lista separada por coma |
| `rn` | No | Lista de `- RN-XXX: descripción` |
| `borde` | No | Lista de `- condición: comportamiento` |
| `dependencias` | No | Lista de `- ruta/archivo.py::Simbolo` |

### side_effects

El campo más importante. Declara qué efectos secundarios produce la función
fuera de su retorno. Valores típicos:

```
side_effects: ninguno                              # sin efectos
side_effects: Crea ticket en BD, Envía email       # lista
side_effects: registra bitácora, sincroniza sesiones
```

El verificador (`docpact check`) camina el AST de la función y compara las
llamadas reales contra los patrones configurados en `docpact.toml`.

### rn (Reglas de Negocio)

Cada ID `RN-XXX` declarado debe aparecer como comentario `# RN-XXX` en el
cuerpo de la función. Esto permite verificar que la regla no solo se menciona
sino que efectivamente hay código que la implementa.

```python
def suspender(ticket, editor, motivo, data):
    """
    CONTRATO:
      rn:
        - RN-004: No se permite saltar entre estados
    """
    # RN-004: verificar transición permitida
    can_transition_to(ticket, Ticket.Estado.SUSPENDIDO)
```

### Indentación

El parser soporta **2 estilos** de indentación:

**Estilo A — campos al mismo nivel que `CONTRATO:`** (recomendado):

```python
    CONTRATO:
    input:
      param: type — desc
    side_effects: ninguno
```

**Estilo B — campos indentados +2**:

```python
    CONTRATO:
      input:
        param: type — desc
      side_effects: ninguno
```

Ambos estilos son equivalentes. El parser los detecta automáticamente.

---

## Ejemplos

### Python

```python
from dataclasses import dataclass


@dataclass
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

### TypeScript

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

### Go

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

## Verificación

El comando `docpact check` verifica:

| Verificación | Qué hace |
|-------------|----------|
| `side_effects` | Camina el AST, busca llamadas que coincidan con patrones de `docpact.toml` |
| `rn` | Extrae comentarios de la fuente, busca IDs RN-XXX |
| `dependencias` | Verifica que archivos y símbolos existan |
| `presencia` | (con `--strict`) Detecta funciones públicas sin CONTRATO |

### docpact.toml

```toml
[docpact]
strict = false
min_score = 75
exclude = ["tests/", "migrations/", "__pycache__/"]

[docpact.side_effects]
db_write = [".create", ".save", ".update", ".bulk_create", ".delete"]
email = ["send_mail", "EmailMessage"]

[docpact.rules]
rn_prefix = "RN-"
```

---

## Integración CI/CD

### GitHub Actions

```yaml
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

### Pre-commit

```yaml
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

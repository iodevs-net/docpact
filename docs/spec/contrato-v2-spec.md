# CONTRATO Format Specification v2.0.0

> **Spec Version:** 2.0.0
> **Status:** Stable
> **Schema:** `src/docpact/schema/contrato-v2.json`
> **Predecessor:** CONTRATO Protocol v1 (`docs/protocolo-v1.md`)
> **Effective since:** 2026-06-13

---

## 1. Introduction

A **CONTRATO** is a structured, machine-parseable block embedded in a function's docstring (or comment header) that declares the function's interface, side effects, business rules, edge cases, and dependencies. It is the core abstraction of docpact — a system that makes AI-generated code changes safe by verifying them against declared contracts.

Unlike narrative docstrings, a CONTRATO is **parseable by machine** and **verifiable statically**. An agent (or a human) can read it and know exactly what to expect from the function without executing it.

### 1.1 Design Goals

1. **Self-documenting**: every `.py` / `.ts` / `.go` file is both implementation and specification.
2. **Machine-verifiable**: side effects, RN markers, dependencies, and signatures are checked against real code.
3. **Agent-first**: optimized for LLM consumption — structured, unambiguous, minimal prose.
4. **Backward-compatible**: v2 extends v1 without breaking existing contracts.

### 1.2 Terminology

| Term | Definition |
|------|-----------|
| **CONTRATO** | The structured block itself, introduced by the `CONTRATO:` marker. |
| **Field** | A named section within the block (e.g., `side_effects`, `rn`). |
| **Compound field** | A field whose value is a list of sub-items (`input`, `rn`, `borde`, `dependencias`). |
| **Simple field** | A field whose value is inline text (`side_effects`, `output`, `comportamiento`, `asume`, `produce`). |
| **Semantic field** | Free-text fields that describe behavior in natural language (`comportamiento`, `asume`, `produce`). |
| **RN** | Regla de Negocio — a business rule identified by a stable `RN-XXX` ID. |
| **Marker** | A comment `# RN-XXX` in function body that links code to a declared RN. |
| **Side effect** | Any observable interaction a function has with the outside world beyond its return value. |

---

## 2. Grammar (BNF)

The following grammar defines the textual syntax of a CONTRATO block as it appears in source code. Whitespace rules follow the host language's indentation conventions.

### 2.1 Top-level Structure

```bnf
contrato-block    ::= contrato-header NEWLINE campo-list
contrato-header   ::= SPACES "CONTRATO" ":" [ version-tag ]
version-tag       ::= "v" DIGIT+ "." DIGIT+ "." DIGIT+

campo-list        ::= campo-entry ( NEWLINE campo-entry )*
campo-entry       ::= campo-compuesto | campo-simple

campo-compuesto   ::= campo-compuesto-name ":" NEWLINE sub-item-list
campo-compuesto-name ::= "input" | "rn" | "reglas" | "borde" | "dependencias"

campo-simple      ::= campo-simple-name ":" SPACING simple-value
campo-simple-name ::= "side_effects" | "output" | "comportamiento" | "asume" | "produce"

simple-value      ::= inline-value | yaml-block-scalar
inline-value      ::= ANY-TEXT-TO-EOL
yaml-block-scalar ::= "|" NEWLINE indented-line+
```

### 2.2 Compound Field Items

```bnf
sub-item-list     ::= sub-item ( NEWLINE sub-item )*
sub-item          ::= list-item | sub-campo

list-item         ::= SPACES "- " item-content
item-content      ::= ANY-TEXT-TO-EOL

sub-campo         ::= SPACES parameter-name ":" SPACING param-value
parameter-name    ::= IDENTIFIER
param-value       ::= type-desc | type-only
type-desc         ::= type SPACING "—" SPACING description
type              ::= ANY-BEFORE-EM-DASH
description       ::= ANY-TEXT-TO-EOL
```

### 2.3 Terminal Patterns

```bnf
IDENTIFIER        ::= ( ALPHA | "_" ) ( ALPHANUM | "_" )*
RN-ID             ::= "RN-" DIGIT{3,}
DEP-REF           ::= module-path [ "::" symbol ]
module-path       ::= IDENTIFIER ( "/" IDENTIFIER )* ( "." extension )?
symbol            ::= IDENTIFIER ( "." IDENTIFIER )*
extension         ::= "py" | "ts" | "js" | "go" | IDENTIFIER
NEWLINE           ::= "\n" | "\r\n"
SPACES            ::= " " { " " }
SPACING           ::= " "*  (at least one space or tab)
ALPHA             ::= "a"-"z" | "A"-"Z"
DIGIT             ::= "0"-"9"
ALPHANUM          ::= ALPHA | DIGIT
ANY-TEXT-TO-EOL   ::= { ANY-CHAR - NEWLINE }
```

### 2.4 Semantic Tokens

For implementors, the lexer produces these token types:

| Token | Meaning | Example |
|-------|---------|---------|
| `MARCA_CONTRATO` | The `CONTRATO:` header line | `CONTRATO:` |
| `CAMPO_COMPUESTO` | A field with list children | `input:` |
| `CAMPO_SIMPLE` | A field with inline value | `side_effects: ninguno` |
| `ITEM_LISTA` | A `- item` under a compound field | `- RN-010: desc` |
| `SUB_CAMPO` | A `key: value` under a compound field | `param: type — desc` |
| `TEXTO_LIBRE` | Unrecognized text (tolerated, not parsed) | stray text |

---

## 3. Fields Reference

### 3.1 Field Inventory

| Field | Type | Required | Cardinality | Since |
|-------|------|----------|-------------|-------|
| `side_effects` | simple | **Yes** | single value | v1 |
| `output` | simple | No | single value | v1 |
| `input` | compound | No | map of `CampoInput` | v1 |
| `rn` | compound | No | list of `ReglaNegocio` | v1 |
| `reglas` | compound | No | alias for `rn` | v1 |
| `borde` | compound | No | list of `CasoBorde` | v1 |
| `dependencias` | compound | No | list of `Dependencia` | v1 |
| `comportamiento` | simple | No | single text value | v2 |
| `asume` | simple | No | single text value | v2 |
| `produce` | simple | No | single text value | v2 |

### 3.2 Field Definitions

#### 3.2.1 `side_effects` (REQUIRED)

Declares what observable side effects the function produces beyond its return value. This is the **most important field** — the only one that is required.

**Syntax:**

```
side_effects: ninguno
side_effects: Crea ticket en BD, Envía email
side_effects: Registra bitácora, Sincroniza sesiones
```

**Rules:**

- MUST be present in every CONTRATO.
- Value `"ninguno"` (case-insensitive) declares a pure function with no side effects.
- Otherwise, value is a comma-separated list of side effect descriptions.
- Each description MUST be at least 2 characters long.
- Commas inside parentheses are NOT separators (see §4.3).
- The verifier (`docpact check`) walks the function's AST and compares real calls against patterns configured in `docpact.toml`.

**Parsed representation:**

```python
# "ninguno" → empty list
side_effects: list[SideEffect] = []

# "Crea ticket, Envía email" → two items
side_effects: list[SideEffect] = [
    SideEffect(descripcion="Crea ticket"),
    SideEffect(descripcion="Envía email"),
]
```

#### 3.2.2 `output` (optional)

Declares the function's return type and optional description.

**Syntax:**

```
output: bool
output: HorasCalculadas — Total de horas y segundos
```

**Rules:**

- If the em-dash ` — ` separator is present, text before it is the type, text after is the description.
- If absent, the entire value is the type, description is empty string.
- The type is informational — docpact does not enforce it at runtime, but it is available for agent consumption.

**Parsed representation:**

```python
output: str | None = None          # type, or None if field absent
output_descripcion: str = ""       # description text
```

#### 3.2.3 `input` (optional)

Declares function parameters with types and descriptions.

**Syntax (compound — one parameter per line):**

```
input:
  param1: str — Descripción del parámetro
  param2: int
  tickets: list[Ticket] — Tickets con sesiones precargadas
```

**Rules:**

- Each sub-line has format: `name: type` or `name: type — description`.
- Parameter names MUST match the function's actual signature (verified by `docpact check`).
- `self` and `cls` are automatically excluded from verification.
- `*args` and `**kwargs` MAY be declared. Combined `*args, **kwargs: dict — desc` on one line is supported.
- Virtual params extracted from `kwargs.pop("x")` / `kwargs.get("x")` in the body are also matched.
- If a declared parameter does not appear in the real signature, an error is raised.
- If a real parameter is not declared in the CONTRATO, a warning is raised.
- Type MUST be non-empty (validated). Empty types are an error unless in the `types_allowlist`.

**Parsed representation:**

```python
input: dict[str, CampoInput] = {
    "param1": CampoInput(nombre="param1", tipo="str", descripcion="Descripción del parámetro"),
    "param2": CampoInput(nombre="param2", tipo="int", descripcion=""),
}
```

#### 3.2.4 `rn` / `reglas` (optional)

Declares which business rules (Reglas de Negocio) this function implements.

**Syntax (compound — list items):**

```
rn:
  - RN-010: solo administradores pueden resolver
  - RN-042: validar plazo máximo de 72 horas
```

**Alternative syntax (JSON inline array on simple field):**

```
rn: [RN-010, RN-042]
```

**Rules:**

- Each ID MUST match the pattern `RN-\d{3,}` (the prefix `RN-` followed by 3 or more digits).
- Each RN declared MUST appear as a comment `# RN-XXX` in the function's body (verified by `docpact check`).
- The `reglas` field name is an alias for `rn`; both are equivalent.
- Description after the colon is optional.
- Placeholder IDs (`RN-XXX`, `RN-TBD`, `RN-WIP`, `RN-NO-APLICA`) are recognized and excluded from statistics.

**Parsed representation:**

```python
rn: list[ReglaNegocio] = [
    ReglaNegocio(id="RN-010", descripcion="solo administradores pueden resolver"),
    ReglaNegocio(id="RN-042", descripcion="validar plazo máximo de 72 horas"),
]
```

#### 3.2.5 `borde` (optional)

Documents edge cases with their expected behavior.

**Syntax (compound — list items):**

```
borde:
  - tickets vacío: retorna HorasCalculadas(0, 0)
  - sesión sin fin: se ignora
```

**Alternative syntax (sub-campo style):**

```
borde:
  tickets vacío: retorna HorasCalculadas(0, 0)
  sesión sin fin: se ignora
```

**Rules:**

- Each item MUST contain a colon separating condition from behavior.
- Items without a colon produce a parse error.
- Condition and behavior are free-text strings.

**Parsed representation:**

```python
borde: list[CasoBorde] = [
    CasoBorde(condicion="tickets vacío", comportamiento="retorna HorasCalculadas(0, 0)"),
    CasoBorde(condicion="sesión sin fin", comportamiento="se ignora"),
]
```

#### 3.2.6 `dependencias` (optional)

Declares external modules and symbols this function depends on.

**Syntax (compound — list items):**

```
dependencias:
  - soporte/models/ticket.py::Ticket
  - soporte/services/horas.py::sumar_sesiones
  - src/utils/validators
```

**Alternative syntax (JSON inline array):**

```
dependencias: ["soporte/models/ticket.py::Ticket"]
```

**Rules:**

- Format: `path/to/file.ext` or `path/to/file.ext::SymbolName`.
- Paths are relative to the project root.
- Path traversal (`..`) is **forbidden** — produces an error.
- The verifier checks that the file exists and (if `::Symbol` is present) that the symbol is defined in that file.
- Allowed characters: `[a-zA-Z0-9_/.-]` for the path part; `[a-zA-Z_][a-zA-Z0-9_.]*` for the symbol.
- The `::` separator is optional — bare paths declare a module dependency without a specific symbol.

**Parsed representation:**

```python
dependencias: list[Dependencia] = [
    Dependencia(ref="soporte/models/ticket.py::Ticket"),
]
```

#### 3.2.7 `comportamiento` (optional, v2)

Free-text description of what the function does, in natural language. Helps agents understand behavior without reading the function body.

**Syntax:**

```
comportamiento: Calcula el total de horas trabajadas sumando sesiones completadas
```

**Multi-line (YAML block scalar):**

```
comportamiento: |
  Calcula el total de horas trabajadas sumando las sesiones
  completadas de cada ticket. Ignora sesiones sin fecha de fin.
```

**Rules:**

- Free text, no structural constraints.
- Multi-line values use the YAML `|` indicator; subsequent indented lines are joined with spaces.
- If the value is empty or just `|`, the field is treated as absent (`None`).

#### 3.2.8 `asume` (optional, v2)

Declares preconditions the function expects.

**Syntax:**

```
asume: usuario autenticado y con permisos de admin
```

**Multi-line:**

```
asume: |
  El ticket existe y está en estado ABIERTO.
  El usuario tiene permisos de supervisor.
```

**Rules:**

- Same format and parsing rules as `comportamiento` (§3.2.7).
- Free text describing what must be true before calling the function.

#### 3.2.9 `produce` (optional, v2)

Describes specific changes the function makes to the system state. More specific than `side_effects` — focuses on the *what* rather than the *category*.

**Syntax:**

```
produce: Actualiza ticket.estado a SUSPENDIDO y agrega entrada en historial
```

**Multi-line:**

```
produce: |
  Crea un nuevo registro en la tabla soporte_ticket.
  Envía notificación por email al técnico asignado.
  Actualiza el contador de tickets abiertos en el dashboard.
```

**Rules:**

- Same format and parsing rules as `comportamiento` (§3.2.7).
- Free text describing concrete state mutations.

---

## 4. Parsing Rules

### 4.1 Block Detection

A CONTRATO block begins at any line containing the literal text `CONTRATO:` (with optional surrounding whitespace). The block continues until:

1. A line with indentation equal to or less than the `CONTRATO:` line and containing non-whitespace content that is NOT a field, OR
2. The end of the docstring/comment block.

The parser supports two indentation styles:

**Style A — Fields at same level as `CONTRATO:` (recommended):**

```python
CONTRATO:
input:
  param: type — desc
side_effects: ninguno
```

**Style B — Fields indented +2 from `CONTRATO:`:**

```python
CONTRATO:
  input:
    param: type — desc
  side_effects: ninguno
```

Both styles are equivalent. The parser auto-detects by examining the first non-empty line after `CONTRATO:`.

### 4.2 Root Field Classification

The following strings are recognized as root field names (case-insensitive):

```
input, output, side_effects, rn, reglas, borde, dependencias,
comportamiento, asume, produce
```

A line is classified as a root field if its stripped form starts with one of these names followed by `:`.

### 4.3 Comma Splitting (Parenthesis-Aware)

When `side_effects` values are split by commas, commas inside parentheses are **not** treated as separators:

```
# Input:
side_effects: subprocess (docker info, hostname, uname), http get a netdata

# Parsed as 2 items, NOT 4:
#   1. "subprocess (docker info, hostname, uname)"
#   2. "http get a netdata"
```

**Algorithm:**

1. Track parenthesis nesting level (starts at 0).
2. Track whether inside a string literal (`"` or `'`).
3. A comma at nesting level 0, outside a string, is a separator.
4. All other commas are literal characters.

### 4.4 JSON Inline Arrays

Compound fields (`rn`, `borde`, `dependencias`) also accept a JSON array syntax on a single line:

```
rn: [RN-010, RN-042]
dependencias: ["soporte/models/ticket.py::Ticket"]
```

If the value starts with `[` and ends with `]`, the parser:

1. Attempts `json.loads()`.
2. On failure, falls back to stripping brackets and splitting by comma.

### 4.5 Inline Comments

Trailing Python comments (`# ...`) after field values are stripped before parsing:

```
rn: [RN-001]  # inherited from parent
#       ^^^^^^^^^^^^^^^^^^^^^^^^^ stripped
```

### 4.6 Language-Specific Embedding

CONTRATO blocks are embedded differently depending on the host language:

**Python** — inside docstrings:

```python
def my_function(param: str) -> bool:
    """Description.

    CONTRATO:
      side_effects: ninguno
    """
```

**TypeScript/JavaScript** — inside `//` or `/** */` comments:

```typescript
// CONTRATO:
//   side_effects: ninguno
//   rn:
//     - RN-010: rule description

/**
 * CONTRATO:
 *   side_effects: ninguno
 */
```

**Go** — inside `//` comments:

```go
// CONTRATO:
//   side_effects: ninguno
//   rn:
//     - RN-010: rule description
```

### 4.7 YAML Block Scalars (Multi-line Text)

Semantic fields (`comportamiento`, `asume`, `produce`) support multi-line text via the YAML block scalar indicator `|`:

```
comportamiento: |
  First line of description.
  Second line continues here.
  Third line.
```

**Parsing rules:**

1. The line ending with `:` then `|` triggers block scalar mode.
2. All subsequent lines with indentation **greater than** the root field level are captured.
3. Captured lines are stripped and joined with spaces.
4. The first line at or below root indentation ends the block.

---

## 5. Verification Rules

docpact performs static analysis on CONTRATO blocks against the actual source code. The following table summarizes all checks:

| Check | Field(s) | What It Verifies | Severity |
|-------|----------|------------------|----------|
| **side_effects** | `side_effects` | AST walk finds real calls; compares against declared effects | error |
| **rn markers** | `rn` | Each `RN-XXX` ID appears as `# RN-XXX` comment in function body | error |
| **signature** | `input` | Declared params match real function signature | error/warning |
| **dependencies** | `dependencias` | Referenced files and symbols exist on disk | error |
| **imports** | `dependencias` | Inline imports don't duplicate declared deps | warning |
| **marker honesty** | `rn` | `# RN-XXX` markers are not on delegation-only lines | warning |
| **rn registry** | `rn` | Declared RNs exist in `REGISTRO.md` | error |
| **rn tests** | `rn` | Each `RN-XXX` has a corresponding test file | warning |
| **transitive effects** | `side_effects` | Called functions' declared effects are accounted for | warning |
| **boundary** | `dependencias` | Dependencies respect module boundary rules from `modules.toml` | error |

### 5.1 Validation Rules (Structural)

These rules apply to the parsed `Contrato` model regardless of source code:

| Rule | Field | Constraint | Error |
|------|-------|------------|-------|
| SE-1 | `side_effects` | MUST be present | Missing `side_effects` field |
| SE-2 | `side_effects` | Each description length ≥ 2 | Side effect description too short |
| RN-1 | `rn` | Each ID matches `^RN-\d{3,}$` | Invalid RN ID format |
| IN-1 | `input` | Each parameter has non-empty type (unless in allowlist) | Input without declared type |
| DE-1 | `dependencias` | Each ref matches `^[a-zA-Z0-9_/.-]+(::[a-zA-Z_][a-zA-Z0-9_.]*)?$` | Invalid dependency format |
| DE-2 | `dependencias` | Refs MUST NOT contain `..` | Path traversal forbidden |
| BD-1 | `borde` | Each item MUST contain `:` separator | Edge case without separator |

### 5.2 Signature Matching

The `input` field is verified against the function's actual AST:

- `self` / `cls` parameters are automatically excluded.
- `*args` and `**kwargs` are matched by name.
- Virtual parameters extracted from `kwargs.pop("x")` or `kwargs.get("x")` calls in the body are also recognized.
- A declared parameter not in the real signature → **error**.
- A real parameter not in the CONTRATO → **warning**.

### 5.3 Marker Honesty

When a `# RN-XXX` comment appears on a line that **only** delegates to another service (e.g., `return Service.method(args)`), the marker is flagged as potentially "decorative" — the function may not actually implement the rule itself.

Detection heuristics:

- `return Service.method(...)` where `Service` is external
- `x = Service.method(...)` with no other logic on the line
- Object field assignments (`self.x = value`) with no conditional logic

This check emits a **warning**, not an error — delegation can be a valid implementation pattern.

### 5.4 RN Traceability

Each `RN-XXX` declared in a CONTRATO is cross-referenced against:

1. **REGISTRO.md** — the canonical business rule registry in `docs/reglas-del-negocio/`.
2. **Test files** — `tests/rn/test_rn_XXX.py` for each declared RN.
3. **Source markers** — `# RN-XXX` comments in the function body.

The traceability matrix produces four statuses:

| Status | Declared in CONTRATO | In REGISTRO.md | Has Tests | Has Markers |
|--------|---------------------|----------------|-----------|-------------|
| `FULL` | Yes | Yes | Yes | Yes |
| `DECLARED_ONLY` | Yes | Yes | No | Yes |
| `TEST_ONLY` | No | Yes | Yes | N/A |
| `ORPHAN` | No | Yes | No | N/A |

---

## 6. Data Model

### 6.1 Core Dataclasses

```python
@dataclass(frozen=True)
class CampoInput:
    nombre: str          # parameter name
    tipo: str            # type hint (free text)
    descripcion: str = ""  # optional description

@dataclass(frozen=True)
class SideEffect:
    descripcion: str     # side effect description (≥ 2 chars)

@dataclass(frozen=True)
class ReglaNegocio:
    id: str              # e.g. "RN-010"
    descripcion: str = ""  # optional description

@dataclass(frozen=True)
class CasoBorde:
    condicion: str       # edge case condition
    comportamiento: str  # expected behavior

@dataclass(frozen=True)
class Dependencia:
    ref: str             # e.g. "soporte/models/ticket.py::Ticket"

@dataclass(frozen=True)
class Contrato:
    input: dict[str, CampoInput] = field(default_factory=dict)
    output: Optional[str] = None
    output_descripcion: str = ""
    side_effects: list[SideEffect] = field(default_factory=list)
    rn: list[ReglaNegocio] = field(default_factory=list)
    borde: list[CasoBorde] = field(default_factory=list)
    dependencias: list[Dependencia] = field(default_factory=list)
    # Semantic fields (all optional, backward-compatible with v1)
    comportamiento: Optional[str] = None
    asume: Optional[str] = None
    produce: Optional[str] = None

@dataclass(frozen=True)
class ErrorParser:
    campo: str           # field name, or "general"
    mensaje: str         # error message
    linea: int = 0       # source line number (0 = unknown)
    sugerencia: str = "" # fix suggestion

class TipoFuncion(Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
```

### 6.2 Extraction Result

```python
@dataclass(frozen=True)
class ContratoExtraido:
    funcion: str              # function name
    tipo: TipoFuncion         # function, method, or class
    archivo: str              # source file path
    linea: int                # line number of the CONTRATO header
    contrato: Contrato        # parsed contract
    raw_text: str             # original block text
    errores: list[ErrorParser] = field(default_factory=list)
```

---

## 7. Examples

### 7.1 Minimal Contract

The smallest valid CONTRATO — only the required field:

```python
def get_user_name(user_id: int) -> str:
    """Returns the user's display name.

    CONTRATO:
      side_effects: ninguno
    """
    return db.query(User).get(user_id).name
```

### 7.2 Full Contract (All Fields)

```python
def sumar_sesiones(tickets: list) -> HorasCalculadas:
    """Calcula horas totales de sesiones de trabajo.

    CONTRATO:
      comportamiento: |
        Calcula el total de horas trabajadas sumando las sesiones
        completadas de cada ticket. Ignora sesiones sin fecha de fin.
      asume: tickets con sesiones precargadas (no lazy-loaded)
      produce: nada — función pura, solo calcula
      input:
        tickets: list[Ticket] — Tickets con sesiones precargadas.
      output: HorasCalculadas — Total de horas y segundos.
      side_effects: ninguno
      rn:
        - RN-002: solo sesiones completadas descuentan horas
        - RN-015: sesiones menores a 5 minutos no cuentan
      borde:
        - tickets vacío: retorna HorasCalculadas(0, 0)
        - sesión sin fin: se ignora
        - sesión menor a 5 minutos: se descarta (RN-015)
      dependencias:
        - soporte/models/ticket.py::Ticket
    """
    total = 0
    for ticket in (tickets or []):
        for sesion in getattr(ticket, 'sesiones', []):
            if sesion.get('fin'):  # RN-002
                duracion = (sesion['fin'] - sesion['inicio']).total_seconds()
                if duracion >= 300:  # RN-015
                    total += duracion
    return HorasCalculadas(total_horas=total / 3600, total_segundos=int(total))
```

### 7.3 Delegation Contract

A function that delegates side effects to a service:

```python
def suspender_ticket(ticket_id: int, editor: User, motivo: str, data: dict) -> Ticket:
    """Suspende un ticket con motivo obligatorio.

    CONTRATO:
      input:
        ticket_id: int — ID del ticket a suspender
        editor: User — Usuario que realiza la suspensión
        motivo: str — Motivo obligatorio de la suspensión
        data: dict — Datos adicionales para el historial
      output: Ticket — Ticket actualizado en estado SUSPENDIDO
      side_effects: Actualiza ticket en BD, Registra en historial, Envía notificación
      rn:
        - RN-004: No se permite saltar entre estados
        - RN-009: Toda suspensión requiere motivo
      borde:
        - ticket no existe: levanta TicketNotFoundError
        - motivo vacío: levanta ValueError
        - ticket ya suspendido: retorna sin cambios
      dependencias:
        - soporte/models/ticket.py::Ticket
        - soporte/services/transiciones.py::puede_transicionar
    """
    # RN-009: validar motivo obligatorio
    if not motivo:
        raise ValueError("Motivo de suspensión es obligatorio")

    ticket = Ticket.objects.get(id=ticket_id)  # puede lanzar TicketNotFoundError

    # RN-004: verificar transición permitida
    puede_transicionar(ticket, Ticket.Estado.SUSPENDIDO)

    ticket.estado = Ticket.Estado.SUSPENDIDO
    ticket.save()
    registrar_historial(ticket, editor, motivo, data)  # delegación al servicio
    notificar_cambio_estado(ticket)
    return ticket
```

### 7.4 Contract with Side Effects (Non-trivial)

```python
def procesar_pago(order_id: str, monto: float) -> PagoResult:
    """Procesa un pago contra la pasarela de cobro.

    CONTRATO:
      input:
        order_id: str — ID de la orden a pagar
        monto: float — Monto en la moneda base
      output: PagoResult — Resultado con estado y referencia
      side_effects: Llama API de cobro externa, Actualiza orden en BD, Envía email de confirmación
      rn:
        - RN-020: monto debe ser mayor a cero
        - RN-021: no permitir doble cobro
      borde:
        - monto <= 0: levanta ValueError
        - orden ya pagada: retorna estado DUPLICATE
        - timeout de pasarela: reintenta 3 veces
      dependencias:
        - pagos/gateway.py::CobroGateway
        - ordenes/models.py::Orden
    """
    if monto <= 0:  # RN-020
        raise ValueError("Monto debe ser mayor a cero")

    orden = Orden.objects.get(id=order_id)
    if orden.pagada:  # RN-021
        return PagoResult(estado="DUPLICATE", referencia=orden.pago_ref)

    resultado = CobroGateway.cobrar(order_id, monto)  # API externa
    orden.marcar_pagada(resultado.referencia)
    enviar_email_confirmacion(orden)
    return PagoResult(estado=resultado.estado, referencia=resultado.referencia)
```

### 7.5 TypeScript Example

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
 *   borde:
 *     - mes inválido: levanta Error
 *     - contrato sin sesiones: retorna 0
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

### 7.6 Go Example

```go
// CONTRATO:
//   input:
//     ticketID: int64 — ID del ticket
//     userID: int64 — ID del usuario
//   output: *Ticket — Ticket resuelto
//   side_effects: Actualiza estado, Registra bitácora, Envía notificación
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

### 7.7 Inline JSON Array (Compact)

```python
def validar_email(email: str) -> bool:
    """Valida formato de email.

    CONTRATO:
      side_effects: ninguno
      rn: [RN-030, RN-031]
    """
    # RN-030: verificar formato básico
    # RN-031: rechazar dominios bloqueados
    return _validar_formato(email) and _verificar_dominio(email)
```

---

## 8. Edge Cases

### 8.1 Empty Block

A `CONTRATO:` header with no fields produces a `Contrato()` with defaults and a parse error:

```
CONTRATO:
```

**Result:** Empty `Contrato` with warning `"No se encontró bloque CONTRATO en el docstring"`.

### 8.2 Missing side_effects

If `side_effects` is absent, the parser produces a `Contrato` with an empty `side_effects` list. The validator flags this as an error.

### 8.3 Duplicate Fields

If a field appears multiple times, the parser accumulates values:

- `input`: last declaration of a parameter name wins (dict merge).
- `rn`, `borde`, `dependencias`: lists are extended (items accumulate).
- `side_effects`, `output`, `comportamiento`, `asume`, `produce`: last value wins.

### 8.4 `side_effects: ninguno` vs Empty List

```
side_effects: ninguno     →  side_effects: []  (explicitly no effects)
# (absent)                →  side_effects: []  (missing — validation error)
```

Both produce an empty list, but the absence triggers a validation error while explicit `ninguno` is valid.

### 8.5 Parenthesized Commas in side_effects

```
side_effects: subprocess (docker info, hostname, uname), http get
```

Parsed as 2 items (not 4): `"subprocess (docker info, hostname, uname)"` and `"http get"`.

### 8.6 Nested Parentheses

The parenthesis-aware split tracks nesting depth:

```
side_effects: f (a, g(b, c)), h
```

Parsed as 2 items: `"f (a, g(b, c))"` and `"h"`.

### 8.7 RN Placeholders

The following RN IDs are treated as placeholders and excluded from statistics:

```
RN-XXX, RN-TBD, RN-WIP, RN-NO-APLICA
```

They are recognized by pattern `^RN-(?:XXX|NO-APLICA|TBD|WIP)$` (case-insensitive).

### 8.8 Empty Semantic Fields

```
comportamiento:
comportamiento: |
```

Both produce `None` — an empty semantic field is treated as absent.

### 8.9 Mixed Indentation

The parser auto-detects the indentation level from the first content line after `CONTRATO:`. Mixing styles within a single block is not supported and produces parse errors.

### 8.10 `reglas` as Alias for `rn`

```
reglas:
  - RN-010: descripción
```

This is equivalent to `rn:` with the same content. Both field names are recognized.

### 8.11 Trailing Comments

```
rn: [RN-001]  # inherited from parent class
```

The `# inherited from parent class` is stripped before parsing. The effective value is `[RN-001]`.

### 8.12 `*args` / `**kwargs` Combined Declaration

```
input:
  *args, **kwargs: positional and keyword arguments
```

The parser splits by comma, strips `*` prefixes, and creates separate `CampoInput` entries for `args` (default type `tuple`) and `kwargs` (default type `dict`).

### 8.13 borde Without Colon

```
borde:
  - tickets vacío retorna cero
```

Produces a parse error: `"Caso borde sin ':' separador"`. The colon is mandatory.

---

## 9. JSON Schema

The canonical JSON Schema for the Contrato data model (for programmatic validation and MCP serialization):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://docpact.dev/schemas/contrato-v2.json",
  "title": "CONTRATO v2 — Protocolo de verificación de código para agentes de IA",
  "type": "object",
  "properties": {
    "comportamiento": {
      "type": "string",
      "description": "Descripción en lenguaje natural de qué hace la función."
    },
    "asume": {
      "type": "string",
      "description": "Precondiciones que el código espera."
    },
    "produce": {
      "type": "string",
      "description": "Cambios específicos en BD/sistema."
    },
    "input": {
      "type": "object",
      "description": "Parámetros de entrada. Cada clave es el nombre del parámetro.",
      "patternProperties": {
        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
          "type": "object",
          "properties": {
            "type": { "type": "string" },
            "description": { "type": "string" }
          },
          "required": ["type"],
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },
    "output": {
      "type": "object",
      "description": "Valor de retorno de la función.",
      "properties": {
        "type": { "type": "string" },
        "description": { "type": "string" }
      },
      "required": ["type"],
      "additionalProperties": false
    },
    "side_effects": {
      "description": "Efectos secundarios. 'ninguno' cuando no hay efectos.",
      "oneOf": [
        { "type": "string", "pattern": "^ninguno$" },
        { "type": "string", "minLength": 1 }
      ]
    },
    "rn": {
      "type": "array",
      "description": "Reglas de negocio implementadas por esta función.",
      "items": {
        "oneOf": [
          { "type": "string", "pattern": "^RN-[0-9]{3,}$" },
          {
            "type": "object",
            "properties": {
              "id": { "type": "string", "pattern": "^RN-[0-9]{3,}$" },
              "description": { "type": "string" }
            },
            "required": ["id"],
            "additionalProperties": false
          }
        ]
      }
    },
    "borde": {
      "type": "array",
      "description": "Casos borde documentados.",
      "items": {
        "type": "object",
        "properties": {
          "condicion": { "type": "string" },
          "comportamiento": { "type": "string" }
        },
        "required": ["condicion", "comportamiento"],
        "additionalProperties": false
      }
    },
    "dependencias": {
      "type": "array",
      "description": "Referencias a módulos/símbolos externos.",
      "items": {
        "type": "string",
        "pattern": "^[a-zA-Z0-9_/.\\-]+(::[a-zA-Z_][a-zA-Z0-9_.]*)?$"
      }
    }
  },
  "required": ["side_effects"],
  "additionalProperties": false
}
```

---

## 10. Migration from v1

### 10.1 What Changed in v2

| Change | Type | Description |
|--------|------|-------------|
| Added `comportamiento` field | MINOR | Optional semantic field describing function behavior |
| Added `asume` field | MINOR | Optional semantic field for preconditions |
| Added `produce` field | MINOR | Optional semantic field for state changes |
| YAML block scalar support | MINOR | `comportamiento: \|` multi-line syntax |
| Version header support | MINOR | `CONTRATO:v2.0.0:` explicit version tag |

### 10.2 Backward Compatibility

**v1 contracts are valid v2 contracts without modification.** The three new fields (`comportamiento`, `asume`, `produce`) are optional. No existing field changed semantics or syntax.

A docpact installation supporting v2 continues to parse v1 blocks identically. The version tag is optional — blocks without it are parsed using the latest stable grammar.

### 10.3 Migration Steps

1. **No changes required.** Existing `CONTRATO:` blocks work as-is.
2. **Optional enrichment.** Add semantic fields to improve agent understanding:
   - `comportamiento` — what the function does (especially useful for complex functions)
   - `asume` — what the caller must ensure
   - `produce` — what state mutations occur
3. **Optional version tag.** Add `CONTRATO:v2.0.0:` to the header for explicit versioning.

### 10.4 Automated Migration

```bash
# Enrich existing contratos with semantic fields (AI-assisted)
docpact fix --enrich-semantic

# Add version tags to all contratos
docpact fix --add-version v2.0.0
```

### 10.5 Rollback

Semantic fields are ignored by v1 parsers. If you need to revert to a v1-only toolchain:

1. Remove `comportamiento`, `asume`, `produce` lines from CONTRATO blocks.
2. Remove `CONTRATO:v2.0.0:` version tags (replace with plain `CONTRATO:`).
3. No other changes needed — all other fields are unchanged.

### 10.6 Version Negotiation

When docpact encounters a `CONTRATO:` block:

1. If the header declares a version (e.g., `CONTRATO:v2.0.0:`), docpact uses the corresponding parser.
2. If no version is declared, docpact assumes the latest stable protocol version.
3. If the detected syntax is ambiguous, docpact falls back to v1 and emits a warning.

---

## 11. Configuration Interaction

CONTRATO verification behavior is configured via `docpact.toml`:

```toml
[docpact]
strict = false           # true = missing CONTRATO is an error
min_score = 75           # minimum project score to pass
exclude = ["tests/", "migrations/"]

[docpact.side_effects]
# Category → list of AST call patterns
db_write = [".create", ".save", ".update", ".bulk_create", ".delete"]
email = ["send_mail", "EmailMessage"]
external = ["requests.", "httpx.", "urllib.request"]

[docpact.rules]
rn_prefix = "RN-"        # prefix for RN ID detection

[docpact.marker_honesty]
enabled = true            # check for decorative markers
max_rns_per_function = 5  # warn if exceeded
```

Side effect patterns are matched as substring patterns against the AST representation of function calls. Categories are arbitrary — projects define their own taxonomy.

---

## 12. Conformance

### 12.1 Levels

| Level | Description |
|-------|-------------|
| **Core** | Parses `side_effects`, `output`, `input`, `rn`, `borde`, `dependencias`. |
| **Semantic** | Core + parses `comportamiento`, `asume`, `produce` with YAML block scalar support. |
| **Full** | Semantic + all verification checks + marker honesty + traceability. |

### 12.2 Minimum Conformance

A conforming implementation MUST:

1. Detect `CONTRATO:` blocks in the host language's comment/docstring syntax.
2. Parse the `side_effects` field (required).
3. Produce a structured representation with at least the `side_effects` field.
4. Reject blocks where `side_effects` is missing with an error.

A conforming implementation SHOULD:

5. Parse all v1 fields (`input`, `output`, `rn`, `borde`, `dependencias`).
6. Verify RN markers against function body comments.
7. Verify input parameters against the function signature.

A conforming implementation MAY:

8. Parse v2 semantic fields.
9. Perform all verification checks described in §5.
10. Support language-specific embedding (TypeScript, Go, etc.).

---

## Appendix A: Complete ABNF Token Reference

For implementors building lexers:

```
; Whitespace and structure
NEWLINE       = %x0A / %x0D.0A
SPACE         = %x20
TAB           = %x09
INDENT        = 1*SPACE

; Markers
CONTRATO-HDR  = *SPACE "CONTRATO" ":" [VERSION-TAG] *SPACE NEWLINE
VERSION-TAG   = "v" 1*DIGIT "." 1*DIGIT "." 1*DIGIT

; Field names (case-insensitive matching required)
COMPOUND-NAME = "input" / "rn" / "reglas" / "borde" / "dependencias"
SIMPLE-NAME   = "side_effects" / "output" / "comportamiento" / "asume" / "produce"
FIELD-NAME    = COMPOUND-NAME / SIMPLE-NAME

; Separators
EM-DASH       = " — "   ; U+2014 with surrounding spaces
COLON         = ":"
COMMA         = ","
LIST-MARKER   = "- "

; Identifiers
IDENTIFIER    = (ALPHA / "_") *(ALPHANUM / "_")
ALPHA         = %x41-5A / %x61-7A
DIGIT         = %x30-39
ALPHANUM      = ALPHA / DIGIT

; RN format
RN-ID         = "RN-" 3*DIGIT

; Dependency format
DEP-REF       = MODULE-PATH ["::" SYMBOL]
MODULE-PATH   = IDENTIFIER *("/" IDENTIFIER) ["." 1*(ALPHA / DIGIT)]
SYMBOL        = IDENTIFIER *("." IDENTIFIER)
```

---

## Appendix B: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 2.0.0 | 2026-06-13 | Added `comportamiento`, `asume`, `produce` semantic fields. Added YAML block scalar support. Added version header. Full formal spec with BNF grammar. |
| 1.0 | 2026-06-09 | Initial protocol. `side_effects`, `input`, `output`, `rn`, `borde`, `dependencias`. |

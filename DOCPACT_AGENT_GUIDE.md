# docpact Agent Guide

The definitive guide for AI agents using docpact to verify business rules in code.

---

## 1. What is docpact

docpact is a **type checker for business rules**. It verifies that your code actually implements the business rules you declared in structured docstring blocks called **CONTRATOs**.

It does not replace your linter, type checker, or test runner. It fills the gap none of them cover: **verifying that declared business rules are actually implemented in code**.

**How it works:**
1. You write a function and add a `CONTRATO:` block to its docstring declaring what it does, its side effects, and which business rules (RNs) it implements.
2. docpact parses those declarations and checks them against the actual code using AST analysis.
3. It verifies side effects match, business rule patterns exist in the source, and tests cover the rules.

**Key concepts:**
- **CONTRATO** — A structured docstring block that declares a function's business contract (inputs, outputs, side effects, RNs).
- **RN (Regla de Negocio)** — A business rule identified by an ID (e.g., `RN-008`, `RN-FAC-003`).
- **Side effects** — What the function does beyond returning a value: `db_write`, `email`, `file_write`, `http_call`, `service_delegation`, or `ninguno`.
- **Hallazgo** — A finding from verification (error or warning).

---

## 2. Quick Start (3 Commands)

Run these three commands after writing or modifying code. In order.

```bash
# Step 1: Validate your changes — checks contracts, side effects, transitive effects
docpact check .

# Step 2: Verify business rules are implemented in code
docpact verify-rn --project-root .

# Step 3: Check coverage — which RNs are declared, implemented, and tested
docpact traceability --project-root .
```

If all three pass, your changes are contractually sound. If any fail, see **Troubleshooting**.

---

## 3. MCP Tools Reference

docpact exposes 18 MCP tools for agent integration. Use these when connected via MCP.

### Discovery & Context

#### `obtener_contexto_funcion`
Get the complete context of a function: its CONTRATO, RNs, tests, file, and line number. Use this before editing a function.

```
Parameters:
  nombre_funcion (required) — Function name (partial or full). Example: "crear_ticket"

Returns: {
  existe: true,
  multiples: [{ archivo, linea, contrato, rns, tiene_test, test_archivo }]
}
```

**When to use:** Before modifying any function. Understand what it declares before you change it.

---

#### `buscar_por_intencion`
Search for functions by natural language intent. Uses semantic search (with FastEmbed) or keyword fallback.

```
Parameters:
  intencion (required) — What you're looking for. Example: "validar RUT de cliente"

Returns: { resultados: [{ funcion, archivo, score, contrato_resumen }], total }
```

**When to use:** You don't know the function name. Describe what you need.

---

#### `navegar_referencias`
Navigate cross-references. Pass an RN to find implementing functions, a file to list its functions, or a function to see what it calls.

```
Parameters:
  referencia (required) — RN ID ("RN-TKT-001"), file path ("soporte/views/portal.py"), or function name ("crear_ticket")

Returns: { tipo, relacionados: [...] }
```

**When to use:** Understanding call chains, finding all code that implements a rule, or mapping a file's responsibilities.

---

#### `obtener_briefing`
Get the project's business rules briefing. Read this before starting any coding session.

```
Parameters: none

Returns: { rns_activas, side_effects, zonas_riesgo, resumen }
```

**When to use:** At the start of a session. Understand the project's rules before writing code.

---

#### `listar_rns`
List all RNs in the project with their descriptions, implementing functions, and status.

```
Parameters: none

Returns: { total, rns: [{ rn_id, descripcion, funciones, tiene_test }] }
```

**When to use:** When asked "what rules exist?" or when you need the full picture.

---

### RN Management

#### `obtener_rn`
Get the complete context of a specific RN: description, implementing functions, test, and status.

```
Parameters:
  rn_id (required) — RN ID. Example: "RN-TKT-001"

Returns: { existe: true, rn_id, descripcion, funciones, tiene_test, test_archivo }
```

---

#### `buscar_rns_por_tema`
Search RNs by topic or keyword. Combines semantic and keyword search.

```
Parameters:
  tema (required) — Topic or keyword. Example: "facturación"

Returns: { rns: [{ rn_id, descripcion, score }], total }
```

---

#### `verificar_conflicto`
Check if a new RN would conflict with existing ones. Detects duplicates, overrides, and concept clashes. **ALWAYS use before creating a new RN.**

```
Parameters:
  rn_descripcion (required) — Description of the RN you want to create.

Returns: { conflictos: [...], duplicados: [...], recomendacion }
```

---

#### `crear_rn`
Create a new RN in REGISTRO.md. Must verify conflicts first. Must get user confirmation before calling.

```
Parameters:
  rn_id (required) — Format: RN-[CATEGORY]-[NUMBER]. Example: "RN-TKT-001"
  descripcion (required) — Clear description of the rule.
  archivo_registro (optional) — Path to REGISTRO.md. Default: "docs/reglas-del-negocio/REGISTRO.md"

Returns: { creado: true, rn_id, archivo }
```

---

#### `explicar_rn`
Explain an RN in plain language for non-technical stakeholders. Translates technical details into natural language.

```
Parameters:
  rn_id (required) — RN ID to explain.

Returns: { rn_id, lenguaje_simple, implementada_por, verificada, estado }
```

---

### Validation & Enforcement

#### `validar_cambio`
Validate a diff and run relevant tests before commit. This is **ENFORCEMENT** — if tests fail, the change is INVALID. The agent must not commit until this passes.

```
Parameters:
  archivo (required) — Modified file path. Example: "soporte/views/portal.py"
  diff (required) — The diff or changed lines.
  ejecutar_tests (optional, default: true) — Whether to run tests.

Returns: {
  valido: true/false,
  errores: [...],
  warnings: [...],
  test_results: [...],
  resumen: "APROBADO" or "BLOQUEADO: N error(s)..."
}
```

**When to use:** After every code change, before commit. This is the gate.

---

#### `modificar_archivo`
Validate a change against CONTRATOs before applying it. If the change violates side effects or RNs, it is REJECTED. **Use BEFORE modifying any file.**

```
Parameters:
  archivo (required) — File to modify.
  diff (required) — The diff or new code to apply.

Returns: { aprobado: true/false, violaciones: [...], sugerencias: [...] }
```

---

### Creation & Correction

#### `crear_contrato`
Generate a CONTRATO for a function from a natural language description. Returns a formatted docstring block to insert.

```
Parameters:
  archivo (required) — File path. Example: "src/tickets.py"
  funcion (required) — Function name. Example: "crear_ticket"
  side_effects (required) — Array of side effects. Example: ["db_write", "email_send"]
  rn (optional) — Array of RN IDs. Example: ["RN-TKT-001"]
  input_desc (optional) — Input description.
  output_desc (optional) — Output description.

Returns: { contrato: "CONTRATO:\n  input:\n    ..." }
```

---

#### `corregir_contrato`
Analyze a problematic CONTRATO and suggest a fix.

```
Parameters:
  archivo (required) — File path.
  funcion (required) — Function name.
  problema (required) — Detected problem. Example: "side_effects no coincide con implementación"

Returns: { problema, correccion_sugerida, diff_sugerido }
```

---

### Execution & Reporting

#### `ejecutar_verificacion`
Run full CONTRATO verification. Returns errors, warnings, and metrics.

```
Parameters:
  project_root (optional) — Project root directory.

Returns: { errores, warnings, metricas, resumen }
```

**Equivalent to:** `docpact check .`

---

#### `ejecutar_tests`
Run business rule tests with pytest. Returns pass/fail status.

```
Parameters:
  project_root (optional) — Project root directory.

Returns: { tests_passed, tests_failed, output }
```

**Equivalent to:** `docpact test .`

---

#### `generar_reporte`
Generate a business rules report: how many RNs exist, how many have code, how many have tests.

```
Parameters:
  project_root (optional) — Project root directory.

Returns: { total_rns, con_codigo, con_test, sin_codigo, sin_test }
```

**Equivalent to:** `docpact report .`

---

#### `setup_docpact`
Initialize docpact in a project: creates `docpact.toml`, docs directory, and generates `index.json`. Run once at project start.

```
Parameters:
  project_root (optional) — Project root directory.

Returns: { inicializado: true, archivos_creados: [...] }
```

---

## 4. Workflow

### Before Coding

1. **Read the briefing.** Call `obtener_briefing` or run `docpact check .` to understand the project's active rules, side effects, and risk zones.
2. **Understand the target function.** Call `obtener_contexto_funcion` on any function you plan to modify. Read its CONTRATO.
3. **Check for conflicts.** If adding a new RN, call `verificar_conflicto` first.
4. **Validate before modifying.** Call `modificar_archivo` with your planned changes to see if they violate existing contracts.

### During Coding

5. **Add CONTRATOs to new functions.** Every public function must have a `CONTRATO:` block. Use `crear_contrato` to generate one, or write it manually using the template:
   ```python
   def my_function(arg1, arg2):
       """Short description.

       CONTRATO:
         input:
           arg1: Type — Description
           arg2: Type — Description
         output: ReturnType — Description
         side_effects: db_write  # or: ninguno, email, file_write, http_call, service_delegation
         rn: [RN-XXX]
         borde:
           error_condition: ExceptionType
       """
   ```
6. **Keep side_effects honest.** If your function calls `Model.save()`, declare `db_write`. If it sends email, declare `email`. If it delegates to callees that handle side effects, use `service_delegation`.
7. **Use `service_delegation` wisely.** When a function orchestrates calls to other functions that have their own CONTRATOs, use `side_effects: service_delegation`. docpact will still verify callees have CONTRATOs.

### After Coding

8. **Validate your changes.** Run `docpact check .` or call `ejecutar_verificacion`. Fix all errors before proceeding.
9. **Verify business rules.** Run `docpact verify-rn --project-root .` or check via `validar_cambio`. Ensure all referenced RNs pass.
10. **Check traceability.** Run `docpact traceability --project-root .` or call `generar_reporte`. Ensure RNs show `FULL` status (declared + tested).
11. **Commit only when all three pass.**

---

## 5. Common Patterns

### Pattern: Service Delegation
When a function orchestrates calls to services that handle their own side effects:
```python
def process_order(order):
    """Process an order end-to-end.

    CONTRATO:
      input:
        order: Order — The order to process
      output: Order — Processed order
      side_effects: service_delegation
      rn: [RN-ORD-001]
    """
```

### Pattern: Pure Query (no side effects)
```python
def get_active_users(cliente_id):
    """Return active users for a client.

    CONTRATO:
      input:
        cliente_id: int — Client identifier
      output: QuerySet[Usuario] — Active users
      side_effects: ninguno
      rn: [RN-CL-002]
    """
```

### Pattern: Full Mutation (side effects + error cases)
```python
def crear_ticket(editor, cliente, titulo):
    """Create a support ticket.

    CONTRATO:
      input:
        editor: AbstractUser — User creating the ticket
        cliente: Cliente — Client associated
        titulo: str — Ticket title
      output: Ticket — Created ticket instance
      side_effects: db_write, email
      rn:
        - RN-001: Base ticket states
        - RN-FAC-003: Clients without contract can't create tickets
      borde:
        cliente_restringido: PermissionError
    """
```

### Pattern: Finding functions by intent
When you don't know the function name:
```
buscar_por_intencion("validar RUT de cliente")
```

### Pattern: Impact analysis before changing code
Before modifying a function, check what depends on it:
```
navegar_referencias("crear_ticket")  # See callers and callees
obtener_rn("RN-TKT-001")            # See what business rules it implements
```

---

## 6. Troubleshooting

### "Funciones sin CONTRATO"
**Meaning:** Public functions exist without a `CONTRATO` docstring block.
**Fix:** Add a `CONTRATO:` section to each flagged function. Use `docpact init . --batch` to auto-generate skeletons.

### "side_effects mismatch"
**Meaning:** A function declares `side_effects: ninguno` but calls code that writes to the database, sends emails, etc. Or vice versa.
**Fix:** Check what the function actually calls. Add the missing side effects. If it delegates to callees, use `service_delegation`.

### "ORDER_FAIL"
**Meaning:** A function checks a condition AFTER performing an action it should have blocked first (e.g., checking permissions after modifying the database).
**Fix:** Move the validation check BEFORE the operation it guards.

### "RN pattern not found"
**Meaning:** `verify-rn` can't find the code pattern for a business rule.
**Fix:** The RN is declared but not implemented. Add the actual code that implements the rule. Or add a pattern to `rn_verifier.py`.

### "RN no existe en REGISTRO.md"
**Meaning:** Your CONTRATO references an RN ID that doesn't exist in the registry.
**Fix:** Either remove the RN reference from your CONTRATO, or create the RN using `crear_rn` (after verifying conflicts).

### "Test FALLÓ"
**Meaning:** Your code change broke an existing RN test.
**Fix:** Read the test output. The test verifies a real business rule. Fix your code so the test passes. Do not modify the test to match broken code.

### "DECLARED_ONLY" in traceability
**Meaning:** An RN is declared in a CONTRATO but has no test.
**Fix:** Write a test in `tests/rn/test_rn_<ID>.py`.

### "TEST_ONLY" in traceability
**Meaning:** A test exists for an RN but no CONTRATO declares it.
**Fix:** Add the RN to the relevant function's CONTRATO.

### MCP server won't start / tools not loading
**Fix:** Run `docpact mcp-doctor` to diagnose. Ensure the index exists (`docpact index .`).

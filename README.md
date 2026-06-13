# docpact

**The type checker for business rules.**

docpact verifies that your code actually implements the business rules you declared. It doesn't replace your linter, type checker, or test runner — it fills the gap none of them cover.

```bash
pip install docpact
```

## Quick Start for Agents

Run these three commands after writing or modifying code. In order.

```bash
# Step 1: Validate your changes
docpact check .

# Step 2: Verify business rules are implemented
docpact verify-rn --project-root .

# Step 3: Check coverage
docpact traceability --project-root .
```

If all three pass, your changes are contractually sound. If any fail, see **Troubleshooting** below.

## Common Workflows

### I just wrote a new function

1. Add a `CONTRATO` block to the docstring (see **CONTRATO Template** below).
2. Run `docpact check .` — it must pass with zero errors.
3. Commit.

### I modified an existing function

1. Run `docpact check .` — it validates that the existing CONTRATO still matches the code.
2. If the function's behavior changed, update the CONTRATO fields (`side_effects`, `output`, `rn`).
3. Run `docpact check .` again.
4. Commit.

### I need to add a new business rule (RN)

1. Add a pattern to `rn_verifier.py` that proves the rule is implemented in code.
2. Run `docpact verify-rn --project-root .` — the new RN should show `PASS`.
3. Add a test in `tests/rn/`.
4. Run `docpact traceability --project-root .` — the RN should show `FULL`.

### Pre-commit hook

```bash
docpact validate --staged
```

This runs in under 1 second. It checks only the files you staged. Add it to your git hooks:

```bash
echo 'docpact validate --staged' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## What docpact IS

docpact is a **verification gate** for business rules. It answers one question:

> "Does the code do what the business rule says?"

If your code says `rn: [RN-008]` (restricted clients can't create tickets), docpact verifies that the code actually checks for restricted status. If your code says `side_effects: ninguno`, docpact verifies there are no database writes.

## What docpact is NOT

docpact does **not** replace these tools:

| Tool | What it does | docpact overlap |
|------|-------------|-----------------|
| ruff / pylint | Syntax, style, complexity | None |
| mypy / pyright | Type checking | None |
| pytest | Test execution | None |
| coverage | Test coverage | None |
| bandit | Security scanning | None |

docpact fills a **different gap**: verifying that declared business rules are actually implemented in code. No other tool does this.

## Why it exists

In AI-generated codebases, agents write code AND declare business rules. But who verifies that the declarations match reality?

docpact does. It's the quality gate between "I wrote a business rule" and "the business rule is actually implemented."

## Commands

| Command | Purpose |
|---------|---------|
| `docpact check .` | Validate contracts, side effects, transitive effects |
| `docpact verify-rn --project-root .` | Verify critical RNs are implemented in code |
| `docpact traceability --project-root .` | RN traceability matrix (declared vs tested) |
| `docpact validate --staged` | Pre-commit hook: fast contract enforcement |
| `docpact lint .` | Static analysis only (no tests, ideal for pre-commit) |
| `docpact test .` | Execute RN tests with pytest |
| `docpact extract` | Extract contracts as JSON |
| `docpact init` | Generate contract template for a function |
| `docpact fix .` | Auto-fix contract signature warnings |
| `docpact report` | Delta: declared rules vs code evidence |
| `docpact doctor` | Self-diagnosis of the docpact ecosystem |
| `docpact mcp` | Start MCP server for agent integration |

## How it works

### 1. Contracts (CONTRATOs)

Every public function declares its business rules in a docstring block:

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

### 2. Verification layers

docpact verifies at three levels:

**Static analysis** (AST parsing):
- Contracts exist and have required fields
- Side effects declarations match code patterns
- Dependencies are real and importable
- State transitions match the YAML matrix

**Transitive analysis**:
- If function A calls function B, A must declare B's side effects
- Exception: `service_delegation` means "I delegate, trust my callees"

**Pattern verification** (`docpact verify-rn`):
- Each critical business rule has a code pattern
- docpact verifies the pattern exists in the source

### 3. RN Pattern Verification

The most powerful feature. For each critical business rule, docpact checks that the code actually implements it:

```bash
docpact verify-rn --project-root .

=============================================================
  RN Pattern Verifier — 10 RNs checked
=============================================================

  ✅ RN-008    PASS    RESTRINGIDO no puede crear tickets
  ✅ RN-006    PASS    resuelto es el unico estado terminal
  ✅ RN-004    PASS    no saltos entre estados
  ✅ RN-TNT-001 PASS   TenantManager fail-closed
  ✅ RN-SEG-002 PASS   solo supervision asigna tareas
  ✅ RN-SEC-001 PASS   sesion expira 1 hora
  ✅ RN-SEC-002 PASS   lockout tras 5 intentos
  ✅ RN-C-016   PASS   credenciales fuera de logs
  ✅ RN-CL-002  PASS   clientes solo ven su info
  ✅ RN-010     PASS   consumo al 100% bloquea

  PASS: 10  FAIL: 0  NO_PATTERN: 0
=============================================================
```

### 4. RN Traceability Matrix

Shows which business rules are declared, implemented, and tested:

```bash
docpact traceability --project-root .

  RN           Status           Declarations                   Tests
  ──────────── ──────────────── ────────────────────────────── ────────────────────
  RN-001       FULL             soporte/state_machine/...       tests/rn/test_rn_001.py
  RN-008       FULL             clientes/models.py:activo       tests/rn/test_rn_008.py
  RN-SEC-001   FULL             nucleo/middleware/...            tests/rn/test_rn_SEC-001.py

  Summary: FULL: 79 | DECLARED_ONLY: 2 | TEST_ONLY: 10 | Coverage: 87%
```

Status meanings:
- **FULL** — Declared in code AND has a passing test. No action needed.
- **DECLARED_ONLY** — Has a CONTRATO but no test. Write a test in `tests/rn/`.
- **TEST_ONLY** — Has a test but no CONTRATO. Add a CONTRATO to the function.

### 5. YAML State Machine Validation

State transitions are declared in YAML and verified against code:

```toml
# docpact.toml
"RN-004" = { type = "state_transition", from_estado = "atender",
  to_cualquiera = ["asignado", "remoto", "programado"],
  yaml_source = "soporte/state_machine/tickets.yaml" }
```

docpact reads the YAML directly — no dict duplication needed.

## CONTRATO Template

Copy-paste this into any new function's docstring. Fill in the fields.

### Minimal (no side effects)

```python
def get_active_users(cliente_id):
    """Return active users for a client.

    CONTRATO:
      input:
        cliente_id: int — Client identifier
      output: QuerySet[Usuario] — Active users belonging to the client
      side_effects: ninguno
      rn: [RN-CL-002]
    """
```

### Full (with side effects and error cases)

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

### Delegation (trusts callees for side effects)

```python
def process_maintenance(maintenance):
    """Process a maintenance request end-to-end.

    CONTRATO:
      input:
        maintenance: Mantencion — Maintenance record
      output: Mantencion — Updated maintenance record
      side_effects: service_delegation
      rn: [RN-MANT-001]
    """
```

Use `service_delegation` when the function calls other functions and you don't want to enumerate every callee's side effects. docpact will still verify that callees have their own CONTRATOs.

## Troubleshooting

### "Funciones sin CONTRATO"

**Meaning:** Public functions exist without a `CONTRATO` docstring block.

**Fix:** Add a `CONTRATO:` section to the docstring of each flagged function. Use the template above.

```bash
# Auto-generate skeletons for all functions missing CONTRATOs:
docpact init . --batch
```

### "side_effects mismatch"

**Meaning:** A function declares `side_effects: ninguno` but calls another function that does `db_write`, sends emails, etc. Or vice versa.

**Fix:** Check what the function actually calls. If it calls `Model.save()`, add `db_write`. If it calls `send_email()`, add `email`. If it delegates everything to callees, use `service_delegation`.

```bash
# Re-check after fixing:
docpact check .
```

### "ORDER_FAIL"

**Meaning:** An operation checks a condition AFTER performing an action it should have blocked first. For example, checking permissions after already modifying the database.

**Fix:** Move the validation check BEFORE the operation it guards. The CONTRATO's `borde` field should list conditions checked before the main action.

### "RN pattern not found"

**Meaning:** `docpact verify-rn` can't find the code pattern for a business rule.

**Fix:** Add a pattern to `rn_verifier.py` that proves the rule is implemented. This is usually a specific function call, model method, or conditional check.

```bash
# Check which RNs are missing patterns:
docpact verify-rn --project-root .
# Get suggestions:
docpact config-suggest --project-root .
```

### "Tests NOT_FOUND"

**Meaning:** An RN declared in a CONTRATO has no corresponding test in `tests/rn/`.

**Fix:** Create a test file at `tests/rn/test_rn_<RN-ID>.py` that exercises the business rule.

## Installation

```bash
pip install docpact
```

For YAML support:
```bash
pip install docpact[yaml]
```

Python 3.10+. Core dependencies: stdlib only. Optional: pyyaml, httpx.

## License

MIT

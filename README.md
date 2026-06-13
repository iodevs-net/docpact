# docpact

**The type checker for business rules.**

docpact verifies that your code actually implements the business rules you declared. It doesn't replace your linter, type checker, or test runner — it fills the gap none of them cover.

```bash
pip install docpact
docpact check .
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
| `docpact report` | Delta: declared rules vs code evidence |
| `docpact extract` | Extract contracts as JSON |
| `docpact init` | Generate contract template for a function |

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

============================================================
  RN Pattern Verifier — 10 RNs checked
============================================================

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
============================================================
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

### 5. YAML State Machine Validation

State transitions are declared in YAML and verified against code:

```toml
# docpact.toml
"RN-004" = { type = "state_transition", from_estado = "atender",
  to_cualquiera = ["asignado", "remoto", "programado"],
  yaml_source = "soporte/state_machine/tickets.yaml" }
```

docpact reads the YAML directly — no dict duplication needed.

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

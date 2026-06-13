# docpact

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/fandijos/docpact)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-green.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-18%20tools-purple.svg)](#mcp-tools-18-total)

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

### Quick Start with MCP

For AI agents connected via [Model Context Protocol](https://modelcontextprotocol.io/), docpact exposes 18 tools natively. Start the server:

```bash
docpact mcp
```

The recommended agent workflow:

1. `obtener_briefing` — understand the project's business rules before coding
2. `obtener_contexto_funcion` — read a function's CONTRATO before editing it
3. `validar_cambio` — validate your diff and run relevant tests (enforcement gate)
4. `generar_reporte` — check overall compliance

For the full MCP tools reference and integration patterns, see the **[Agent Guide](DOCPACT_AGENT_GUIDE.md)**.

## MCP Tools (18 Total)

docpact exposes 18 MCP tools organized by purpose. Tools use semantic search powered by [FastEmbed](https://github.com/qdrant/fastembed) when available, with keyword fallback.

### Discovery & Context

| Tool | Purpose |
|------|---------|
| `obtener_contexto_funcion` | Full context for a function: CONTRATO, RNs, tests, file, line |
| `buscar_por_intencion` | Semantic search for functions by natural language intent |
| `navegar_referencias` | Cross-reference navigation: RN → functions, file → functions, function → calls |
| `obtener_briefing` | Project briefing with active RNs, side effects, risk zones |
| `listar_rns` | List all business rules with descriptions, functions, and test status |

### RN Management

| Tool | Purpose |
|------|---------|
| `obtener_rn` | Full context for a specific business rule |
| `buscar_rns_por_tema` | Search RNs by topic (semantic + keyword) |
| `verificar_conflicto` | Check if a new RN conflicts with existing ones |
| `crear_rn` | Create a new business rule in REGISTRO.md |
| `explicar_rn` | Explain an RN in plain language for stakeholders |

### Validation & Enforcement

| Tool | Purpose |
|------|---------|
| `validar_cambio` | Validate a diff + run relevant RN tests (enforcement gate) |
| `modificar_archivo` | Validate changes against CONTRATOs before applying |

### Contract Management

| Tool | Purpose |
|------|---------|
| `crear_contrato` | Generate a CONTRATO docstring from natural language |
| `corregir_contrato` | Diagnose and fix a broken CONTRATO |

### Operations

| Tool | Purpose |
|------|---------|
| `ejecutar_verificacion` | Full CONTRATO verification across the project |
| `ejecutar_tests` | Run business rule tests with pytest |
| `generar_reporte` | Generate coverage and compliance report |
| `setup_docpact` | Initialize docpact in a project (config, registry, index) |

## FastEmbed Semantic Detection

When [FastEmbed](https://github.com/qdrant/fastembed) is installed, docpact uses vector embeddings for semantic search across functions and RNs. The `buscar_por_intencion` and `buscar_rns_por_tema` tools combine cosine similarity (70%) with keyword matching (30%) for accurate results — even when the user's description doesn't match function names literally.

```bash
# Install with semantic search support
pip install docpact[semantic]
```

When FastEmbed is not available, docpact falls back to keyword-only search automatically. No configuration needed.

## Autonomous Agent Workflow

docpact is designed for autonomous AI agents that write and verify code. The MCP server injects a context string on initialization so agents understand available tools and the recommended workflow without reading external docs.

**The enforcement model:**

1. **Before editing** — call `obtener_contexto_funcion` to understand the function's contract
2. **Before committing** — call `validar_cambio` with your diff. If RN tests fail, the change is **INVALID** and must not be committed
3. **Adding business rules** — call `verificar_conflicto` first, then `crear_rn`, then `crear_contrato`
4. **Exploring** — use `buscar_por_intencion` when you don't know the function name

The `validar_cambio` tool is enforcement, not advisory. It runs the relevant RN tests filtered by `pytest -k` and blocks commits when tests fail.

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
| `docpact test-quality` | Evaluate test quality for RN coverage |
| `docpact llm-judge` | LLM-based evaluation of contract quality |
| `docpact extract` | Extract contracts as JSON |
| `docpact index` | Build pre-computed index for MCP server |
| `docpact init` | Generate contract template for a function |
| `docpact fix .` | Auto-fix contract signature warnings |
| `docpact config-suggest` | Suggest docpact.toml configuration |
| `docpact report` | Delta: declared rules vs code evidence |
| `docpact briefing` | Generate business rules briefing document |
| `docpact doctor` | Self-diagnosis of the docpact ecosystem |
| `docpact mcp` | Start MCP server for agent integration |
| `docpact mcp-doctor` | Diagnose MCP server and tool loading |
| `docpact install-mcp` | Install MCP server configuration for hosts |
| `docpact guard` | Validate changes against contracts at runtime |
| `docpact run` | Run a command with docpact guard active |

## Formal Specification

docpact implements the **Contrato Protocol v1** — a formal contract system for AI-native Python codebases. The protocol is specified in `docs/protocolo-v1/` with 7 documents covering schema, syntax, verification stages, and examples.

Key properties of the protocol:
- Every `.py` file is both implementation and specification
- Contracts are co-located with their implementations in docstrings
- The system operates as a 7-stage pipeline: Parse → Index → Verify → Dynamic Check → Aggregate → MCP Output → Reports
- All state is filesystem-based (JSON indexes, Markdown reports) — no database required

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

For YAML state machine support:
```bash
pip install docpact[yaml]
```

For semantic search (FastEmbed):
```bash
pip install docpact[semantic]
```

Python 3.10+. Core dependencies: stdlib only. Optional: pyyaml, fastembed.

## Further Reading

- **[Agent Guide](DOCPACT_AGENT_GUIDE.md)** — Complete MCP tools reference, workflow patterns, and troubleshooting for AI agents
- **[Architecture Brief](docs/architecture-brief.md)** — Pipeline architecture, key directories, and critical invariants
- **[Contrato Protocol v1](docs/protocolo-v1/)** — Formal specification (7 documents)

## License

MIT

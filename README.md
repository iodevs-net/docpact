# docpact

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/iodevs-net/docpact)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-green.svg)](https://github.com/iodevs-net/docpact)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-27%20tools-purple.svg)](#mcp-tools-27-total)

**The type checker for business rules.**

docpact verifies that your code actually implements the business rules you declared. It doesn't replace your linter, type checker, or test runner — it fills the gap none of them cover.

```bash
pip install git+https://github.com/iodevs-net/docpact.git
```

> **Installation note**: docpact is not yet published on PyPI. Install directly from the repository until the 1.0.1 release. For semantic search support: `pip install "docpact[semantic] @ git+https://github.com/iodevs-net/docpact.git"`.

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

For AI agents connected via [Model Context Protocol](https://modelcontextprotocol.io/), docpact exposes 27 tools natively. Start the server:

```bash
docpact mcp
```

The recommended agent workflow:

1. `obtener_briefing` — understand the project's business rules before coding
2. `obtener_contexto_funcion` — read a function's CONTRATO before editing it
3. `validar_cambio` — validate your diff and run relevant tests (enforcement gate)
4. `generar_reporte` — check overall compliance

For the full MCP tools reference and integration patterns, see the **[Agent Guide](DOCPACT_AGENT_GUIDE.md)**.

## MCP Tools (27 Total)

docpact exposes 27 MCP tools organized by purpose. Tools use semantic search powered by [FastEmbed](https://github.com/qdrant/fastembed) when available, with keyword fallback.

### Discovery & Context (5)

| Tool | Purpose |
|------|---------|
| `obtener_contexto_funcion` | Full context for a function: CONTRATO, RNs, tests, file, line |
| `buscar_por_intencion` | Semantic search for functions by natural language intent |
| `navegar_referencias` | Cross-reference navigation: RN → functions, file → functions, function → calls |
| `obtener_briefing` | Project briefing with active RNs, side effects, risk zones |
| `listar_rns` | List all business rules with descriptions, functions, and test status |

### RN Management (5)

| Tool | Purpose |
|------|---------|
| `obtener_rn` | Full context for a specific business rule |
| `buscar_rns_por_tema` | Search RNs by topic (semantic + keyword) |
| `verificar_conflicto` | Check if a new RN conflicts with existing ones |
| `crear_rn` | Create a new business rule in REGISTRO.md |
| `explicar_rn` | Explain an RN in plain language for stakeholders |

### Validation & Enforcement (4)

| Tool | Purpose |
|------|---------|
| `validar_cambio` | Validate a diff + run relevant RN tests (enforcement gate) |
| `modificar_archivo` | Validate changes against CONTRATOs before applying |
| `explicar_errores` | Translate docpact error codes into plain language with fix suggestions |
| `predecir_bugs` | AST-based bug prediction (mutable defaults, bare except, resource leaks) |

### Contract Management (2)

| Tool | Purpose |
|------|---------|
| `crear_contrato` | Generate a CONTRATO docstring from natural language |
| `corregir_contrato` | Diagnose and fix a broken CONTRATO |

### Discovery & Auto-generation (4)

| Tool | Purpose |
|------|---------|
| `extraer_rns` | Analyze a project and extract implicit business rules (regex + AST) |
| `descubrir_reglas` | Find business rules not yet declared in CONTRATOs |
| `generar_codigo` | Generate code stubs from a CONTRATO spec |
| `config-suggest` | Suggest docpact.toml patterns for RNs without validators (CLI) |

### Operations (7)

| Tool | Purpose |
|------|---------|
| `ejecutar_verificacion` | Full CONTRATO verification across the project |
| `ejecutar_tests` | Run business rule tests with pytest |
| `generar_reporte` | Generate coverage and compliance report |
| `setup_docpact` | Initialize docpact in a project (config, registry, index) |
| `metricas_violaciones` | Live metrics: how many CONTRATOs are violated, by category |
| `sugerir_reglas` | Suggest rules to formalize based on code patterns |
| `salud_reglas` | Health check of the rule registry: orphans, conflicts, gaps |
| `priorizar_reglas` | Rank rules by impact (coverage, violations, risk) |

> **Note**: The "Reglas Vivas" suite (`metricas_violaciones`, `sugerir_reglas`, `salud_reglas`, `priorizar_reglas`, `predecir_bugs`, `generar_codigo`, `descubrir_reglas`, `extraer_rns`, `explicar_errores`) was added in commit `9335cfa` and is not yet documented in `DOCPACT_AGENT_GUIDE.md`. See `CHANGELOG.md` for the full list.

## FastEmbed Semantic Detection

When [FastEmbed](https://github.com/qdrant/fastembed) is installed, docpact uses vector embeddings powered by the `jina-embeddings-v2-base-es` model for semantic search across functions and RNs. The `buscar_por_intencion` and `buscar_rns_por_tema` tools combine cosine similarity (70%) with keyword matching (30%) for accurate results — even when the user's description doesn't match function names literally.

```bash
# Install with semantic search support
pip install "docpact[semantic] @ git+https://github.com/iodevs-net/docpact.git"
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

This runs in under 1 second. It checks only the files you staged. Add it to git hooks:

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
|------|-------------|----------------|
| ruff / pylint | Syntax, style, complexity | None |
| mypy / pyright | Type checking | None |
| pytest | Test execution | None |
| coverage | Test coverage | None |
| bandit | Security scanning | None |

docpact fills a **different gap**: verifying that declared business rules are actually implemented in code. No other tool does this.

## Honest limitations

In the spirit of the project's "honest metrics" policy (see `docs/marker-honesty.md`):

- **`extraer_rns` is a starting point, not ground truth.** It uses regex + AST patterns and overcounts: in a 105-file Django project, it reports ~1,400 "rule evidences" grouped into 11 categories, where many are false positives (string literals, queries, docstrings, UI copy that match the pattern). Use it to discover candidates, then validate manually.
- **`init --batch` scaffolds empty CONTRATOs.** Empty CONTRATOs are worse than no CONTRATO because they create a false sense of coverage. Use `init` per-function, write the actual side_effects and rn fields, then commit.
- **Semantic search is optional.** Without FastEmbed, `buscar_por_intencion` and `buscar_rns_por_tema` fall back to keyword search. Install the `[semantic]` extra for better discovery.

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
| `docpact extract` | Extract existing CONTRATOs as JSON |
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

docpact implements the **Contrato Protocol v2** — a formal contract system for AI-native Python codebases. The protocol is specified in `docs/spec/` with 7 documents covering schema, syntax, verification stages, and examples.

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
…
  Summary: FULL: 79 | DECLARED_ONLY: 2 | TEST_ONLY: 10 | Coverage: 87%
```

## Project structure

```
src/docpact/
├── api.py                    # Public Python API
├── bridge.py                 # Internal component bridge
├── briefing.py               # Briefing generation
├── config.py                 # Configuration loading
├── config_suggest.py         # Auto-suggest docpact.toml patterns
├── generator.py              # CONTRATO skeleton generator
├── guard.py                  # Runtime guard
├── index.py                  # Pre-computed index for MCP
├── installer.py              # MCP host installer
├── llm_generator.py          # LLM-powered CONTRATO generation
├── llm_judge.py              # LLM-powered quality evaluation
├── mcp_server.py             # MCP server (27 tools, 2,674 LoC)
├── reporter.py               # Report generation
├── runner.py                 # Dynamic sandbox runner
├── cli/
│   ├── main.py               # CLI entry point (67 LoC)
│   └── commands/             # 23 subcommands
├── checker/                  # 22 verification modules
│   ├── orchestrator.py       # Pipeline coordinator
│   ├── rn_checker.py         # RN pattern verification
│   ├── contract_index.py     # CONTRATO index
│   ├── side_effects.py       # Side effect detection
│   └── semantic/             # 5 semantic validators
├── models/
│   └── contrato.py           # CONTRATO dataclass
├── parser/                   # Python + TypeScript parsers
├── runtime/
│   └── pytest_plugin.py      # pytest integration
└── schema/
    └── validator.py          # CONTRATO schema validation
```

## License

MIT

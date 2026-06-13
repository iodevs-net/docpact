# Repository Guidelines

## Project Overview

docpact is a **type checker for business rules** — a static analysis + runtime verification tool that ensures Python (and TypeScript) code implements the business rules declared in structured docstring blocks called **CONTRATOs**. It parses docstrings for contract blocks, verifies side effects via AST analysis, validates business rules (RN-XXX) through semantic validators, generates an index for MCP agent integration, and provides a pytest plugin for runtime enforcement.

Targets AI-generated codebases where agents write code AND declare rules, but nobody verifies the declarations match reality.

## Architecture & Data Flow

Pipeline architecture with clear layer separation:

**Layer 1 — Parsing** (`src/docpact/parser/`)
- Lexer tokenizes CONTRATO blocks from docstrings using indentation-aware rules
- Parser converts tokens into frozen `Contrato` dataclasses
- Extractors: Python (stdlib `ast`) and TypeScript (regex-based)

**Layer 2 — Verification** (`src/docpact/checker/`)
- `orchestrator.py` (884 lines) coordinates 21 specialized checkers per function:
  1. `side_effects.py` — AST walker classifies calls into categories vs declared effects
  2. `transitive_effects.py` — Follows call chains via `ContractIndex` for undeclared effects
  3. `semantic_rn.py` (666 lines) — Dispatcher for 5 validators: `state_transition`, `no_import`, `required_groups`, `tenant_safe`, `has_pattern`
  4. `marker_honesty.py` — Detects decorative # RN-XXX on delegation lines
  5. `rn_checker.py` — Basic # RN-XXX marker verification
  6. `rn_crossref.py` — RN propagation across call boundaries
  7. `rn_test_checker.py` — Verifies test existence and execution
  8. `rn_verifier.py` — Hardcoded pattern verification (50+ RN specs)
  9. `deps_checker.py` — Dependency file/symbol existence
  10. `import_checker.py` — Prevents duplicate inline imports
  11. `boundary_checker.py` — Module isolation rules
  12. `contract_index.py` — Global index for cross-function analysis
  13. `doctor.py` — Autodiagnostic system
  14. `signature_checker.py` — Function signature validation
  15. `ts_checker.py` — TypeScript-specific verification
  16. `ts_sidefx.py` — TypeScript side effects detection
  17. `rn_patterns.py` — RN pattern matching utilities
  18. `rn_registry.py` — RN registry management

**Layer 3 — Indexing** (`src/docpact/index.py`)
- Pre-calculates `.docpact/index.json` with function metadata, RN mappings, test locations
- Optional FastEmbed embeddings for semantic search
- Single-scan, RAM-resident queries for MCP

**Layer 4 — Runtime Enforcement** (`src/docpact/runtime/`)
- `pytest_plugin.py` — Auto-wraps functions with CONTRATOs at test time
- `sentinels.py` — Context managers intercept DB writes (Django), file writes, emails
- `exceptions.py` — `ContractViolationError` on undeclared side effects
- Modes: `strict` (raises) and `warning` (emits warnings)

**Layer 5 — Interfaces**
- CLI (`cli/main.py` 620 lines + `cli/commands.py` 1191 lines, 15+ commands)
- MCP server (`mcp_server.py`, JSON-RPC 2.0 over stdio, 12 tools)
- Python API (`api.py`, thin wrappers)

**Key data flow**: Source files → AST parse → docstring extraction → lexer tokens → `Contrato` model → checker pipeline → `Hallazgo` list → `ResultadoProyecto` → report. For MCP: source files → index generation (one-time) → RAM index → tool queries (<5ms).

## Key Directories

| Path | Purpose |
|------|---------|
| `src/docpact/checker/` | 21 specialized verification modules |
| `src/docpact/models/` | Frozen dataclasses: `Contrato`, `SideEffect`, `ReglaNegocio`, etc. |
| `src/docpact/runtime/` | Pytest plugin, sentinels, `ContractViolationError` |
| `src/docpact/cli/` | CLI entry point (`main.py`) + `commands/` package (7 modules) |
| `src/docpact/schema/` | JSON Schema (`contrato-v1.json`) + validator |
| `tests/` | 35 test files, flat structure, fixtures dirs |
| `tests/fixtures_ts/` | TypeScript/TSX CONTRATO example files (17 files) |
| `docs/` | Protocol spec, side effects patterns, marker honesty docs |
| `docs/investigacion/` | 9 LLM research reports on AI-native code |
| `docs/conclusiones/` | Synthesis document combining research findings |
| `workplans/` | 4 implementation phases (F01-F04) + 2 task improvements (T01-T02) |

## Development Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run tests
pytest                              # all tests
pytest tests/test_parser.py         # single file
pytest -k "test_side_effects"       # by name pattern

# Type checking
mypy src/docpact

# Build
hatch build

# CLI commands
docpact check .                     # full verification
docpact extract .                   # extract all CONTRATOs
docpact lint .                      # static-only (no test execution)
docpact test .                      # RN tests only
docpact validate .                  # pre-commit hook mode
docpact index .                     # generate MCP index
docpact mcp .                       # start MCP server
docpact doctor .                    # autodiagnostic
docpact verify-rn .                 # RN-specific check
docpact traceability .              # RN traceability matrix
docpact report .                    # delta report vs REGISTRO.md
docpact init .                      # generate CONTRATO skeletons
docpact fix .                       # auto-fix missing CONTRATOs
docpact config-suggest .            # suggest docpact.toml config
docpact test-quality .              # test quality check
docpact install-mcp                 # install MCP server config
docpact mcp-doctor                  # MCP server diagnostics
```

## Code Conventions & Common Patterns

### Data Models
- **Frozen dataclasses** throughout: `Contrato`, `SideEffect`, `ReglaNegocio`, `CasoBorde`, `Dependencia`, `Hallazgo`, `ResultadoFuncion`, `ResultadoArchivo`, `ResultadoProyecto`
- Enum for fixed types: `TipoFuncion`
- Spanish naming for domain concepts (CONTRATO, RN, borde, dependencias)

### Analysis Patterns
- **AST-based analysis** — never execute code for static checks (stdlib `ast` module)
- **Regex for TypeScript** — `.ts`/`.tsx` files use regex extraction, not AST
- **Compiled regex cache** — `DocpactConfig` pre-compiles all patterns for fast matching
- **ContractIndex** with import resolution — resolves cross-function/cross-module calls

### Error Handling
- `Hallazgo` dataclass with severity levels (error vs warning)
- Warnings don't block CLI exit; errors do
- `ContractViolationError` (extends `AssertionError`) for runtime violations
- Graceful fallbacks throughout (e.g., `tomllib` with fallback for Python <3.11)

### Configuration
- `docpact.toml` — project-level config (read via `tomllib`)
- `modules.toml` — optional cross-module boundary rules
- `REGISTRO.md` — canonical RN registry (optional)

### Naming
- Python modules: snake_case
- Test files: `test_<module>.py` matching source module name
- CLI commands: kebab-case (`verify-rn`, `traceability`, `config-suggest`)
- RN IDs: `RN-XXX` format (regex: `RN-\d+`)
- Domain terms in Spanish: `contrato`, `regla_negocio`, `borde`, `dependencia`, `side_effects`

### Key Invariants
- `side_effects` is the only required field in a CONTRATO
- All model classes are frozen (immutable)
- Index is generated once, read many times (MCP perf)
- Marker honesty: warnings only, never errors (agent decides)
- Transitive effects: semantic matching for Spanish descriptions

## Important Files

| File | Role |
|------|------|
| `pyproject.toml` | Build config, deps, entry points, pytest/mypy config |
| `src/docpact/__init__.py` | Package root, version declaration |
| `src/docpact/config.py` | `DocpactConfig` — reads `docpact.toml`, compiles patterns |
| `src/docpact/models/contrato.py` | Core domain models (all frozen dataclasses) |
| `src/docpact/checker/orchestrator.py` | Central verification pipeline (884 lines) |
| `src/docpact/parser/lexer.py` | CONTRATO block tokenizer |
| `src/docpact/parser/parser.py` | Token-to-`Contrato` model converter |
| `src/docpact/parser/extractor.py` | Python AST docstring extractor |
| `src/docpact/mcp_server.py` | MCP server (12 tools, JSON-RPC over stdio) |
| `src/docpact/index.py` | Pre-calculated index generator for MCP |
| `src/docpact/cli/main.py` | CLI entry point (620 lines) + `commands/` package (7 modules) |
| `src/docpact/runtime/pytest_plugin.py` | Pytest plugin for runtime enforcement |
| `src/docpact/runtime/sentinels.py` | DB/disk/email interceptors |
| `src/docpact/schema/contrato-v1.json` | JSON Schema (draft-07) for CONTRATO validation |
| `.github/workflows/ci.yml` | CI: Python 3.12+3.13, pytest, self-check |
| `src/docpact/guard.py` | Guard system for runtime enforcement (245 lines) |
| `src/docpact/briefing.py` | Briefing generation for context handoff (324 lines) |
| `src/docpact/llm_generator.py` | LLM-powered code generation (205 lines) |
| `src/docpact/llm_judge.py` | LLM-based judgment/scoring (179 lines) |
| `src/docpact/bridge.py` | Bridge between components (128 lines) |

## Runtime/Tooling Preferences

- **Python 3.10+** required (CI tests 3.12 and 3.13)
- **Zero runtime dependencies** — stdlib only (uses `tomllib` with fallback for <3.11)
- **Optional extras**: `pyyaml>=6` (`[yaml]`), `jsonschema>=4` (`[dev]`), `fastembed` for semantic search
- **Build backend**: Hatchling (PEP 517)
- **Package manager**: pip (no poetry/pdm/hatch CLI usage)
- **No separate linter config** — all tooling config in `pyproject.toml`
- **mypy** targets 3.10 strict mode (with ignore_errors for `cli.*`, `mcp_server`, `runner`, `tests.*`)
- **Docker**: `sandbox.Dockerfile` for sandboxed test execution (python:3.12-slim)

## Testing & QA

- **Framework**: pytest >=7 with pytest-cov >=4
- **Config**: `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=['tests']`, `addopts='-v --cov=src/docpact --cov-report=term-missing'`
- **No conftest.py** — all fixtures defined inline per test file
- **Primary fixture**: `tmp_path` (used in 20+ files for temp project structures)
- **Mocking**: `unittest.mock.patch` for HTTP, `monkeypatch` for env vars/module patching
- **35 test files**, ~300KB total, flat structure (no subdirectories for test files)
- **Test classes**: Used for logical grouping only (no `__init__`, no setup/teardown)
- **Helper functions**: Module-level `_mock_*`, `_make_*`, `_write_*` prefixes
- **Coverage**: Configured but no threshold enforced (`--cov-fail-under` absent)
- **Self-check**: CI runs `docpact doctor . --min-score 0` as smoke test
- **Language**: Test docstrings and comments in Spanish, function names in English

### Running tests

```bash
pytest                              # all tests
pytest --cov=src/docpact --cov-report=html  # with HTML coverage
pytest tests/test_semantic_rn.py    # single module
pytest -k "tenant_safe"             # by keyword
```

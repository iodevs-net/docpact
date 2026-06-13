# Tasks: docpact Spec Ecosystem Implementation

## Reference
- **Specs:** `docs/spec/contrato-v2-spec.md`, `docs/spec/verification-v1-spec.md`, `docs/spec/mcp-v2-spec.md`, `docs/spec/discovery-v1-spec.md`, `docs/spec/versioning-v1-spec.md`
- **Current state:** docpact v0.5.0 — functional parser, checker pipeline (13 checkers), MCP server (6 tools), CLI (7 command groups), briefing, reporter, index generator, guard, pytest plugin.

## Task List

---

### Task 1: Contrato v2 — Semantic Fields in Data Model
- **Description**: Add the three v2 semantic fields (`comportamiento`, `asume`, `produce`) to the `Contrato` dataclass. All are `Optional[str]`, defaulting to `None`. Backward-compatible: existing v1 contracts parse identically.
- **Files to modify**: `src/docpact/models/contrato.py`
- **Dependencies**: None
- **Verification**: `pytest tests/test_parser.py tests/test_extractor.py` — existing tests still pass. Manually parse a docstring with `comportamiento: |` block scalar and confirm the field populates.
- **Estimated scope**: small

---

### Task 2: Contrato v2 — Parser YAML Block Scalar Support
- **Description**: Extend the CONTRATO parser to handle YAML block scalar syntax (`comportamiento: |`, `asume: |`, `produce: |`). Lines after `|` at greater indentation are captured, stripped, and joined with spaces. The first line at or below root indentation ends the block. Also support `CONTRATO:v2.0.0:` version tag in the header.
- **Files to modify**: `src/docpact/parser/contrato_parser.py` (or equivalent lexer/parser modules)
- **Dependencies**: Task 1
- **Verification**: `pytest tests/test_parser.py` — add test cases for: (a) single-line semantic fields, (b) multi-line `|` block scalars, (c) empty `|` producing `None`, (d) version tag `CONTRATO:v2.0.0:` parsed correctly, (e) mixed v1/v2 fields in same block.
- **Estimated scope**: medium

---

### Task 3: Contrato v2 — JSON Schema File
- **Description**: Create the canonical JSON Schema (`src/docpact/schema/contrato-v2.json`) as defined in contrato-v2-spec §9. This schema validates the serialized Contrato representation for MCP and programmatic use.
- **Files to modify**: `src/docpact/schema/contrato-v2.json` (new)
- **Dependencies**: Task 1
- **Verification**: `python -c "import json; json.load(open('src/docpact/schema/contrato-v2.json'))"` — valid JSON. Write a test that validates sample Contrato dicts against the schema using `jsonschema.validate()`.
- **Estimated scope**: small

---

### Task 4: Contrato v2 — Comma Splitting with Parenthesis Awareness
- **Description**: Ensure `side_effects` parsing handles commas inside parentheses correctly (e.g., `"subprocess (docker info, hostname, uname), http get"` → 2 items, not 4). Track parenthesis nesting depth and string literals during split.
- **Files to modify**: `src/docpact/parser/contrato_parser.py`
- **Dependencies**: None
- **Verification**: `pytest tests/test_parser.py` — add test cases for: nested parens, quoted strings with commas, empty parens, consecutive commas.
- **Estimated scope**: small

---

### Task 5: Contrato v2 — Inline JSON Array Parsing for Compound Fields
- **Description**: Support `rn: [RN-010, RN-042]` and `dependencias: ["path/file.py::Symbol"]` as compact alternatives to the list syntax. Parse via `json.loads()` with fallback to bracket-strip-and-split.
- **Files to modify**: `src/docpact/parser/contrato_parser.py`
- **Dependencies**: None
- **Verification**: `pytest tests/test_parser.py` — test JSON array syntax for `rn`, `borde`, `dependencias`. Test malformed JSON fallback.
- **Estimated scope**: small

---

### Task 6: Contrato v2 — Validation Rules (Structural)
- **Description**: Implement the structural validation rules from contrato-v2-spec §5.1: SE-1 (side_effects required), SE-2 (description length ≥ 2), RN-1 (ID format `^RN-\d{3,}$`), IN-1 (non-empty type unless allowlisted), DE-1 (dependency ref format), DE-2 (no path traversal `..`), BD-1 (borde colon separator).
- **Files to modify**: `src/docpact/parser/contrato_parser.py`, `src/docpact/models/contrato.py`
- **Dependencies**: Task 1
- **Verification**: `pytest tests/test_parser.py tests/test_validator.py` — one test per rule (SE-1 through BD-1), covering both valid and invalid inputs.
- **Estimated scope**: medium

---

### Task 7: Verification — Ensure All 13 Checkers Are Wired
- **Description**: Audit the orchestrator (`src/docpact/checker/orchestrator.py`) against verification-v1-spec §4.3 and Appendix A. Ensure all 13 checkers execute in the specified order: (1) Side Effects, (2) Transitive Side Effects, (3) RN Marker [LEGACY], (4) Dependency, (5) Inline Import, (6) Semantic RN, (7) Signature, (8) RN Registry, (9) RN Test, (10) Marker Honesty, (11) Module Boundary, (12) RN Cross-Reference, (13) Doctor. Fix any ordering gaps.
- **Files to modify**: `src/docpact/checker/orchestrator.py`, `src/docpact/checker/_process_function.py`
- **Dependencies**: None
- **Verification**: `pytest tests/test_orchestrator.py tests/test_orchestrator_semantic.py` — confirm each checker is invoked. Add a test that mocks each checker and verifies call order.
- **Estimated scope**: medium

---

### Task 8: Verification — Honest Metrics and Gate Enforcement
- **Description**: Ensure `ResultadoProyecto` exposes `rns_fake`, `rns_huerfanas`, `rns_placeholders`, `funciones_sin_contrato`, `funciones_totales`, and `score_legacy`. Implement gate enforcement per verification-v1-spec §8.1: gates checked in order (rns_fake → rns_huerfanas → min_score → errors → strict). First failing gate determines exit code.
- **Files to modify**: `src/docpact/checker/models.py`, `src/docpact/cli/commands/check.py`
- **Dependencies**: Task 7
- **Verification**: `pytest tests/test_orchestrator.py` — test gate ordering, test that `rns_fake > 0` exits 1 before checking score. Test `--max-rns-fake`, `--max-rns-huerfanas`, `--min-score` flags.
- **Estimated scope**: medium

---

### Task 9: Verification — Legacy Score (Deprecated) with Honest Metrics Default
- **Description**: Keep the legacy scoring formula (verification-v1-spec §7.1) for backward compat but mark it deprecated. Implement the Honest Metrics (§7.2) as the recommended output. CLI output should default to honest metrics; legacy score behind `--legacy-score` flag.
- **Files to modify**: `src/docpact/checker/models.py`, `src/docpact/cli/commands/check.py`, `src/docpact/reporter.py`
- **Dependencies**: Task 8
- **Verification**: `pytest tests/test_orchestrator.py tests/test_reporter.py` — verify honest metrics are default output, legacy score accessible via flag.
- **Estimated scope**: small

---

### Task 10: MCP Server — Discovery & Navigation Tools (1–6)
- **Description**: Implement the 6 Discovery & Navigation tools: `obtener_contexto_funcion`, `buscar_por_intencion`, `validar_cambio`, `obtener_rn`, `buscar_rns_por_tema`, `navegar_referencias`. Each tool reads from the pre-computed index and returns structured JSON per the MCP spec §7.1. `validar_cambio` runs pytest as a gate.
- **Files to modify**: `src/docpact/mcp_server.py`
- **Dependencies**: Task 7 (index must be complete)
- **Verification**: `pytest tests/test_mcp_tools.py` — one test per tool covering: success case, not-found case, multi-match case. Test `validar_cambio` with passing and failing tests.
- **Estimated scope**: large

---

### Task 11: MCP Server — Project Context Tools (7–8)
- **Description**: Implement `obtener_briefing` (returns `.docpact/briefing.md`, auto-regenerates if stale) and `modificar_archivo` (guard: validates a diff against CONTRATOs before applying, returns allowed/rejected with violations).
- **Files to modify**: `src/docpact/mcp_server.py`, `src/docpact/guard.py`
- **Dependencies**: None
- **Verification**: `pytest tests/test_mcp_tools.py tests/test_guard.py` — test briefing regeneration on stale fingerprint, test guard rejection with side_effect and rn violations.
- **Estimated scope**: medium

---

### Task 12: MCP Server — Rule Management Tools (9–12)
- **Description**: Implement `listar_rns`, `verificar_conflicto`, `crear_rn`, `explicar_rn`. `verificar_conflicto` uses semantic similarity (FastEmbed when available, keyword fallback) to detect duplicates, same-concept, and override conflicts. `crear_rn` appends to REGISTRO.md with ID validation.
- **Files to modify**: `src/docpact/mcp_server.py`
- **Dependencies**: Task 10 (index must expose RN data)
- **Verification**: `pytest tests/test_mcp_tools.py` — test `listar_rns` returns all RNs with status. Test `verificar_conflicto` with near-duplicate description. Test `crear_rn` appends to registry. Test `explicar_rn` status values (COMPLETA, PARCIAL, PENDIENTE).
- **Estimated scope**: large

---

### Task 13: MCP Server — Contract Management Tools (13–15)
- **Description**: Implement `setup_docpact` (idempotent project init: create docpact.toml, docs dirs, generate index, check FastEmbed), `crear_contrato` (generate CONTRATO block from description), `corregir_contrato` (diagnose and suggest fixes for a broken CONTRATO).
- **Files to modify**: `src/docpact/mcp_server.py`, `src/docpact/cli/init.py` (reuse setup logic)
- **Dependencies**: None
- **Verification**: `pytest tests/test_mcp_tools.py` — test `setup_docpact` idempotency (run twice, no errors). Test `crear_contrato` output format. Test `corregir_contrato` with known-bad CONTRATO.
- **Estimated scope**: large

---

### Task 14: MCP Server — Verification & Reporting Tools (16–18)
- **Description**: Implement `ejecutar_verificacion` (full project verification, returns errors/warnings/score), `ejecutar_tests` (run pytest subprocess with 60s timeout), `generar_reporte` (RN coverage summary). Wire these to existing checker/reporter infrastructure.
- **Files to modify**: `src/docpact/mcp_server.py`
- **Dependencies**: Tasks 7, 9
- **Verification**: `pytest tests/test_mcp_tools.py` — test `ejecutar_verificacion` returns correct counts. Test `ejecutar_tests` timeout handling. Test `generar_reporte` output structure.
- **Estimated scope**: medium

---

### Task 15: MCP Server — Protocol Conformance
- **Description**: Ensure the MCP server conforms to mcp-v2-spec §13: (a) all 18 tools registered, (b) `initialize` response has `protocolVersion`, `capabilities`, `serverInfo`, (c) `tools/list` returns all 18 with correct `inputSchema`, (d) `shutdown` returns null, (e) unknown methods return `-32000`, (f) tool-level errors use `"error"` key in result (not JSON-RPC errors), (g) notifications handled silently.
- **Files to modify**: `src/docpact/mcp_server.py`
- **Dependencies**: Tasks 10–14
- **Verification**: `pytest tests/test_mcp_tools.py` — test initialize response shape, tools/list count = 18, shutdown returns null, unknown method returns -32000, notification (no `id`) gets no response.
- **Estimated scope**: medium

---

### Task 16: Discovery — Project-Root Detection (Sentinel Algorithm)
- **Description**: Implement the sentinel-based project-root detection from discovery-v1-spec §3. Walk upward from start path checking for `docpact.toml`, `REGISTRO.md`, `pyproject.toml`, `.git/` in priority order. Support overrides: `--project-root` flag, `DOCPACT_PROJECT_ROOT` env var, MCP `projectRoot` param.
- **Files to modify**: `src/docpact/runtime/sentinels.py`
- **Dependencies**: None
- **Verification**: `pytest tests/test_runtime.py` — test sentinel priority (closest ancestor wins), test override precedence (CLI > env > sentinel > CWD), test monorepo scenario from Appendix A.
- **Estimated scope**: medium

---

### Task 17: Discovery — Configuration Cascade and Defaults
- **Description**: Implement the config resolution cascade from discovery-v1-spec §4.3: (1) explicit `--config`, (2) `docpact.toml` in project root, (3) `.docpact.toml` in project root, (4) `docpact.toml` in CWD, (5) built-in defaults. Missing/malformed TOML is NOT an error — use defaults and log warning. Unknown keys silently ignored.
- **Files to modify**: `src/docpact/config.py`
- **Dependencies**: Task 16
- **Verification**: `pytest tests/test_config.py` — test cascade order, test malformed TOML falls back to defaults, test unknown keys ignored, test `modules.toml` merge behavior.
- **Estimated scope**: medium

---

### Task 18: Discovery — MCP Server Handshake
- **Description**: Ensure the MCP handshake matches discovery-v1-spec §5: `initialize` resolves project root (param > env > CWD), loads/generates index, responds with `protocolVersion`/`capabilities`/`serverInfo`. Startup diagnostics log to stderr. Index auto-regenerates when stale.
- **Files to modify**: `src/docpact/mcp_server.py`
- **Dependencies**: Tasks 15, 16
- **Verification**: `pytest tests/test_mcp_tools.py` — test initialize with explicit `projectRoot`, test with `DOCPACT_PROJECT_ROOT` env var, test stale index auto-regeneration, test stderr diagnostic output.
- **Estimated scope**: small

---

### Task 19: Discovery — `install-mcp` Command and Host Detection
- **Description**: Implement `docpact install-mcp` that detects the agent host (OMP, Claude Code, generic) using the cascade from discovery-v1-spec §6.6 and writes the appropriate MCP server config. Includes `docpact mcp-doctor` for environment diagnostics.
- **Files to modify**: `src/docpact/cli/commands/mcp.py` (new subcommands)
- **Dependencies**: Task 16
- **Verification**: `pytest tests/test_installer.py tests/test_mcp_doctor.py` — test host detection for each priority level, test config generation for OMP and Claude Code formats, test `mcp-doctor` output.
- **Estimated scope**: medium

---

### Task 20: CLI — `docpact validate` (Pre-commit Hook)
- **Description**: Implement `docpact validate` that runs static-only verification on staged files (`git diff --cached`). No pytest. Fails if any staged file has CONTRATOs contradicting implementation. Target <1s latency.
- **Files to modify**: `src/docpact/cli/commands/check.py` (new subcommand or flag)
- **Dependencies**: Task 7
- **Verification**: `pytest tests/test_main.py` — test that `validate` only processes staged files, test that it skips pytest, test exit code 1 on violations.
- **Estimated scope**: medium

---

### Task 21: CLI — `docpact lint` (Static-Only Check)
- **Description**: Implement `docpact lint` — same as `check` but static analysis only (no pytest execution). Reuses the existing checker pipeline with `run_tests=False`.
- **Files to modify**: `src/docpact/cli/commands/check.py`
- **Dependencies**: Task 7
- **Verification**: `pytest tests/test_main.py` — test that `lint` never invokes pytest, test output matches `check` minus test results.
- **Estimated scope**: small

---

### Task 22: CLI — `docpact doctor` (Ecosystem Self-Diagnosis)
- **Description**: Implement `docpact doctor` as a CLI command. Runs the 7 checks from verification-v1-spec §6.13: CI workflow, pre-commit config, score threshold, RN registry, test placeholders, docpact version, FastEmbed availability. Output human-readable or `--json`.
- **Files to modify**: `src/docpact/cli/commands/check.py` (or new doctor module), `src/docpact/checker/doctor.py`
- **Dependencies**: None
- **Verification**: `pytest tests/test_diagnostico.py` — test each of the 7 checks passes/fails correctly. Test `--json` output format.
- **Estimated scope**: medium

---

### Task 23: CLI — `docpact index` Command
- **Description**: Expose the index generator as a standalone CLI command: `docpact index [--force] [--project-root PATH]`. Generates `.docpact/index.json` and logs stats.
- **Files to modify**: `src/docpact/cli/commands/generate.py` (or new index module)
- **Dependencies**: None
- **Verification**: `pytest tests/test_main.py` — test `docpact index` creates `.docpact/index.json`, test `--force` regenerates, test output stats.
- **Estimated scope**: small

---

### Task 24: CLI — `docpact migrate` Command
- **Description**: Implement `docpact migrate --from X --to Y` per versioning-v1-spec §4.2. Reads project version, applies migrations in order, rewrites `docpact.toml` to new schema preserving user values. Supports `--dry-run`. Idempotent. Never deletes user data.
- **Files to modify**: `src/docpact/cli/commands/migrate.py` (new), `src/docpact/migrate/` (new package)
- **Dependencies**: Task 17
- **Verification**: `pytest tests/test_migrate.py` (new) — test dry-run shows changes without writing, test idempotency (run twice = same result), test config rewrite preserves values, test incomplete migrations leave `# TODO: docpact migrate` comment.
- **Estimated scope**: large

---

### Task 25: CLI — Exit Code Contract
- **Description**: Ensure all CLI commands use the stable exit code contract: `0` = success, `1` = verification failure, `2` = usage error. Audit every command handler.
- **Files to modify**: `src/docpact/cli/commands/*.py`
- **Dependencies**: Tasks 20–24
- **Verification**: `pytest tests/test_main.py` — test each command returns correct exit code for success, failure, and usage error scenarios.
- **Estimated scope**: small

---

### Task 26: Versioning — Deprecation Warning Infrastructure
- **Description**: Implement the deprecation warning system from versioning-v1-spec §5.2. Create a utility that emits warnings in the spec-defined format for CLI flags (`WARNING: --old-flag is deprecated...`), Python API (`warnings.warn(..., DeprecationWarning)`), and MCP tools (text in CallToolResult). Mark `min_score`/legacy score as deprecated.
- **Files to modify**: `src/docpact/deprecation.py` (new), `src/docpact/config.py`, `src/docpact/cli/commands/check.py`
- **Dependencies**: None
- **Verification**: `pytest tests/test_deprecation.py` (new) — test warning format matches spec, test `--strict` mode converts deprecation warnings to errors, test Python API `warnings.warn` with correct `stacklevel`.
- **Estimated scope**: medium

---

### Task 27: Versioning — `CHANGELOG.md` Structure
- **Description**: Create `CHANGELOG.md` following Keep a Changelog format per versioning-v1-spec §6. Include `[Unreleased]` section with Added/Changed/Deprecated/Removed/Fixed/Security subsections. Add initial entry for current version.
- **Files to modify**: `CHANGELOG.md` (new)
- **Dependencies**: None
- **Verification**: File exists and follows the format. `grep -c "## \[" CHANGELOG.md` ≥ 2 (Unreleased + current version).
- **Estimated scope**: small

---

### Task 28: Versioning — `--version` and Version Source of Truth
- **Description**: Ensure `docpact --version` reads from `pyproject.toml` `[project].version` (via `importlib.metadata`). All other version references (MCP `serverInfo.version`, reports) derive from this single source. Currently works — verify and lock down.
- **Files to modify**: `src/docpact/cli/main.py`, `src/docpact/mcp_server.py`
- **Dependencies**: None
- **Verification**: `docpact --version` outputs `docpact 0.5.0`. MCP `initialize` response `serverInfo.version` matches. No hardcoded version strings elsewhere.
- **Estimated scope**: small

---

### Task 29: Discovery — Briefing Auto-Regeneration
- **Description**: Ensure `.docpact/briefing.md` auto-regenerates when source files change (fingerprint-based cache). The `obtener_briefing` MCP tool checks the fingerprint and regenerates if stale. Fingerprint tracks `.py` file mtimes.
- **Files to modify**: `src/docpact/briefing.py`, `src/docpact/mcp_server.py`
- **Dependencies**: Task 11
- **Verification**: `pytest tests/test_mcp_tools.py` — modify a fixture file, call `obtener_briefing`, confirm `updated: true` and new content.
- **Estimated scope**: small

---

### Task 30: Verification — TypeScript/JSX Pipeline Alignment
- **Description**: Ensure the TypeScript/JSX verification pipeline (regex-based) matches verification-v1-spec §4.4. Runs: (1) extract CONTRATO from JSDoc, (2) side-effects via regex, (3) dependency check (file existence), (4) RN marker check in comments, (5) RN test checker. No transitive effects, no semantic RN, no signature check.
- **Files to modify**: `src/docpact/checker/ts_checker.py`, `src/docpact/checker/ts_sidefx.py`
- **Dependencies**: None
- **Verification**: `pytest tests/test_ts_parser.py tests/test_ts_sidefx.py` — verify only the 5 specified checks run for TS files, verify no AST-based checks are attempted.
- **Estimated scope**: small

---

### Task 31: Config — Full Schema Alignment
- **Description**: Align `DocpactConfig` with the full schema from verification-v1-spec §9.2 and discovery-v1-spec §4.2. Ensure all documented keys are supported: `strict`, `min_score`, `exclude`, `run_tests`, `types_allowlist`, `side_effects.*`, `rules.rn_prefix`, `warnings.suppress`, `marker_honesty.*`, `rn_patrones.*`, `modules.*`. Unknown keys silently ignored.
- **Files to modify**: `src/docpact/config.py`
- **Dependencies**: Task 17
- **Verification**: `pytest tests/test_config.py tests/test_config_rn_patrones.py` — test loading a full `docpact.toml` with all sections. Test unknown keys are ignored. Test defaults when keys are missing.
- **Estimated scope**: medium

---

### Task 32: Verification — Zero-Friction Introspection
- **Description**: Ensure the "Zero-Friction Introspection" step (verification-v1-spec §4.3 step 4) works: when a CONTRATO is present but `input` or `output` fields are empty, introspect the Python function signature via AST to fill them. This is additive only — never overwrites declared fields.
- **Files to modify**: `src/docpact/checker/signature_checker.py`, `src/docpact/checker/_process_function.py`
- **Dependencies**: Task 1
- **Verification**: `pytest tests/test_orchestrator.py` — test that a CONTRATO with only `side_effects` auto-populates `input` from the function signature. Test that declared fields are never overwritten.
- **Estimated scope**: small

---

### Task 33: Integration — End-to-End Smoke Test
- **Description**: Write an end-to-end test that exercises the full pipeline: (1) create a temp project with `docpact.toml` and `.py` files containing CONTRATOs, (2) run `docpact check`, (3) run `docpact index`, (4) start MCP server and call `tools/list` + `obtener_contexto_funcion`, (5) run `docpact doctor`. Verify exit codes and output at each step.
- **Files to modify**: `tests/test_e2e.py` (new)
- **Dependencies**: Tasks 7, 10, 15, 16, 17, 22, 23
- **Verification**: `pytest tests/test_e2e.py` — full pipeline passes, all exit codes correct, MCP tools return expected shapes.
- **Estimated scope**: large

---

## Implementation Order

```
Phase 1 — Foundation (no dependencies, parallelizable)
├── Task 1:  Contrato v2 semantic fields
├── Task 4:  Parenthesis-aware comma splitting
├── Task 5:  Inline JSON array parsing
├── Task 16: Sentinel project-root detection
├── Task 26: Deprecation warning infrastructure
├── Task 27: CHANGELOG.md structure
├── Task 28: Version source of truth
└── Task 30: TypeScript pipeline alignment

Phase 2 — Core Data Model
├── Task 2:  Parser YAML block scalar support      → T1
├── Task 3:  JSON Schema file                       → T1
├── Task 6:  Structural validation rules            → T1
└── Task 32: Zero-friction introspection            → T1

Phase 3 — Configuration & Discovery
├── Task 17: Config cascade and defaults            → T16
├── Task 31: Full config schema alignment           → T17
└── Task 19: install-mcp + mcp-doctor               → T16

Phase 4 — Verification Pipeline
├── Task 7:  Wire all 13 checkers                   → T6
├── Task 8:  Honest metrics + gate enforcement      → T7
├── Task 9:  Legacy score deprecated                → T8
├── Task 20: CLI validate (pre-commit)              → T7
├── Task 21: CLI lint (static-only)                 → T7
└── Task 22: CLI doctor                             → T7

Phase 5 — MCP Server (18 tools)
├── Task 10: Discovery & Navigation tools (1–6)     → T7
├── Task 11: Project Context tools (7–8)            → T7
├── Task 12: Rule Management tools (9–12)           → T10
├── Task 13: Contract Management tools (13–15)      → T7
├── Task 14: Verification & Reporting tools (16–18) → T7, T9
├── Task 15: Protocol conformance                   → T10–14
└── Task 18: MCP handshake conformance              → T15, T16

Phase 6 — CLI Commands
├── Task 23: CLI index command
├── Task 24: CLI migrate command                    → T17
└── Task 25: Exit code contract audit               → T20–24

Phase 7 — Integration & Polish
├── Task 29: Briefing auto-regeneration             → T11
└── Task 33: End-to-end smoke test                  → T7, T10, T15–17, T22, T23
```

## Notes

- **Backward compatibility is paramount.** Tasks 1–6 extend the parser without breaking existing v1 contracts. The v2 spec explicitly states v1 contracts are valid v2 without modification.
- **MCP server is the largest work item.** The current server has 6 tools; the spec requires 18. Tasks 10–14 can be parallelized once the index is stable.
- **The `migrate` command (Task 24) is forward-looking.** It is only needed when the first MAJOR version ships. Implement the scaffolding now; populate migration logic when v1→v2 breaking changes are defined.
- **Tests exist for most checkers already.** Tasks 7–9 are primarily about wiring and ordering, not writing new checker logic.
- **The deprecation infrastructure (Task 26) should land early** so that `min_score` deprecation warnings are visible throughout development.
- **Risk: MCP tool count.** 18 tools is a large surface area. Consider implementing in sub-batches (6+6+6) with integration tests after each batch.

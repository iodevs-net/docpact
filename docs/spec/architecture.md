# docpact Specification Ecosystem Architecture

> **Spec Version:** 1.0.0  
> **Status:** Stable  
> **Date:** 2026-06-13  
> **Covers:** All 5 specs in the docpact protocol suite

---

## 1. Purpose

This document describes how the five docpact specifications form a coherent protocol ecosystem. It defines the relationships between specs, the dependency graph that governs implementation order, the data contracts that connect them, and the architectural vision that makes docpact more than the sum of its parts.

If you are implementing docpact from scratch, integrating it into a new agent host, or building a compatible tool, this is your map.

---

## 2. The Five Specifications

| # | Spec | Version | Core Question |
|---|------|---------|---------------|
| 1 | **Contrato Format** (`contrato-v2-spec.md`) | 2.0.0 | *What does a contract look like?* |
| 2 | **Verification Protocol** (`verification-v1-spec.md`) | 1.0.0 | *How do we know a contract is honest?* |
| 3 | **MCP Protocol** (`mcp-v2-spec.md`) | 2.0.0 | *How do agents interact with contracts?* |
| 4 | **Auto-Discovery** (`discovery-v1-spec.md`) | 1.0.0 | *How does docpact find a project, and how does a project find docpact?* |
| 5 | **Versioning & Migration** (`versioning-v1-spec.md`) | 1.0.0 | *How does any of this change without breaking users?* |

Each spec is self-contained: an implementer can read one spec and reproduce its behavior in isolation. But the specs are designed to compose — the whole system is greater than any individual spec.

---

## 3. The Protocol Stack

docpact operates as a layered protocol. Each layer depends on the layer below it and is consumed by the layer above it.

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 5: Governance                       │
│              Versioning & Migration (v1)                    │
│     Governs how ALL layers change over time                 │
├─────────────────────────────────────────────────────────────┤
│                    Layer 4: Transport                        │
│              MCP Protocol (v2) + Auto-Discovery (v1)        │
│     How agents find and communicate with docpact            │
├─────────────────────────────────────────────────────────────┤
│                    Layer 3: Verification                     │
│              Verification Protocol (v1)                      │
│     13 checkers, scoring, gates, enforcement                │
├─────────────────────────────────────────────────────────────┤
│                    Layer 2: Representation                   │
│              Contrato Format (v2)                            │
│     Grammar, fields, data model, parsing rules              │
├─────────────────────────────────────────────────────────────┤
│                    Layer 1: Source                            │
│              Python/TypeScript/Go source files               │
│     Functions, classes, docstrings, comments                │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Input | Output | Spec |
|-------|-------|--------|------|
| **1 — Source** | Raw source files | `.py`/`.ts`/`.go` file trees | (host language) |
| **2 — Representation** | Source files with `CONTRATO:` blocks | `Contrato` dataclass instances, `ContratoExtraido` extraction results | Contrato Format |
| **3 — Verification** | `Contrato` instances + source AST | `Hallazgo` findings, `ResultadoProyecto` results, exit codes | Verification Protocol |
| **4 — Transport** | Index + verification results | JSON-RPC tool responses, CLI output, briefing docs | MCP Protocol + Auto-Discovery |
| **5 — Governance** | Any change to layers 1–4 | Compatibility guarantees, migration paths, deprecation warnings | Versioning & Migration |

---

## 4. Dependency Graph

The specs have explicit dependencies. An arrow `A → B` means "B depends on A" — you cannot fully implement B without A.

```
                    ┌──────────────────────┐
                    │  Versioning (v1)      │
                    │  (cross-cutting)      │
                    └──────────┬───────────┘
                               │ governs
          ┌────────────────────┼────────────────────┐
          │                    │                     │
          ▼                    ▼                     ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Contrato Format │  │ Verification    │  │ MCP Protocol    │
│ (v2)            │  │ (v1)            │  │ (v2)            │
│                 │  │                 │  │                 │
│ Defines:        │  │ Consumes:       │  │ Consumes:       │
│ - Grammar       │  │ - Contrato model│  │ - Contrato model│
│ - Fields        │  │ - Field semantics│ │ - Hallazgo      │
│ - Data model    │  │ - side_effects  │  │ - Resultado-*   │
│ - Parsing rules │  │ - rn markers    │  │ - Index format  │
│                 │  │                 │  │                 │
│                 │  │ Defines:        │  │ Defines:        │
│                 │  │ - 13 checkers   │  │ - 18 tools      │
│                 │  │ - Scoring       │  │ - JSON-RPC msgs │
│                 │  │ - Gates         │  │ - Lifecycle     │
│                 │  │ - Hallazgo type │  │ - Error codes   │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                     │
         │                    │                     │
         └────────────┬───────┘                     │
                      │                             │
                      ▼                             │
              ┌──────────────────┐                  │
              │  Auto-Discovery  │◄─────────────────┘
              │  (v1)            │
              │                  │
              │  Consumes:       │
              │  - MCP handshake │
              │  - docpact.toml  │
              │  - Index format  │
              │                  │
              │  Defines:        │
              │  - Sentinel walk │
              │  - Config cascade│
              │  - Integration   │
              │    patterns      │
              └──────────────────┘
```

### Dependency Table

| Spec | Depends On | Depended On By |
|------|-----------|----------------|
| **Contrato Format** | — (foundational) | Verification, MCP, Auto-Discovery |
| **Verification Protocol** | Contrato Format | MCP, Auto-Discovery |
| **MCP Protocol** | Contrato Format, Verification Protocol | Auto-Discovery |
| **Auto-Discovery** | Contrato Format, Verification, MCP | — (leaf) |
| **Versioning & Migration** | — (cross-cutting) | All specs (governance) |

---

## 5. Data Contracts Between Specs

The specs communicate through shared data structures. These are the seams where one spec ends and another begins.

### 5.1 Contrato Format → Verification Protocol

The Contrato Format spec defines the **input** to verification:

| Data Structure | Defined In | Consumed By |
|---------------|-----------|-------------|
| `Contrato` (dataclass) | Contrato Format §6.1 | Verification §3.1 |
| `side_effects` field semantics | Contrato Format §3.2.1 | Verification §6.1, §6.2 |
| `rn` ID format (`RN-\d{3,}`) | Contrato Format §3.2.4 | Verification §6.3, §6.6, §6.8, §6.9 |
| `input` parameter names | Contrato Format §3.2.3 | Verification §6.7 |
| `dependencias` path format | Contrato Format §3.2.6 | Verification §6.4, §6.5 |
| `borde` structure | Contrato Format §3.2.5 | (informational; no checker yet) |
| Semantic fields (`comportamiento`, `asume`, `produce`) | Contrato Format §3.2.7–9 | (agent consumption via MCP) |

**Key contract:** The Contrato Format spec is the **schema authority**. Verification must not reject data that the format spec declares valid, and must not accept data that the format spec declares invalid.

### 5.2 Verification Protocol → MCP Protocol

The Verification Protocol spec defines the **output** that MCP tools surface:

| Data Structure | Defined In | Consumed By |
|---------------|-----------|-------------|
| `Hallazgo` (finding) | Verification §3.3 | MCP tools: `ejecutar_verificacion`, `modificar_archivo`, `validar_cambio` |
| `ResultadoProyecto` (result tree) | Verification §3.4 | MCP tool: `ejecutar_verificacion` |
| Exit codes (0/1/2) | Verification §8.2 | MCP tool: `ejecutar_verificacion` |
| Score and level | Verification §7 | MCP tool: `ejecutar_verificacion` |
| Honest metrics | Verification §7.2 | MCP tool: `generar_reporte` |

**Key contract:** MCP tools are a thin presentation layer over verification. They do not re-implement checkers — they invoke the same `check_proyecto()` / `check_file()` entry points that the CLI uses.

### 5.3 Contrato Format + Verification → MCP Protocol (Index)

The MCP server operates on a pre-computed **index**, not raw source files:

| Index Component | Derived From | Used By |
|----------------|-------------|---------|
| Function metadata (`funcion`, `archivo`, `linea`) | Contrato Format extraction | MCP: `obtener_contexto_funcion`, `navegar_referencias` |
| `rn_ids` per function | Contrato Format `rn` field | MCP: `obtener_rn`, `listar_rns`, `verificar_conflicto` |
| `contrato` object | Contrato Format full parse | MCP: `obtener_contexto_funcion`, `crear_contrato` |
| `tests` file paths | Verification RN test checker | MCP: `validar_cambio`, `ejecutar_tests` |
| Search keywords | Contrato Format field text | MCP: `buscar_por_intencion`, `buscar_rns_por_tema` |
| Semantic embeddings (optional) | FastEmbed on field text | MCP: `buscar_por_intencion`, `verificar_conflicto` |

**Key contract:** The index is a materialized view of Contrato Format data enriched with Verification results. It is regenerated from source — never manually edited.

### 5.4 Auto-Discovery → Everything

Auto-Discovery defines how the system **locates** itself before any other spec can operate:

| Mechanism | Defined In | Used By |
|-----------|-----------|---------|
| Project-root sentinel walk | Discovery §3 | CLI, MCP server, Verification entry points |
| `docpact.toml` config cascade | Discovery §4 | Verification (config), Contrato Format (side-effect patterns) |
| MCP handshake sequence | Discovery §5 | MCP Protocol (lifecycle) |
| Index loading/staleness | Discovery §5.4 | MCP Protocol (server startup) |
| Integration patterns | Discovery §7 | All consumers (CLI, MCP, API, pytest plugin, briefing) |

**Key contract:** Discovery resolves ambiguity before any other spec operates. If discovery fails, every other spec degrades gracefully — not catastrophically.

### 5.5 Versioning → All Specs

The Versioning spec governs how every surface changes:

| Surface | Governed By | Breaking Change Requires |
|---------|-----------|-------------------------|
| Contrato block syntax | Versioning §3.5 | Protocol MAJOR version |
| Verification checker behavior | Versioning §3.3 (API) | Software MAJOR version |
| MCP tool names/schemas | Versioning §3.4 | Software MAJOR version |
| `docpact.toml` config keys | Versioning §3.6 | Software MAJOR version |
| CLI commands/flags | Versioning §3.2 | Software MAJOR version |

**Key contract:** The Contrato Protocol has its own version (currently v2), independent of the software version. A docpact 2.0 release may still operate under Contrato Protocol v2.

---

## 6. The Verification Pipeline in Context

The verification pipeline (Verification §4) is the system's core value proposition. Here is how it connects to every other spec:

```
Source files (Layer 1)
    │
    ▼
Contrato Format parser (Layer 2)
    │  - Extracts CONTRATO: blocks
    │  - Produces Contrato dataclasses
    │  - Uses grammar from Contrato Format §2
    │
    ▼
ContractIndex build (Layer 2→3 bridge)
    │  - All functions, imports, cross-references
    │  - Used by transitive checks, MCP server
    │
    ▼
Per-function checkers (Layer 3)
    │  - 12 checkers in fixed order (Verification §4.3)
    │  - Each checker reads Contrato + source AST
    │  - Produces Hallazgo findings
    │
    ▼
Project-level aggregation (Layer 3)
    │  - RN registry cross-reference
    │  - Module boundary enforcement
    │  - Scoring and honest metrics
    │
    ▼
Results (Layer 3→4 bridge)
    ├── CLI: exit code, printed report (Verification §8)
    ├── MCP: tools/call responses (MCP §7.5)
    ├── Index: .docpact/index.json (Discovery §5.4)
    └── Briefing: .docpact/briefing.md (Discovery §7.5)
```

### Checker Dependency on Contrato Format Fields

| Checker (Verification §6) | Reads From Contrato Format | Field Contract |
|---------------------------|---------------------------|----------------|
| §6.1 Side Effects | `side_effects` | Must be present; `"ninguno"` = empty list |
| §6.2 Transitive Effects | `side_effects` + callee's `side_effects` | Keyword matching with bilingual mappings |
| §6.3 RN Marker (legacy) | `rn` | Each `RN-XXX` must appear as `# RN-XXX` in body |
| §6.4 Dependency | `dependencias` | Path format: `file.ext` or `file.ext::Symbol` |
| §6.5 Inline Import | `dependencias` | Overlap detection with `from X import Y` |
| §6.6 Semantic RN | `rn` | Dispatches to configured validator type |
| §6.7 Signature | `input` | Param names must match function signature |
| §6.8 RN Registry | `rn` | Cross-references against REGISTRO.md |
| §6.9 RN Test | `rn` | Checks `tests/rn/test_rn_XXX.py` exists |
| §6.10 Marker Honesty | `rn` | Detects decorative markers on delegation lines |
| §6.11 Module Boundary | `dependencias` | Respects module allow/forbid rules |
| §6.12 RN Cross-Ref | `rn` | Traces RN propagation across call boundaries |

---

## 7. The MCP Server in Context

The MCP server is the primary interface for AI agents. It consumes all other specs:

```
Agent Host
    │
    │ (Discovery §5: MCP handshake)
    ▼
docpact MCP Server
    │
    ├── initialize (Discovery §5.2)
    │   ├── Resolve project root (Discovery §3)
    │   ├── Load config from docpact.toml (Discovery §4)
    │   └── Load/generate index (Discovery §5.4)
    │
    ├── tools/list (MCP §5.3)
    │   └── Returns 18 tools (MCP §7 + Appendix C)
    │
    ├── tools/call (MCP §5.4)
    │   ├── Discovery tools (MCP §7.1): read from index
    │   ├── Context tools (MCP §7.2): briefing, guard
    │   ├── Rule tools (MCP §7.3): REGISTRO.md operations
    │   ├── Contract tools (MCP §7.4): generate, correct
    │   ├── Verification tools (MCP §7.5): invoke Verification pipeline
    │   └── Reporting tools (MCP §7.6): aggregate metrics
    │
    └── shutdown (MCP §5.5)
```

### Tool-to-Spec Mapping

| MCP Tool Category | Primary Spec Dependency | Secondary |
|-------------------|------------------------|-----------|
| Discovery & Navigation (tools 1–6) | Contrato Format (data model) | — |
| Project Context (tools 7–8) | Verification (guard logic) | Contrato Format |
| Rule Management (tools 9–12) | Contrato Format (RN semantics) | Verification (conflict detection) |
| Contract Management (tools 13–15) | Contrato Format (grammar, fields) | — |
| Verification & Enforcement (tools 3, 16–17) | Verification (checkers, gates) | Contrato Format |
| Reporting (tool 18) | Verification (metrics) | Contrato Format |

---

## 8. Implementation Priorities

Not all specs carry equal weight at every stage. This section defines the recommended implementation order for anyone building docpact from scratch.

### Phase 1: Foundation (Contrato Format)

**Goal:** Parse CONTRATO blocks from source files into structured data.

| Milestone | Spec Section | Effort | Why First |
|-----------|-------------|--------|-----------|
| BNF grammar implementation | Contrato Format §2 | Medium | Everything else reads `Contrato` objects |
| `Contrato` dataclass | Contrato Format §6.1 | Small | Shared data contract for all layers |
| `side_effects` field parsing | Contrato Format §3.2.1 | Small | Only required field; drives verification |
| Full field parsing (v1 fields) | Contrato Format §3.2.2–6 | Medium | Enables all verification checkers |
| Semantic fields (v2) | Contrato Format §3.2.7–9 | Small | Optional; enriches agent context |
| Language-specific embedding | Contrato Format §4.6 | Medium | Python first, then TypeScript, then Go |

**Exit criteria:** `docpact extract .` produces correct `ContratoExtraido` JSON for all test fixtures.

### Phase 2: Verification (Verification Protocol)

**Goal:** Verify that CONTRATOs are honest — that code implements declared contracts.

| Milestone | Spec Section | Effort | Why Second |
|-----------|-------------|--------|------------|
| Side effects checker | Verification §6.1 | Medium | Core value proposition |
| Signature checker | Verification §6.7 | Small | Quick win, high signal |
| Dependency checker | Verification §6.4 | Small | Prevents broken references |
| RN marker checker (legacy) | Verification §6.3 | Small | Bridge until semantic validators |
| Transitive effects checker | Verification §6.2 | Large | Requires ContractIndex |
| Semantic RN validators | Verification §6.6 | Medium | 5 validator types |
| RN registry + test checkers | Verification §6.8–9 | Medium | Completes RN lifecycle |
| Marker honesty checker | Verification §6.10 | Medium | Agent trust signal |
| Module boundary checker | Verification §6.11 | Small | Optional, config-driven |
| Scoring and gates | Verification §7–8 | Medium | CI integration |

**Exit criteria:** `docpact check .` produces correct `ResultadoProyecto` with zero false positives on the test suite.

### Phase 3: Interface (MCP Protocol + Auto-Discovery)

**Goal:** Make contracts accessible to AI agents and CI pipelines.

| Milestone | Spec Section | Effort | Why Third |
|-----------|-------------|--------|-----------|
| Project-root detection | Discovery §3 | Small | Prerequisite for everything |
| `docpact.toml` loading | Discovery §4 | Small | Configuration source |
| Index generation | Discovery §5.4 | Medium | MCP server's data source |
| MCP server skeleton | MCP §2–5 | Medium | JSON-RPC over stdio |
| Discovery tools (1–6) | MCP §7.1 | Medium | Agent reads contracts |
| Verification tools (16–17) | MCP §7.5 | Medium | Agent verifies changes |
| Rule management tools (9–12) | MCP §7.3 | Medium | Agent manages RNs |
| Contract management tools (13–15) | MCP §7.4 | Small | Agent creates contracts |
| Enforcement tools (3, 8) | MCP §7.1, §7.2 | Medium | Agent gates changes |
| Reporting tool (18) | MCP §7.6 | Small | Coverage visibility |
| Briefing generation | Discovery §7.5 | Small | Agent context handoff |
| `install-mcp` + host detection | Discovery §6.6, §7.1 | Small | Frictionless setup |

**Exit criteria:** An agent can discover, read, verify, and manage contracts via MCP without reading source files.

### Phase 4: Governance (Versioning & Migration)

**Goal:** Ensure the system can evolve without breaking users.

| Milestone | Spec Section | Effort | Why Last |
|-----------|-------------|--------|----------|
| Semver enforcement | Versioning §2 | Small | Policy, not code |
| Changelog automation | Versioning §6 | Small | CI integration |
| Deprecation warnings | Versioning §5 | Medium | Requires all surfaces stable |
| `docpact migrate` command | Versioning §4.2 | Medium | First MAJOR release prerequisite |
| Lockfile support | Versioning §4.3 | Small | Optional, but valuable |
| Protocol version negotiation | Versioning §4.4 | Medium | Enables Contrato v3+ |

**Exit criteria:** A user upgrading from one MAJOR version to the next has a working `migrate` command and a clear migration guide.

---

## 9. The Five Pax — Architectural Principles

These principles are not in any single spec. They emerge from the ecosystem as a whole.

### 9.1 Self-Documenting Source

Every `.py` file is both implementation and specification. A CONTRATO block co-located with its function means the contract is always one `git blame` away from its implementation. This is not documentation — it is a machine-parseable assertion about behavior.

**Implication:** The Contrato Format spec defines the grammar. The Verification spec enforces it. The MCP spec exposes it. Discovery finds it. Versioning governs how it changes.

### 9.2 Verification Before Trust

docpact does not trust declarations. A CONTRATO that says `side_effects: ninguno` is a **claim**. The side-effects checker (Verification §6.1) is the **evidence**. The `validar_cambio` MCP tool (MCP §7.1) is the **gate**.

**Implication:** Every layer that consumes CONTRATO data must be prepared for the data to be wrong. The verification layer exists to catch this. MCP tools that surface contract data without running verification are informational, not authoritative.

### 9.3 Graceful Degradation

docpact works without a `docpact.toml` (Discovery §4.5). It works without an index (Discovery §6.3). It works without FastEmbed (Discovery §6.4). It works without REGISTRO.md (Verification §6.8). Every component has a fallback.

**Implication:** No spec may require another spec's output as a hard prerequisite for startup. Verification can run without MCP. MCP can start without verification (it reads the index). Discovery resolves before everything, but falls back to CWD if nothing else works.

### 9.4 Agent-First, Human-Compatible

The primary consumer of docpact is an AI agent — not a human. Contrato blocks are optimized for LLM consumption (structured, unambiguous, minimal prose). MCP tools return machine-parseable JSON. But every MCP output also has a human-readable `resumen` field. CLI output is formatted for terminals.

**Implication:** The MCP spec defines tool schemas. The Contrato Format spec defines the grammar agents parse. Both must be deterministic — no "the server might return this or that" ambiguity.

### 9.5 Independent Evolution

The Contrato Protocol version (currently v2) is independent of the docpact software version (currently 0.1.3). The MCP server version (currently v2.0.0) is independent of both. Each spec has its own semver lifecycle (Versioning §10).

**Implication:** A docpact 2.0 release may still support Contrato Protocol v2. A Contrato Protocol v3 could be introduced in a docpact 1.x MINOR release with backward compatibility. The MCP server can bump its major version independently when tools change.

---

## 10. Cross-Spec Invariants

These invariants hold across all specs simultaneously. Violating any one of them indicates a spec inconsistency.

1. **The `Contrato` dataclass is the universal interchange format.** Every spec that produces or consumes contract data uses the dataclass defined in Contrato Format §6.1. No spec defines its own contract representation.

2. **`side_effects` is the only required field.** This is declared in Contrato Format §3.1, enforced in Verification §6.1, surfaced in MCP tool outputs, and preserved across all versioning changes (Versioning §5.3).

3. **Hallazgo is the universal finding type.** All verification checkers produce `Hallazgo` objects (Verification §3.3). MCP tools that surface verification results serialize Hallazgos. No checker produces a different finding type.

4. **The index is derived, never authored.** `.docpact/index.json` is generated from source files by the indexer. It is never manually created or edited. MCP tools read from it; they never write to it (except `setup_docpact` which triggers regeneration).

5. **Config is optional.** `docpact.toml` is never required (Discovery §4.5). Every config key has a built-in default (Discovery §4.4, Verification §9.2). Unknown keys are silently ignored (Versioning §3.6).

6. **Exit codes are stable.** `0` = success, `1` = verification failure, `2` = usage error (Verification §8.2). Changing these is a MAJOR version bump (Versioning §3.2).

7. **Deprecation precedes removal.** No feature is removed without at least one MINOR release of deprecation warnings (Versioning §5.1). The Contrato Protocol syntax itself MUST NOT be deprecated without a MAJOR version bump (Versioning §5.3).

8. **Thread safety.** Per-file verification is thread-safe (Verification §12.9). The MCP server is single-process but serves requests sequentially. The index is built once and read many times.

---

## 11. Extension Points

The specs define several explicit extension points for future growth.

### 11.1 New Contrato Fields

Adding a new optional field to the Contrato block is a MINOR protocol change (Contrato Format, Versioning §3.5). The parser ignores unrecognized fields. The dataclass gets a new optional field with a default value.

### 11.2 New Verification Checkers

Adding a new checker is a MINOR software change. The per-function pipeline (Verification §4.3) is an ordered list — new checkers are appended. The checker-to-field mapping (Verification §5.3) is extended. No existing checker is affected.

### 11.3 New MCP Tools

Adding a new tool is a MINOR MCP change (MCP §10.2). The tool catalog is static per session but extensible across versions. New tools are added to the end of the catalog.

### 11.4 New Languages

Contrato Format already supports Python, TypeScript, and Go (Contrato Format §4.6). Adding a new language requires:
1. A parser for the host language's comment/docstring syntax.
2. An extractor that finds CONTRATO blocks.
3. Optionally, a verification checker for language-specific constructs.

No changes to existing specs are needed.

### 11.5 New Semantic RN Validator Types

Adding a new validator type (e.g., `rate_limit`, `circuit_breaker`) is a MINOR verification change. The dispatch table (Verification §6.6) is extended. Configuration is additive in `docpact.toml`.

### 11.6 New Integration Patterns

Adding a new integration pattern (e.g., LSP server, GitHub App) is a MINOR discovery change. The integration patterns section (Discovery §7) is extended. No existing patterns are affected.

---

## 12. Security Model

Security concerns span multiple specs:

| Concern | Spec | Mitigation |
|---------|------|-----------|
| File system access | Discovery §8.2 | Server reads only within project root; writes only to `.docpact/` |
| Input validation | MCP §12.4 | RN IDs validated against regex; paths resolved relative to project root |
| Process isolation | Discovery §8.1 | MCP server is a child process; no network exposure |
| Test execution | MCP §12.1 | `pytest` runs in subprocess; timeout enforcement (30s per test, 60s suite) |
| Config trust | Versioning §5.4 | Forced deprecation for security vulnerabilities in config handling |
| Index integrity | Discovery §6.3 | Index is regenerated from source; never trusted across invocations |

The trust boundary is the host process. docpact does not authenticate, authorize, or encrypt — it runs locally with the user's permissions.

---

## 13. Testing Strategy Across Specs

Each spec defines conformance criteria. The testing strategy aligns with them:

| Spec | Conformance Test | How |
|------|-----------------|-----|
| Contrato Format | Parse all examples from §7 | Unit tests for parser + data model |
| Contrato Format | Reject invalid inputs from §8 | Negative tests for edge cases |
| Verification | Run all checkers from §6 against fixtures | Per-checker unit tests |
| Verification | Score calculation matches §7 | Property-based tests (Hypothesis) |
| Verification | Gate enforcement matches §8 | Integration tests with exit codes |
| MCP | All 18 tools return correct schemas | Tool-level integration tests |
| MCP | Lifecycle sequence from §3 | Protocol-level tests |
| Auto-Discovery | Sentinel walk from §3.2 | Unit tests with mock filesystems |
| Auto-Discovery | Config cascade from §4.3 | Config resolution tests |
| Auto-Discovery | Fallbacks from §6 | Degraded-mode tests |
| Versioning | Deprecation lifecycle from §5.1 | Policy tests (assert warnings exist) |
| Versioning | Migration idempotency from §4.2 | Round-trip migration tests |

---

## 14. File Map

Where each spec's rules are implemented in code:

| Spec Section | Implementation File(s) |
|-------------|----------------------|
| Contrato Format §2 (Grammar) | `src/docpact/parser/lexer.py`, `parser.py` |
| Contrato Format §3 (Fields) | `src/docpact/parser/parser.py`, `models/contrato.py` |
| Contrato Format §6 (Data Model) | `src/docpact/models/contrato.py` |
| Verification §4 (Pipeline) | `src/docpact/checker/orchestrator.py` |
| Verification §6.1 (Side Effects) | `src/docpact/checker/side_effects.py` |
| Verification §6.2 (Transitive) | `src/docpact/checker/transitive_effects.py` |
| Verification §6.6 (Semantic RN) | `src/docpact/checker/semantic/` (5 modules) |
| Verification §6.7 (Signature) | `src/docpact/checker/signature_checker.py` |
| Verification §6.10 (Honesty) | `src/docpact/checker/marker_honesty.py` |
| Verification §6.11 (Boundary) | `src/docpact/checker/boundary_checker.py` |
| Verification §7–8 (Scoring/Gates) | `src/docpact/checker/orchestrator.py`, `reporter.py` |
| MCP §5 (Methods) | `src/docpact/mcp_server.py` |
| MCP §7 (Tools) | `src/docpact/mcp_server.py` (18 tool handlers) |
| Discovery §3 (Sentinels) | `src/docpact/config.py`, `cli/main.py` |
| Discovery §4 (Config) | `src/docpact/config.py` |
| Discovery §5 (Handshake) | `src/docpact/mcp_server.py` |
| Discovery §5.4 (Index) | `src/docpact/index.py` |
| Versioning §4.2 (Migrate) | `src/docpact/cli/commands/` (future) |

---

## 15. Glossary

| Term | Definition | Defined In |
|------|-----------|-----------|
| **CONTRATO** | A structured contract block embedded in source file docstrings | Contrato Format §1 |
| **RN** (Regla de Negocio) | A business rule identified by a stable `RN-XXX` ID | Contrato Format §1.2 |
| **Hallazgo** | A single verification finding (error, warning, or info) | Verification §3.3 |
| **Checker** | A function that inspects one aspect of a CONTRATO | Verification §2 |
| **ContractIndex** | A global lookup of all CONTRATOs, built before verification | Verification §2 |
| **Sentinel file** | A file whose presence signals the project root | Discovery §2 |
| **Marker file** | `docpact.toml` — the canonical config and identity file | Discovery §2 |
| **Briefing** | A Markdown summary of project context for agents | Discovery §7.5 |
| **Gate** | A threshold that determines pass/fail for verification | Verification §2 |
| **Semantic field** | Free-text Contrato field describing behavior (`comportamiento`, `asume`, `produce`) | Contrato Format §1.2 |
| **Protocol version** | The Contrato block syntax version (currently v2), independent of software version | Versioning §3.5 |
| **Spec version** | The version of a specification document, independent of software version | Versioning §10 |

---

## Appendix A: Spec Version Matrix

| Spec | Current Version | First Stable | Protocol Version |
|------|----------------|-------------|-----------------|
| Contrato Format | 2.0.0 | 2026-06-13 | v2 |
| Verification Protocol | 1.0.0 | 2026-06-13 | — |
| MCP Protocol | 2.0.0 | 2026-06-13 | MCP 2024-11-05 |
| Auto-Discovery | 1.0.0 | 2026-06-13 | — |
| Versioning & Migration | 1.0.0 | 2026-06-13 | — |

## Appendix B: Data Flow Diagram

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Source Files │────▶│  Contrato Parser  │────▶│  Contrato Model  │
│  (.py/.ts)   │     │  (Format §2)      │     │  (Format §6.1)   │
└──────────────┘     └──────────────────┘     └────────┬─────────┘
                                                        │
                              ┌─────────────────────────┼──────────────────────┐
                              │                         │                      │
                              ▼                         ▼                      ▼
                    ┌──────────────────┐     ┌──────────────────┐   ┌──────────────────┐
                    │  ContractIndex   │     │  Verification    │   │  Index Generator │
                    │  (Verification   │     │  Pipeline        │   │  (Discovery §5.4)│
                    │   §10.2)         │     │  (Verification §4)│  │                  │
                    └────────┬─────────┘     └────────┬─────────┘   └────────┬─────────┘
                             │                        │                      │
                             │                        ▼                      ▼
                             │               ┌──────────────────┐  ┌──────────────────┐
                             │               │  Hallazgo list   │  │  .docpact/       │
                             │               │  Resultado-*     │  │  index.json      │
                             │               │  (Verification §3)│  │                  │
                             │               └────────┬─────────┘  └────────┬─────────┘
                             │                        │                      │
                             └────────────────────────┼──────────────────────┘
                                                      │
                              ┌────────────────────────┼────────────────────────┐
                              │                        │                        │
                              ▼                        ▼                        ▼
                    ┌──────────────────┐     ┌──────────────────┐   ┌──────────────────┐
                    │  CLI             │     │  MCP Server      │   │  Briefing        │
                    │  (Verification §8)│     │  (MCP §5–7)      │   │  (Discovery §7.5)│
                    │  exit code +     │     │  18 tools via    │   │  .docpact/       │
                    │  printed report  │     │  JSON-RPC/stdio  │   │  briefing.md     │
                    └──────────────────┘     └──────────────────┘   └──────────────────┘
```

## Appendix C: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-06-13 | Initial ecosystem architecture. Covers all 5 specs with dependency graph, data contracts, implementation priorities, and architectural principles. |

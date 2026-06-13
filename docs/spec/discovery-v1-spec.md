# docpact Auto-Discovery Specification

> **Spec Version:** 1.0.0
> **Status:** Stable
> **Applies to:** docpact MCP Server, CLI, Python API, and all agent integrations
> **Effective since:** 2026-06-13

---

## 1. Purpose

This specification defines how AI agents and external tools discover and connect to docpact within a software project. It covers four mechanisms: project-root detection via sentinel files, the `docpact.toml` marker file, the MCP server handshake protocol, and fallback behaviors when discovery fails. Every rule here is binding for docpact maintainers, agent host implementors, and tool integrators.

---

## 2. Terminology

| Term | Definition |
|------|------------|
| **agent** | An AI coding assistant (e.g., OMP, Claude Code, Cursor, Aider) that operates on a project's source code. |
| **agent host** | The runtime environment that manages an agent (e.g., Oh My Pi, Claude Code, VS Code). |
| **sentinel file** | A file whose presence in a directory signals that directory is the project root. |
| **marker file** | `docpact.toml` — the canonical configuration and identity file for docpact in a project. |
| **project root** | The top-level directory of a software project, as resolved by §3. |
| **MCP** | Model Context Protocol — the JSON-RPC 2.0 over stdio protocol used for agent-server communication. |
| **MCP server** | The `docpact mcp` process that exposes CONTRATO tools to agents. |
| **CONTRATO** | A structured contract declaration embedded in source file docstrings (see `docs/protocolo-v1.md`). |
| **RN** | Regla de Negocio — a business rule tracked in the project's registry. |
| **index** | The pre-computed JSON index at `.docpact/index.json` containing all CONTRATOs, RNs, and optional embeddings. |

---

## 3. Project-Root Detection

Agents and CLI commands MUST determine the project root before any docpact operation. This section defines the canonical algorithm.

### 3.1 Sentinel Files

docpact recognizes the following sentinel files, checked in order of priority:

| Priority | Sentinel | Why |
|----------|----------|-----|
| 1 | `docpact.toml` | docpact's own marker (§4). Strongest signal. |
| 2 | `REGISTRO.md` | The RN registry file. Present in projects using docpact's RN tracking. |
| 3 | `pyproject.toml` | Standard Python project root (PEP 518). |
| 4 | `.git/` | Git repository root. Universal fallback. |

### 3.2 Algorithm

```
function find_project_root(start_path):
    dir ← start_path
    loop:
        for sentinel in [docpact.toml, REGISTRO.md, pyproject.toml, .git/]:
            if (dir / sentinel) exists:
                return dir
        parent ← parent_directory(dir)
        if parent == dir:          # filesystem root reached
            return start_path      # fallback: CWD
        dir ← parent
```

The search walks upward from the starting path (typically CWD or the file being checked), returning the first directory containing any sentinel. If no sentinel is found after reaching the filesystem root, the starting path itself is returned as a degraded default.

### 3.3 Overrides

The project root MAY be overridden by:

1. **CLI flag**: `--project-root /path/to/project` on any docpact command.
2. **Environment variable**: `DOCPACT_PROJECT_ROOT`. Set by the CLI wrapper before spawning the MCP server (see §5.3).
3. **MCP parameter**: `projectRoot` in the `initialize` request (§5.2).

Priority order: CLI flag > MCP parameter > environment variable > sentinel detection > CWD.

### 3.4 Behavior on Ambiguity

If multiple sentinels exist at different levels (e.g., `pyproject.toml` at `/repo/` and `docpact.toml` at `/repo/services/auth/`), the closest ancestor wins — the first match walking upward from the starting path. This allows monorepos where individual services have their own `docpact.toml`.

---

## 4. The `docpact.toml` Marker File

### 4.1 Role

`docpact.toml` serves two simultaneous roles:

1. **Identity marker**: Its presence declares "this directory is a docpact-enabled project."
2. **Configuration source**: Its contents control docpact's behavior (verification strictness, side-effect patterns, exclusions, module definitions).

### 4.2 Schema

The file uses TOML format with the `[docpact]` top-level table:

```toml
[docpact]
strict = false                   # Require CONTRATOs on all public functions
min_score = 75                   # Minimum passing score (0-100)
exclude = ["tests/", "migrations/", "__pycache__/"]
run_tests = true                 # Execute RN tests during verification

[docpact.side_effects]
db_write = [".create", ".save", ".update", ".bulk_create", ".delete"]
email = ["send_mail", "EmailMessage"]
external = ["requests.", "httpx.", "urllib.request"]
notification = ["_notificar_", "notificar_"]

[docpact.rules]
rn_prefix = "RN-"               # Prefix for business rule identifiers

[docpact.warnings]
suppress = []                    # Warning codes to suppress

[docpact.rn_patrones]           # Per-RN pattern overrides (legacy + semantic)
# RN-001 = { patron = "validar_rut" }

[docpact.marker_honesty]        # Marker honesty enforcement config

[docpact.types_allowlist]       # Type names that never generate warnings

[modules]                        # Module definitions (alternative: modules.toml)
```

### 4.3 Resolution Cascade

When loading configuration, docpact resolves the config file using this cascade:

```
1. Explicit --config <path> argument (CLI only)
2. docpact.toml in the resolved project root
3. .docpact.toml in the resolved project root (hidden file variant)
4. docpact.toml in CWD
5. Built-in defaults (see §4.4)
```

If a `modules.toml` file exists alongside `docpact.toml`, it is loaded and merged, with `docpact.toml` values taking precedence on key conflicts.

### 4.4 Default Behavior

When no `docpact.toml` is found (or it is malformed), docpact operates with these defaults:

| Setting | Default |
|---------|---------|
| `strict` | `false` |
| `min_score` | `75` |
| `exclude` | `["__pycache__", ".venv", "venv", "node_modules", ".git", "migrations", ".pytest_cache", "__init__.py"]` |
| `run_tests` | `true` |
| `side_effects` | Built-in patterns for `db_write`, `email`, `external`, `audit`, `notification` |
| `rn_prefix` | `"RN-"` |

A missing or unreadable `docpact.toml` is NOT an error. The system operates with defaults and logs a notice.

### 4.5 File Not Required

A project MAY use docpact without a `docpact.toml` file. In this case:
- All operations use built-in defaults.
- The sentinel fallback chain uses other sentinels (`REGISTRO.md`, `pyproject.toml`, `.git/`).
- The `docpact doctor` check for "docpact.toml exists" will report a warning, not an error.

---

## 5. MCP Server Handshake

The MCP server communicates over JSON-RPC 2.0 on stdin/stdout. This section defines the handshake sequence that establishes a session between an agent host and docpact.

### 5.1 Transport

- **Protocol**: JSON-RPC 2.0, newline-delimited.
- **Transport**: stdio (stdin for requests, stdout for responses).
- **Logging**: All diagnostic output goes to stderr. The server logs startup diagnostics on every launch, including Python version, docpact path, CWD, resolved project root, and index status.

### 5.2 Handshake Sequence

```
Agent Host                        docpact MCP Server
    │                                     │
    │──── initialize ────────────────────►│
    │     {                               │
    │       "jsonrpc": "2.0",             │
    │       "id": 1,                      │
    │       "method": "initialize",       │
    │       "params": {                   │
    │         "projectRoot": "/abs/path", │  (optional)
    │         "force": false              │  (optional)
    │       }                             │
    │     }                               │
    │                                     │── Resolve project root (§3.3)
    │                                     │── Load or generate index (§5.4)
    │                                     │── Initialize embedder (optional)
    │◄──── response ─────────────────────│
    │     {                               │
    │       "protocolVersion": "2024-11-05",
    │       "capabilities": {"tools": {}},
    │       "serverInfo": {               │
    │         "name": "docpact-mcp",      │
    │         "version": "2.0.0"          │
    │       }                             │
    │     }                               │
    │                                     │
    │──── tools/list ────────────────────►│
    │◄──── response (TOOLS array) ───────│
    │                                     │
    │──── tools/call (any tool) ─────────►│
    │◄──── response ─────────────────────│
    │     ...                             │
    │──── shutdown ──────────────────────►│
    │◄──── response (null) ──────────────│
    │                                     │── Process exits
```

### 5.3 Project-Root Resolution at Handshake

During the `initialize` handler, the server resolves the project root using this priority:

```
1. params.projectRoot  (from the initialize request)
2. $DOCPACT_PROJECT_ROOT  (environment variable)
3. "."  (current working directory)
```

The CLI wrapper (`docpact mcp`) sets `DOCPACT_PROJECT_ROOT` from its `--project-root` argument before launching the server process. Agent hosts MAY also pass `projectRoot` directly in the initialize params.

### 5.4 Index Loading

After resolving the project root, the server loads or generates the index:

```
function load_or_generate_index(project_root, force):
    index_path ← project_root / ".docpact" / "index.json"

    if not force and index_path exists:
        if index_mtime > latest_source_file_mtime:
            regenerate index           # stale: source changed after last index
        else:
            load from disk             # fresh: return cached
    else:
        generate from scratch          # missing or forced

    store index in memory for the session lifetime
```

The index contains:
- All extracted CONTRATOs (function name, file, line, contract fields).
- All RNs from the registry, mapped to implementing functions and tests.
- Search index for keyword matching.
- Optional semantic embeddings (if FastEmbed is installed).

If no `.py` files with CONTRATOs exist, the server still starts successfully with an empty index.

### 5.5 Tool Discovery

After `initialize`, the agent calls `tools/list` to receive the full tool catalog. The response is a static array of 18 tool definitions, each with:
- `name`: Machine-readable identifier.
- `description`: Natural language description guiding the agent on when to use the tool.
- `inputSchema`: JSON Schema defining required and optional parameters.

The tool catalog is constant for the server's lifetime. Tools are not dynamically added or removed based on project state.

### 5.6 Notifications

Messages without an `id` field are JSON-RPC notifications. The server acknowledges them silently (no response). Agent hosts use notifications for lifecycle events (e.g., `initialized`, `exit`) that require no reply.

### 5.7 Error Handling

| Condition | Behavior |
|-----------|----------|
| Unknown method | Respond with error code `-32000`, message `"Unknown method: <name>"` |
| Tool execution failure | Respond with error wrapped in `CallToolResult` format |
| Invalid JSON on stdin | Silently skip the line |
| Index generation failure | Server starts with empty index; tool calls return `{"error": "Índice no cargado"}` |

---

## 6. Fallback Mechanisms

docpact is designed to degrade gracefully at every layer. This section defines explicit fallback behaviors.

### 6.1 Project-Root Fallback

| Situation | Fallback |
|-----------|----------|
| No sentinel files found | Use CWD as project root |
| `--project-root` not specified | Use `DOCPACT_PROJECT_ROOT` env var |
| Env var not set | Use CWD |
| CWD has no `.py` files | Server starts; tools return empty results |

### 6.2 Configuration Fallback

| Situation | Fallback |
|-----------|----------|
| `docpact.toml` not found | Use built-in defaults (§4.4) |
| `docpact.toml` malformed (invalid TOML) | Use built-in defaults; log warning to stderr |
| `modules.toml` not found | Ignore; use only `docpact.toml` modules |
| `modules.toml` malformed | Ignore; use only `docpact.toml` modules |

### 6.3 Index Fallback

| Situation | Fallback |
|-----------|----------|
| `.docpact/index.json` missing | Generate index from source on startup |
| Index stale (source files modified after index) | Auto-regenerate on startup |
| No CONTRATOs found in project | Start with empty index; tools return informative empty responses |
| Index generation raises exception | Start with empty index; log error |

### 6.4 Embedding Fallback

| Situation | Fallback |
|-----------|----------|
| FastEmbed not installed | Keyword-only search; semantic tools still work with reduced accuracy |
| FastEmbed model download fails | Keyword-only search; log warning |
| Embedding dimension mismatch | Ignore embeddings; fall back to keyword search |

The search scoring weights adjust automatically:
- **With embeddings**: `0.7 × semantic_score + 0.3 × keyword_score`
- **Without embeddings**: `1.0 × keyword_score`

### 6.5 MCP Server Fallback

| Situation | Fallback |
|-----------|----------|
| `docpact` binary not in PATH | Agent host cannot spawn the server. `docpact mcp-doctor` reports this. |
| Server process crashes | Agent host detects broken pipe; reconnect logic is host-specific. |
| Server startup timeout (3s) | `docpact install-mcp` refuses to write config, preventing broken installations. |

### 6.6 Host Detection Fallback

When installing the MCP server configuration (`docpact install-mcp`), the installer detects the agent host using this cascade:

| Priority | Detection | Host |
|----------|-----------|------|
| 1 | `~/.omp/` directory exists | OMP (user-level) |
| 2 | `./.omp/` directory exists | OMP (project-level) |
| 3 | `~/.claude/mcp/` directory exists | Claude Code (user-level) |
| 4 | `./.mcp.json` file exists | Generic project-level MCP |
| 5 | None match | `"unknown"` — installer reports error and suggests manual setup |

---

## 7. Integration Patterns

This section defines how agent hosts integrate with docpact. Each pattern is self-contained.

### 7.1 Pattern A: MCP Server (Primary)

The recommended integration. The agent host spawns docpact as an MCP subprocess and communicates via JSON-RPC over stdio.

**Setup:**

```bash
# One-time: install docpact and generate the index
pip install docpact
docpact index

# One-time: register the MCP server with the agent host
docpact install-mcp
```

**Runtime flow:**

```
1. Agent host spawns: docpact mcp --project-root /path/to/project
2. Agent host sends: initialize → server loads index, responds with capabilities
3. Agent host sends: tools/list → receives 18 tool definitions
4. During coding, agent calls tools/call → server responds with contract context
5. Agent host sends: shutdown → server exits cleanly
```

**Generated config (OMP host):**

```json
{
  "$schema": "https://raw.githubusercontent.com/can1357/oh-my-pi/main/.../mcp-schema.json",
  "mcpServers": {
    "docpact": {
      "command": "/path/to/wrapper",
      "args": ["--project-root", "/path/to/project"]
    }
  }
}
```

**Generated config (Claude Code / generic host):**

```json
{
  "mcpServers": {
    "docpact": {
      "type": "stdio",
      "command": "/path/to/wrapper",
      "args": ["mcp", "--project-root", "/path/to/project"]
    }
  }
}
```

### 7.2 Pattern B: CLI Verification (CI/CD)

For automated pipelines that verify contracts without an agent.

**Setup:**

```bash
pip install docpact
```

**Usage:**

```bash
# Verify all CONTRATOs in a project
docpact check . --config docpact.toml

# Generate the index for MCP or caching
docpact index

# Run the doctor (full ecosystem health check)
docpact doctor
```

**GitHub Actions:**

```yaml
- name: Verify contracts
  run: docpact check . --config docpact.toml --min-score 75
```

**Pre-commit hook:**

```yaml
- id: docpact
  name: docpact check
  entry: docpact check . --config docpact.toml
  language: system
  types: [python]
  stages: [pre-commit]
```

### 7.3 Pattern C: Python API (Programmatic)

For tools that embed docpact logic directly.

```python
from docpact.api import extract_contratos, verify_contratos

# Extract all CONTRATOs from a directory
contratos = extract_contratos(Path("./src"))

# Verify against source code
results = verify_contratos(Path("./src"), config=DocpactConfig.desde_toml("docpact.toml"))
```

### 7.4 Pattern D: Pytest Plugin (Testing)

docpact registers itself as a pytest plugin via the `pytest11` entry point. When installed, it provides markers and fixtures for RN testing:

```python
import pytest

@pytest.mark.rn("RN-001")
def test_validar_rut():
    assert validar_rut("12345678-9") is True
```

The plugin activates automatically when docpact is installed. No configuration beyond `docpact.toml` is needed.

### 7.5 Pattern E: Briefing (Agent Context)

For agents that benefit from reading project context before coding, docpact generates a briefing file at `.docpact/briefing.md`. The briefing contains:
- Active RNs and their implementing functions.
- Side-effect declarations per module.
- Risk zones (functions with complex side effects).
- Fingerprint for cache invalidation (tracks `.py` file mtimes).

The briefing auto-regenerates when source files change. Agents can read it directly or call the `obtener_briefing` MCP tool.

### 7.6 Pattern F: Diagnostic (Troubleshooting)

When integration fails, `docpact mcp-doctor` reports the environment state:

```
docpact MCP doctor

  Python:        3.12.0
  docpact in PATH: /usr/local/bin/docpact
  Project root:  /home/user/myproject
  Index:         /home/user/myproject/.docpact/index.json [EXISTS]

OK — entorno listo para MCP
```

The diagnostic checks:
1. Python executable is accessible.
2. `docpact` binary is in PATH.
3. `DOCPACT_PROJECT_ROOT` is set (if applicable).
4. `.docpact/index.json` exists.

The `--json` flag outputs machine-readable diagnostics for automated troubleshooting.

---

## 8. Security Considerations

### 8.1 Process Isolation

The MCP server runs as a child process of the agent host. It inherits the host's environment and file permissions. It does not open network ports, authenticate users, or escalate privileges.

### 8.2 File System Access

The server reads source files within the project root for index generation. It writes only to:
- `.docpact/index.json` — the pre-computed index.
- `.docpact/briefing.md` and `.docpact/briefing.meta.json` — the agent briefing.

It never modifies source files, configuration, or system files.

### 8.3 Input Validation

All JSON-RPC input is parsed with strict JSON decoding. Malformed messages are silently dropped. Tool arguments are validated against their JSON Schema before dispatch.

---

## 9. Conformance

### 9.1 Agent Host Requirements

An agent host conforming to this specification:

1. MUST spawn the MCP server with the correct project root (via `--project-root` or `DOCPACT_PROJECT_ROOT`).
2. MUST send `initialize` as the first request.
3. MUST call `tools/list` before invoking any tool.
4. MUST send `shutdown` before terminating the server process.
5. SHOULD handle server errors gracefully (retry is not required; the agent may inform the user).
6. SHOULD run `docpact mcp-doctor` or equivalent health check if the server fails to start.

### 9.2 Server Requirements

The MCP server conforming to this specification:

1. MUST resolve the project root using the priority chain in §5.3.
2. MUST load or generate the index before accepting tool calls.
3. MUST respond to `initialize` with `protocolVersion`, `capabilities`, and `serverInfo`.
4. MUST expose exactly the tools listed in `TOOLS` (18 tools as of this spec version).
5. MUST NOT crash on missing `docpact.toml`, missing index, or empty projects.
6. MUST log startup diagnostics to stderr.
7. MUST NOT write to stdout outside of JSON-RPC responses.

### 9.3 Marker File Requirements

A `docpact.toml` file conforming to this specification:

1. MUST use the `[docpact]` top-level table for core settings.
2. MUST use TOML format parseable by Python's `tomllib` (Python 3.11+).
3. SHOULD include only recognized keys; unrecognized keys are silently ignored.
4. MAY be empty or contain only comments — this is valid and equivalent to using defaults.

---

## 10. Versioning

This specification is versioned independently of the docpact software (see `docs/spec/versioning-v1-spec.md`).

| Spec Version | Meaning |
|--------------|---------|
| **1.0.0** | Initial stable release. Covers sentinel detection, `docpact.toml` schema, MCP handshake, fallbacks, and 6 integration patterns. |

Changes to this spec follow the same semver rules as the software:
- **MAJOR**: Breaking change to the handshake protocol, marker schema, or sentinel priority.
- **MINOR**: New optional integration patterns, new optional config keys, new fallback behaviors.
- **PATCH**: Clarifications, typo fixes, examples.

---

## Appendix A: Complete Sentinel Walk Example

Given this directory tree:

```
/workspace/
  pyproject.toml
  services/
    auth/
      docpact.toml
      src/
        login.py      ← agent opens this file
```

If an agent opens `login.py` and calls `find_project_root`:

1. Start at `/workspace/services/auth/src/`.
2. Check `docpact.toml` → not found.
3. Check `REGISTRO.md` → not found.
4. Check `pyproject.toml` → not found.
5. Check `.git/` → not found.
6. Move to `/workspace/services/auth/`.
7. Check `docpact.toml` → **found**. Return `/workspace/services/auth/`.

The `pyproject.toml` at `/workspace/` is never reached. The monorepo service gets its own docpact scope.

---

## Appendix B: MCP Server Capabilities Response

```json
{
  "protocolVersion": "2024-11-05",
  "capabilities": {
    "tools": {}
  },
  "serverInfo": {
    "name": "docpact-mcp",
    "version": "2.0.0"
  }
}
```

The `capabilities.tools` object is empty because tools are discovered via `tools/list`, not declared in capabilities. This follows the MCP specification.

---

## Appendix C: Full Tool Catalog (18 tools)

| # | Tool | Purpose |
|---|------|---------|
| 1 | `obtener_contexto_funcion` | Get full context (CONTRATO, RNs, tests) for a function |
| 2 | `buscar_por_intencion` | Search functions by natural-language intent (semantic + keyword) |
| 3 | `validar_cambio` | Validate a diff against CONTRATOs and run relevant tests |
| 4 | `obtener_rn` | Get full context for a specific business rule |
| 5 | `buscar_rns_por_tema` | Search RNs by topic or keyword |
| 6 | `navegar_referencias` | Navigate cross-references (RN→functions, file→functions, function→calls) |
| 7 | `obtener_briefing` | Get the project's business-rule briefing |
| 8 | `modificar_archivo` | Pre-modification validation against CONTRATOs |
| 9 | `listar_rns` | List all RNs with status and implementing functions |
| 10 | `verificar_conflicto` | Check if a new RN conflicts with existing ones |
| 11 | `crear_rn` | Create a new RN in the registry |
| 12 | `explicar_rn` | Explain an RN in plain language |
| 13 | `setup_docpact` | Initialize docpact in a project (create config, generate index) |
| 14 | `crear_contrato` | Generate a CONTRATO docstring for a function |
| 15 | `corregir_contrato` | Diagnose and suggest fixes for a broken CONTRATO |
| 16 | `ejecutar_verificacion` | Run full CONTRATO verification |
| 17 | `ejecutar_tests` | Run RN tests via pytest |
| 18 | `generar_reporte` | Generate an RN coverage report |

---

## Appendix D: `docpact.toml` Minimal Example

```toml
# This file is all you need. Everything else uses sensible defaults.
[docpact]
strict = false
min_score = 75
```

## Appendix E: `docpact.toml` Full Example

```toml
[docpact]
strict = true
min_score = 80
exclude = ["tests/", "migrations/", "__pycache__/", "scripts/"]
run_tests = true

[docpact.side_effects]
db_write = [".create", ".save", ".update", ".bulk_create", ".delete", ".raw"]
email = ["send_mail", "EmailMessage", "send_mass_mail"]
external = ["requests.", "httpx.", "urllib.request", "aiohttp."]
audit = ["registrar_evento_bitacora", "log_action"]
notification = ["_notificar_", "notificar_", "send_push"]
cache = [".cache.set", ".cache.delete", "redis_client."]

[docpact.rules]
rn_prefix = "RN-"

[docpact.warnings]
suppress = ["W-SE-001"]

[docpact.marker_honesty]
enabled = true

[docpact.types_allowlist]
"None"
"bool"
"str"
"int"
"float"

[modules]
"soporte" = { path = "soporte/", description = "Módulo de soporte técnico" }
"facturacion" = { path = "facturacion/", description = "Módulo de facturación" }
```

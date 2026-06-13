# docpact Versioning and Migration Specification

> **Spec Version:** 1.0.0
> **Status:** Stable
> **Applies to:** docpact CLI, Python API, MCP Server, Contrato Protocol, and configuration
> **Effective since:** 2026-06-13

---

## 1. Purpose

This document defines how docpact versions its software, what compatibility guarantees each component provides, how users migrate between versions, when and how features are deprecated, and how changes are communicated. Every rule here is binding for maintainers and contributors.

---

## 2. Semantic Versioning

docpact follows [Semantic Versioning 2.0.0](https://semver.org/) strictly. The version string is `MAJOR.MINOR.PATCH`, with an optional pre-release suffix.

### 2.1 Version Components

| Component | Incremented when | Examples |
|-----------|------------------|----------|
| **MAJOR** | A breaking change is introduced to any public surface (see §3). Users MUST read the migration guide before upgrading. | Removing a CLI command, changing `Contrato` field names, altering `docpact.toml` schema incompatibly. |
| **MINOR** | A backward-compatible feature is added. Existing workflows, configurations, and contracts continue to work without modification. | Adding a new CLI command, adding an optional `Contrato` field, adding a new MCP tool. |
| **PATCH** | A backward-compatible bug fix. No new features, no deprecations. | Fixing a parser false positive, correcting a report calculation, fixing a crash on edge-case input. |

### 2.2 Pre-release Versions

Pre-release versions use the suffix `-alpha.N`, `-beta.N`, or `-rc.N`:

| Stage | Stability guarantee |
|-------|---------------------|
| `alpha` | Unstable. APIs may change between alpha releases without notice. Not for production CI pipelines. |
| `beta` | Feature-complete but not finalized. APIs are unlikely to change but may. Safe for testing. |
| `rc` | Release candidate. Only critical bug fixes from this point. Safe for staging. |

Pre-release versions do NOT carry the compatibility guarantees in §3. The first stable release of a MAJOR version (e.g., `2.0.0`) is the point at which guarantees activate.

### 2.3 Version Source of Truth

The canonical version lives in `pyproject.toml` under `[project].version`. All other locations (CLI `--version`, MCP server metadata, reports) derive from this single source at build time. The CLI exposes it via:

```bash
docpact --version
# docpact 0.5.0
```

---

## 3. Compatibility Guarantees

docpact exposes five public surfaces. Each has its own compatibility contract.

### 3.1 Surface Inventory

| Surface | Description | Defined in |
|---------|-------------|------------|
| **CLI** | `docpact` command and all subcommands | `src/docpact/cli/` |
| **Python API** | `extract_file()`, `verify_contratos()`, `run_checks()`, and all public symbols in `docpact.*` | `src/docpact/api.py`, `src/docpact/models/` |
| **MCP Server** | Resources and tools exposed to AI agents | `src/docpact/mcp_server.py` |
| **Contrato Protocol** | `CONTRATO:` block syntax, field names, semantics | `docs/protocolo-v1.md` |
| **Configuration** | `docpact.toml` schema, field names, defaults | `src/docpact/config.py` |

### 3.2 CLI Compatibility

**MAJOR:** Removing or renaming a command, removing or renaming a flag, changing the meaning of an existing flag, or changing the output format of `--json` / machine-readable modes.

**MINOR:** Adding a new command, adding a new flag (with a default that preserves existing behavior), adding a new output format.

**PATCH:** Fixing error messages, fixing exit codes to match documentation, correcting help text.

**Stability rules:**

- Every command MUST have a stable exit code contract: `0` = success, `1` = verification failure, `2` = usage error. New exit codes MAY be added in MINOR releases but MUST NOT change existing meanings.
- The `--config` flag path resolution logic is stable: it searches `./docpact.toml`, then `$XDG_CONFIG_HOME/docpact/config.toml`, then the built-in defaults, in that order. Changing this order is a MAJOR change.
- Output written to stdout in non-`--json` mode (human-readable) is NOT a stability contract. Formatting may change in MINOR releases.

### 3.3 Python API Compatibility

**MAJOR:** Removing or renaming a public class/function, removing or renaming a field on a dataclass, changing a function's required parameters, changing a return type.

**MINOR:** Adding a new public function, adding an optional parameter with a default, adding a new field to a dataclass (with a default value), adding a new enum member.

**PATCH:** Performance improvements, docstring fixes, internal refactors that do not alter observable behavior.

**Stability rules:**

- All dataclasses in `src/docpact/models/contrato.py` (`Contrato`, `ContratoExtraido`, `CampoInput`, `SideEffect`, `ReglaNegocio`, `CasoBorde`, `Dependencia`, `ErrorParser`) are public API. Field additions MUST have defaults so existing call sites do not break.
- The `from __future__ import annotations` import is structural. Tools that rely on runtime type introspection should use `typing.get_type_hints()`.
- Internal modules (`docpact._internal`, `docpact.checker.*` implementation details) are NOT public API. They may change in PATCH releases.

### 3.4 MCP Server Compatibility

**MAJOR:** Removing a resource or tool, changing the schema of a resource or tool input/output, changing the MCP protocol version supported.

**MINOR:** Adding a new resource or tool, adding optional fields to an existing resource schema, adding a new MCP capability.

**PATCH:** Fixing resource content, correcting tool descriptions, performance improvements.

**Stability rules:**

- Resource URIs (e.g., `contrato://...`) are stable identifiers. Changing URI patterns is a MAJOR change.
- Tool names exposed via MCP are stable. Renaming is a MAJOR change.
- The JSON-LD `@context` URL is stable within a MAJOR version.

### 3.5 Contrato Protocol Compatibility

The Contrato Protocol (the `CONTRATO:` block syntax in source files) has its own versioning, currently at v1. Protocol versioning is independent of docpact software versioning.

**MAJOR (Protocol):** Removing a required field, changing field semantics, changing the marker syntax (`CONTRATO:`, `//`, `///`).

**MINOR (Protocol):** Adding an optional field, adding a new marker style, relaxing parsing rules (accepting input that was previously rejected).

**PATCH (Protocol):** Clarifying ambiguous wording in the spec, fixing example code.

**Stability rules:**

- A docpact MAJOR release MAY introduce support for a new Protocol MAJOR version, but MUST continue to parse the previous Protocol version. The protocol version is declared in the `CONTRATO:` block header or inferred from the docpact configuration.
- Users' existing `CONTRATO:` blocks MUST NOT need modification when upgrading docpact within the same Protocol version.
- When a new Protocol version is introduced, the parser MUST accept both old and new syntax during the transition period (minimum one MAJOR docpact release cycle).

### 3.6 Configuration Compatibility

**MAJOR:** Removing a config key, changing the type of a config key, changing the default value of a config key in a way that alters behavior.

**MINOR:** Adding a new config key (with a backward-compatible default), adding a new section.

**PATCH:** Fixing config validation error messages, correcting default documentation.

**Stability rules:**

- Unknown config keys MUST be silently ignored (not errors). This allows forward-compatible config files.
- `docpact.toml` is the canonical config format. The schema is:

```toml
[docpact]
strict = false
min_score = 75
exclude = []

[docpact.side_effects]
# Custom patterns per category

[docpact.rules]
rn_prefix = "RN-"

[docpact.marker_honesty]
enabled = true
max_rns_per_function = 5

[docpact.runtime]
modo = "strict"
```

- Adding new sections or keys under `[docpact.*]` is a MINOR change.

---

## 4. Migration Paths

### 4.1 Migration Guide Requirement

Every MAJOR release MUST include a `docs/migration/vX.md` file that covers:

1. **What changed** — exhaustive list of breaking changes with before/after examples.
2. **Why it changed** — the design rationale for each breaking change.
3. **Automated migration** — if a `docpact fix` or `docpact migrate` command can handle the upgrade, the guide documents it.
4. **Manual steps** — any changes that require human judgment.
5. **Rollback** — how to revert if the upgrade causes problems.

### 4.2 The `docpact migrate` Command

Starting with the first MAJOR version that requires migration, docpact provides a `migrate` command:

```bash
docpact migrate --from 0.x --to 1.0
```

**Behavior:**

- Reads the current project's docpact version from the lockfile or `pyproject.toml`.
- Applies all pending migrations in order (0.x → 1.0, 1.0 → 2.0, etc.).
- Rewrites `docpact.toml` to the new schema, preserving user values.
- Updates `CONTRATO:` blocks if the Protocol version changed.
- Prints a summary of every file modified.
- Dry-run mode (`--dry-run`) shows what would change without writing.

**Constraints:**

- The migrate command is idempotent: running it twice produces no additional changes.
- It NEVER deletes user data. If a migration cannot be automated, it leaves the original in place with a `# TODO: docpact migrate` comment and reports it.
- Migrations are additive: the command for `0.x → 2.0` runs `0.x → 1.0` then `1.0 → 2.0`.

### 4.3 Lockfile

docpact MAY introduce a `.docpact-lock.json` file in the project root that records:

```json
{
  "version": "1.0.0",
  "protocol_version": "1",
  "migrations_applied": ["0.x-to-1.0"],
  "last_check": "2026-06-13T12:00:00Z"
}
```

This file is optional. If absent, `docpact migrate` infers the version from the installed package and the presence/absence of config keys.

### 4.4 Protocol Version Negotiation

When docpact encounters a `CONTRATO:` block:

1. If the block declares a protocol version (e.g., `CONTRATO:v2:`), docpact uses the corresponding parser.
2. If no version is declared, docpact assumes the latest stable protocol version.
3. If the detected syntax is ambiguous, docpact falls back to Protocol v1 and emits a warning.

This ensures that files written for older protocol versions continue to parse correctly after a docpact upgrade.

---

## 5. Deprecation Policy

### 5.1 Deprecation Lifecycle

A feature goes through four stages before removal:

```
Active → Deprecated → Scheduled → Removed
```

| Stage | Duration | User-visible behavior |
|-------|----------|----------------------|
| **Active** | Until deprecation is announced. | Feature works normally. |
| **Deprecated** | Minimum one MINOR release. | Feature works but emits a deprecation warning (stderr or log). The warning names the replacement and the version where removal is scheduled. |
| **Scheduled** | Minimum one MINOR release after Deprecated. | Feature works, warning is now an error in `--strict` mode. |
| **Removed** | Next MAJOR release after Scheduled. | Feature is gone. Upgrading without addressing deprecations is a breaking change. |

**Minimum timeline:** A feature announced as deprecated in version `X.Y.0` cannot be removed before version `X+1.0.0`. This guarantees at least one full MINOR release cycle (and typically more) of warning.

### 5.2 Deprecation Warning Format

All deprecation warnings follow a consistent format:

```
DEPRECATED: '<feature>' is deprecated since docpact X.Y and will be removed in X+1.0.
  Use '<replacement>' instead.
  See: https://docpact.dev/migration/vX+1
```

For CLI flags:

```
WARNING: --old-flag is deprecated and will be removed in docpact 2.0. Use --new-flag instead.
```

For Python API:

```python
import warnings
warnings.warn(
    "old_function() is deprecated since docpact 1.2 and will be removed in 2.0. "
    "Use new_function() instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

For MCP tools:

```json
{
  "content": [
    {
      "type": "text",
      "text": "WARNING: tool 'old_tool' is deprecated. Use 'new_tool' instead. Removal in docpact 2.0."
    }
  ]
}
```

### 5.3 What May Be Deprecated

The following MAY be deprecated through the standard lifecycle:

- CLI commands and flags
- Python API functions, classes, and fields
- MCP tools and resources
- Configuration keys and sections
- Contrato Protocol fields (Protocol-level deprecation)

The following MUST NOT be deprecated without a MAJOR version bump:

- The `CONTRATO:` block syntax itself
- Required `side_effects` field in the Contrato Protocol
- The `docpact check` command (core workflow)
- The `docpact.toml` config file location

### 5.4 Forced Deprecation (Security)

In rare cases where a feature has a security vulnerability, the deprecation lifecycle MAY be compressed:

- The feature is removed in the next PATCH release.
- The release notes clearly mark this as a security-forced removal.
- A migration path is provided in the same release.

---

## 6. Changelog Format

docpact maintains a `CHANGELOG.md` file following [Keep a Changelog](https://keepachangelog.com/) format.

### 6.1 Structure

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security

## [1.2.0] - 2026-07-15

### Added
- New `docpact migrate` command for automated upgrades between major versions.
- MCP server now exposes a `contrato_diff` tool for comparing contract changes.

### Changed
- `docpact check` now exits with code 2 (instead of 1) for usage errors,
  distinguishing them from verification failures.

### Deprecated
- `--legacy-format` flag on `docpact extract`. Use `--format=json` instead.
  Removal scheduled for docpact 2.0.

### Fixed
- Parser no longer crashes on `CONTRATO:` blocks inside triple-quoted strings
  that contain escaped quotes.

## [1.1.0] - 2026-06-30
...
```

### 6.2 Entry Rules

| Rule | Requirement |
|------|-------------|
| **One entry per change.** | If a commit touches three things, there are three entries. |
| **User-facing only.** | Internal refactors, CI changes, and test-only updates are omitted unless they affect behavior. |
| **Link to issue/PR.** | Every entry ends with `(#NNN)` linking to the tracking issue or PR. |
| **Migration note.** | Breaking changes in MAJOR releases link to the migration guide: `See [migration guide](docs/migration/vX.md).` |
| **Grouped by type.** | Entries are grouped under the six categories: Added, Changed, Deprecated, Removed, Fixed, Security. |
| **Ordered by impact.** | Within each group, the most impactful entries come first. |

### 6.3 Categories

| Category | When to use |
|----------|-------------|
| **Added** | New features, new commands, new config options, new MCP tools. |
| **Changed** | Changes to existing behavior that are backward-compatible. |
| **Deprecated** | Features that still work but will be removed. MUST include the removal version. |
| **Removed** | Features deleted in this release. MUST include the replacement or migration path. |
| **Fixed** | Bug fixes. |
| **Security** | Vulnerability fixes. MAY be the only entry in a PATCH release that skips other categories. |

### 6.4 Release Cadence

- **PATCH releases** are published as needed, typically within days of a confirmed bug.
- **MINOR releases** follow a monthly cadence when there are features to ship.
- **MAJOR releases** are planned with at least one month of advance notice. The deprecation warnings in the preceding MINOR releases serve as this notice.

### 6.5 Unreleased Section

The `[Unreleased]` section at the top of `CHANGELOG.md` accumulates changes between releases. When a version is cut:

1. All entries under `[Unreleased]` move to the new version heading with the release date.
2. `[Unreleased]` is reset to empty section headers.
3. The version heading links to the git tag: `## [1.2.0] - 2026-07-15`.

---

## 7. Git Tags and Releases

| Artifact | Format | Example |
|----------|--------|---------|
| Git tag | `vMAJOR.MINOR.PATCH` | `v1.2.0` |
| GitHub Release | Created from tag, body = changelog section | — |
| PyPI release | Built from tag by CI | `docpact-1.2.0.tar.gz` |

Pre-release tags use the same format with suffix: `v1.2.0-beta.1`. PyPI pre-releases use the PEP 440 convention: `1.2.0b1`.

---

## 8. Support Windows

| Version | Status | Support |
|---------|--------|---------|
| Current MAJOR | Active | Full support: features, bug fixes, security. |
| Previous MAJOR | Maintenance | Security fixes and critical bugs only. Minimum 6 months after the current MAJOR is released. |
| Older | End of life | No updates. Users should upgrade. |

Example: when docpact 2.0.0 is released, 1.x enters maintenance. When 3.0.0 is released, 1.x reaches end of life.

---

## 9. Guarantees Summary

| Guarantee | Applies to | Breaking change requires |
|-----------|-----------|-------------------------|
| CLI commands and flags are stable | CLI | MAJOR version |
| Python API signatures and dataclass fields are stable | Python API | MAJOR version |
| MCP tool/resource names and schemas are stable | MCP Server | MAJOR version |
| `CONTRATO:` block syntax is parseable | Contrato Protocol | Protocol MAJOR version |
| `docpact.toml` keys are not removed | Configuration | MAJOR version |
| Unknown config keys are ignored | Configuration | Never (permanent) |
| Exit codes 0/1/2 are stable | CLI | MAJOR version |
| Deprecation warnings precede removal by ≥ 1 MINOR | All surfaces | N/A (enforced by policy) |
| Migration guide exists for every MAJOR release | Process | N/A (enforced by policy) |

---

## 10. Versioning This Specification

This specification is itself versioned. The version in the header (`Spec Version: 1.0.0`) tracks changes to the versioning rules. Amendments to this spec:

- **Clarifications** (fixing ambiguity without changing rules): PATCH to spec version.
- **New sections** (adding policy for a new surface): MINOR to spec version.
- **Changed rules** (altering guarantees or timelines): MAJOR to spec version, with a one-release grace period before enforcement.

The spec version is independent of the docpact software version. docpact 2.0 may still operate under Spec Version 1.0.0 if no rules changed.

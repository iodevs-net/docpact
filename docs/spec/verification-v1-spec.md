# docpact Verification Protocol Specification

> **Spec Version:** 1.0.0
> **Status:** Stable
> **Applies to:** `docpact check`, `docpact lint`, `docpact validate`, `docpact verify-rn`, Python API (`check_file`, `check_proyecto`), MCP Server verification tools
> **Effective since:** 2026-06-13

---

## 1. Purpose

This document specifies the verification protocol that docpact uses to validate `CONTRATO:` blocks against actual source code. It defines every checker, the pipeline that orchestrates them, the error taxonomy, the scoring system, the gate enforcement logic, and the configuration schema. This spec is self-contained: an implementer can reproduce the verification behavior from this document alone.

---

## 2. Terminology

| Term | Definition |
|------|------------|
| **CONTRATO** | A structured block inside a function's docstring that declares inputs, outputs, side effects, business rules, edge cases, and dependencies in a machine-parseable format. |
| **Checker** | A function that inspects one aspect of a CONTRATO against the source code and produces zero or more findings. |
| **Hallazgo** | A single verification finding — the universal output type of all checkers. |
| **Pipeline** | The ordered sequence of checkers executed per function and per project. |
| **Gate** | A threshold that determines whether verification passes (exit 0) or fails (exit 1). |
| **REGISTRO.md** | The canonical registry of all business rules (RNs) in the project. Lives at the project root. |
| **ContractIndex** | A global index of all CONTRATOs in the project, built before verification, used for cross-reference and transitive analysis. |
| **RN** | Regla de Negocio — a business rule identified by a prefixed ID (default: `RN-XXX`). |
| **Semantic RN Validator** | A pluggable checker configured in `docpact.toml` under `[docpact.rn_patrones]` that validates a specific RN using structural code analysis. |

---

## 3. Data Model

### 3.1 Input: `Contrato`

The parsed contract extracted from a function's docstring. All fields are optional except where noted.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `input` | `dict[str, CampoInput]` | No | Parameters declared with name, type, and description. |
| `output` | `str` | No | Return type and description. |
| `output_descripcion` | `str` | No | Narrative description of the output. |
| `side_effects` | `list[str]` | **Yes** | Declared side effects. `"ninguno"` for pure functions. |
| `rn` | `list[ReglaNegocio]` | No | Business rules implemented, each with `id` (e.g. `RN-010`) and `descripcion`. |
| `borde` | `list[CasoBorde]` | No | Edge cases, each with `condicion` and `comportamiento`. |
| `dependencias` | `list[Dependencia]` | No | External dependencies, each with a `ref` string (e.g. `models/ticket.py::Ticket`). |

### 3.2 Intermediate: `ErrorParser`

A raw finding produced by individual checkers before promotion to `Hallazgo`.

| Field | Type | Description |
|-------|------|-------------|
| `campo` | `str` | Category field (see §5.2). |
| `mensaje` | `str` | Human-readable description of the issue. |
| `linea` | `int` | Source line number where the issue was detected. |
| `sugerencia` | `str` | Actionable fix suggestion. |

### 3.3 Output: `Hallazgo`

The universal finding type. Every checker's output is normalized to this structure.

| Field | Type | Description |
|-------|------|-------------|
| `tipo` | `str` | Severity: `"error"`, `"warning"`, or `"info"`. |
| `campo` | `str` | Category (see §5.2). |
| `funcion` | `str` | Function name where the finding was detected. |
| `archivo` | `str` | File path. |
| `linea` | `int` | Source line number. |
| `mensaje` | `str` | Human-readable description. |
| `sugerencia` | `str` | Actionable fix suggestion (may be empty). |

### 3.4 Result Hierarchy

Results form a nested tree:

```
ResultadoProyecto
├── archivos: list[ResultadoArchivo]
│   ├── funciones: list[ResultadoFuncion]
│   │   ├── nombre: str
│   │   ├── tiene_contrato: bool
│   │   ├── contrato: Contrato | None
│   │   ├── hallazgos: list[Hallazgo]
│   │   └── codigo_funcion: str
│   ├── archivo: str
│   └── total_errores / total_warnings (derived)
├── rns_fake: list          # RNs declared in code but not in REGISTRO.md
├── rns_huerfanas: list     # RNs in REGISTRO.md but not in any CONTRATO
├── rns_placeholders: list  # Placeholder RN IDs (RN-XXX, RN-NO-APLICA)
└── config: DocpactConfig
```

---

## 4. Verification Pipeline

### 4.1 Entry Points

| Entry Point | Scope | Description |
|-------------|-------|-------------|
| `check_proyecto(path, config, diff_only)` | Project | Full project verification. Scans directory, runs all checkers, computes cross-references. |
| `check_file(path, config, index)` | File | Single-file verification. Parses AST, extracts docstrings, runs per-function pipeline. |
| `docpact check` | CLI | Invokes `check_proyecto()`, enforces gates, prints report. |
| `docpact lint` | CLI | Same as `check` but static-only (no pytest). |
| `docpact validate` | CLI | Pre-commit hook: verifies only staged files. |
| `docpact verify-rn` | CLI | Verifies RN patterns exist in source code. |

### 4.2 Project-Level Pipeline

`check_proyecto()` executes in the following order:

```
1. Scan
   Walk the directory tree, collecting .py, .ts, .tsx, .jsx files.
   Apply exclusion patterns from config.exclude.
   If diff_only=True, filter to files changed vs HEAD (git diff).

2. Build ContractIndex
   Parse ALL project files (not just changed ones when diff_only).
   Extract all CONTRATOs and imports into a global lookup table.
   ImportResolver resolves relative imports, qualified names, and
   ambiguous short names.

3. Per-File Verification (parallel)
   Spawn ThreadPoolExecutor(max_workers=4).
   For each file, call check_file() with the shared ContractIndex.
   Errors in one file do not stop other files.

4. RN Registry Cross-Reference
   Parse REGISTRO.md at project root.
   Compare all CONTRATOs against the registry:
   - rns_fake: RNs declared in code but absent from REGISTRO.md
   - rns_huerfanas: RNs in REGISTRO.md but not declared in any CONTRATO
   - rns_placeholders: Sentinel values (RN-XXX, RN-NO-APLICA)

5. RN Cross-Reference
   If function A declares RN-XXX and calls function B, and B also
   declares RN-XXX, verify that B has # RN-XXX marker in its body.
   Only warns when the destination function ALSO declares the same RN.

6. Module Boundary Check
   If config.modules is non-empty, enforce dependency rules between
   modules. For each function with dependencies, verify the dependency
   module is allowed (and not forbidden) per the modules config.

7. Suppression
   Apply warning suppression patterns from config.warnings_suppress.
   Any Hallazgo whose mensaje contains a suppression pattern is removed.
```

### 4.3 Per-Function Pipeline

`procesar_funcion()` executes for every public function (names not starting with `_`):

```
1. Skip private functions (name starts with _).

2. Extract docstring.
   If no docstring: register as function without CONTRATO.
   If strict mode: emit error (campo=presencia).
   Return early.

3. Parse CONTRATO.
   Tokenize docstring → parse tokens into Contrato dataclass.
   Collect any parse errors as warnings.

4. Zero-Friction Introspection (conditional).
   If CONTRATO is present but input or output fields are empty,
   introspect the Python function signature via AST to fill them.
   This allows minimal CONTRATOs that only declare side_effects + rn.

5. Determine if CONTRATO is substantive.
   A CONTRATO is substantive if it declares at least one of:
   side_effects, rn, input, or output.
   A CONTRATO: marker with no fields is also considered present.

6. Run checkers (ordered sequence):
   a. Side Effects (§6.1)
   b. Transitive Side Effects (§6.2)
   c. RN Marker Check (§6.3) [LEGACY, warning only]
   d. Dependency Check (§6.4)
   e. Inline Import Check (§6.5)
   f. Semantic RN Validation (§6.6)
   g. Signature Check (§6.7)
   h. RN Registry Check (§6.8)
   i. RN Test Check (§6.9)

7. Suppression.
   Filter out Hallazgos matching config.warnings_suppress patterns.

8. Append ResultadoFuncion to ResultadoArchivo.
```

### 4.4 TypeScript/JSX Pipeline

For `.ts`, `.tsx`, `.jsx` files, a separate regex-based pipeline runs:

1. Extract CONTRATO blocks from JSDoc comments using regex.
2. Run side-effects check using regex pattern matching (not AST).
3. Run dependency check (file existence only, no symbol resolution).
4. Run RN marker check in comments.
5. Run RN test checker.

TypeScript verification is less precise than Python (no AST) and does not support transitive effects, semantic RN validation, or signature checking.

---

## 5. Error Taxonomy

### 5.1 Severity Levels

| Level | Meaning | Gate Impact |
|-------|---------|-------------|
| `error` | The CONTRATO contradicts the implementation. Must be fixed. | Counts toward error gate. Blocks CI. |
| `warning` | A potential issue or inconsistency. Should be reviewed. | Counts toward warning gate. Does not block CI by default. |
| `info` | Informational. No action required but worth noting. | No gate impact. |

### 5.2 Field Categories (`campo`)

| Category | Description | Default Error Weight | Default Warning Weight |
|----------|-------------|---------------------|----------------------|
| `presencia` | Missing CONTRATO on a public function (strict mode only). | 12 | — |
| `side_effects` | Side-effect declaration mismatch: declared effects don't match actual code behavior. | 15 | 5 |
| `rn` | RN marker presence: declared RN-XXX not found as a comment in function body. | 10 | 3 |
| `rn_tests` | RN test file missing or placeholder test detected. | 20 | — |
| `rn_semantica` | Semantic RN validator failure: the code does not structurally implement the rule. | 10 (default) | — |
| `dependencias` | Dependency file or symbol not found. | 5 | 2 |
| `test_quality` | Placeholder or trivial test detected (assert True, empty body). | 10 (default) | — |

### 5.3 Checker-to-Field Mapping

| Checker | Fields Produced | Typical Severity |
|---------|-----------------|------------------|
| Side Effects (§6.1) | `side_effects` | error if effects undeclared; warning if declared but not detected |
| Transitive Effects (§6.2) | `side_effects` | error (contract falsification) |
| RN Marker (§6.3) | `rn` | warning (legacy) |
| Dependency (§6.4) | `dependencias` | error |
| Inline Import (§6.5) | `dependencias` | warning |
| Semantic RN (§6.6) | `rn_semantica` | error |
| Signature (§6.7) | `presencia` | warning |
| RN Registry (§6.8) | `rn` | info (if registry not found) |
| RN Test (§6.9) | `rn_tests` | error (missing test); warning (placeholder) |
| Marker Honesty (§6.10) | `rn` | warning |
| Module Boundary (§6.11) | `dependencias` | error |
| RN Cross-Reference (§6.12) | `rn` | warning |

---

## 6. Checkers

### 6.1 Side Effects Checker

**Purpose:** Verify that the `side_effects` field in the CONTRATO matches the actual side effects produced by the function's code.

**Method:** AST walker extracts all function calls within the function body. Each call is classified against configurable pattern categories from `docpact.toml`.

**Default Pattern Categories:**

| Category | Patterns |
|----------|----------|
| `db_write` | `.create`, `.save`, `.update`, `.bulk_create`, `.delete`, `.bulk_update`, `.get_or_create` |
| `email` | `send_mail`, `EmailMessage` |
| `external` | `requests.`, `httpx.`, `urllib.request` |
| `audit` | `registrar_evento_bitacora` |
| `notification` | `_notificar_`, `notificar_` |

**Pattern Matching Rules:**
- Patterns starting with `.` use word-boundary matching (`\.save\b`) to avoid false positives (e.g. `updated_at` matching `.update`).
- Patterns without a leading `.` use exact substring matching.
- Patterns are compiled to `re.Pattern` once at config load time.

**Error Conditions:**

| Condition | Severity | Message Pattern |
|-----------|----------|-----------------|
| Declared `side_effects: ninguno` but real effects detected | error | `"declara 'ninguno' pero se detectaron efectos: {categories}"` |
| Declared specific effects but no matching calls found AND function is not a delegator | warning | `"declara efectos pero no se detectaron llamadas"` |

**Delegator Detection:** A function that contains method calls (`ast.Call` with `ast.Attribute`) is considered a delegator/passthrough. No warning is emitted when a delegator declares effects but shows no direct calls — the calls happen through delegation.

**Configuration:**

```toml
[docpact.side_effects]
db_write = [".create", ".save", ".update"]
email = ["send_mail", "EmailMessage"]
custom_category = ["my_function", "my_other_function"]
```

Custom categories are merged with defaults. Patterns are additive per category.

---

### 6.2 Transitive Side Effects Checker

**Purpose:** When function A calls function B, and B has a CONTRATO declaring side effects, verify that A's `side_effects` declaration covers B's effects.

**Method:**
1. Extract all function calls in the body via AST.
2. Resolve each call through the `ContractIndex` (which maps call names to their CONTRATOs via import resolution).
3. For each callee with a CONTRATO, check if the caller's `side_effects` declaration semantically covers the callee's effects.

**Semantic Matching (`_satisface_efecto`):** Coverage is determined by keyword matching with bilingual mappings:

| Caller Declares | Callee Has | Match? |
|-----------------|-----------|--------|
| `"actualiza BD"` | `db_write` | Yes — "actualiza" + "BD" map to `db_write` |
| `"envia email"` | `email` | Yes — "envia" + "email" map to `email` |
| `"ninguno"` | Any effect | **No** — always fails |

**Error Conditions:**

| Condition | Severity |
|-----------|----------|
| Caller declares `ninguno` but calls function with real effects | error |
| Caller's declaration does not cover callee's effect category | error |

**Skip Condition:** If caller declares `service_delegation` in side_effects, transitive checking is skipped (the function explicitly delegates all effects).

---

### 6.3 RN Marker Check (LEGACY)

**Purpose:** Verify that each `RN-XXX` ID declared in the CONTRATO's `rn` field appears as a `# RN-XXX` comment in the function body.

**Status:** LEGACY — deprecated since T02 Phase A. Scheduled for removal. Semantic RN validators (§6.6) replace this check with structural validation.

**Method:** Extracts comments from the raw source text (not AST, which discards comments). Matches `# RN-XXX` patterns. Supports formats: `RN-XXX`, `RN-SEG-005`, `Gotcha #NNN`.

**Severity:** Always `warning` with `[LEGACY]` prefix in message. The suggestion includes guidance to configure a semantic validator in `docpact.toml`.

---

### 6.4 Dependency Checker

**Purpose:** Verify that each dependency declared in the CONTRATO's `dependencias` field exists as a real file and symbol.

**Method:**
1. For each `Dependencia.ref` (e.g. `models/ticket.py::Ticket`):
   a. Resolve the module path relative to the file, then relative to the project root.
   b. Verify the file exists (with `.py` suffix variants).
   c. If a symbol is specified (after `::`), parse the target module's AST and verify the symbol exists. Supports qualified names (`Clase.metodo`).

**Error Conditions:**

| Condition | Severity |
|-----------|----------|
| Module file not found | error |
| Symbol not found in target module | error |

---

### 6.5 Inline Import Checker

**Purpose:** Detect `from X import Y` statements inside a function body where `Y` is already declared as a CONTRATO dependency. This prevents AI agents from accidentally removing module-level imports thinking the CONTRATO replaces them.

**Method:** Parse function body source for `from ... import ...` statements. Check if imported names overlap with declared dependency symbols.

**Severity:** Always `warning`. Message: `"NO eliminar el import — el CONTRATO no reemplaza imports"`.

---

### 6.6 Semantic RN Validators

**Purpose:** Validate that a declared RN is structurally implemented in the code, not just mentioned in a comment.

**Dispatch:** Each RN declared in the CONTRATO is routed to its configured validator type from `[docpact.rn_patrones]` in `docpact.toml`. If no validator is configured for an RN, an `info` Hallazgo is emitted guiding the user to configure one.

#### 6.6.1 `has_pattern`

**Purpose:** Generic string/pattern presence check in the function body.

**Configuration:**

```toml
[docpact.rn_patrones.RN-010]
type = "has_pattern"
patron = "is_superuser"       # Simple string
# OR: patron = "is_admin|is_superuser"  # Pipe = OR
```

**Behavior:** Searches the function body for the literal string. If the pattern contains `|`, splits on `|` and checks for any match.

#### 6.6.2 `state_transition`

**Purpose:** Validate that a state machine transition exists in the code.

**Configuration:**

```toml
[docpact.rn_patrones.RN-004]
type = "state_transition"
source = "transiciones.yaml"    # YAML file with transitions matrix
# OR: source = "inline"         # Read from function body (AST dict literal)
```

**Behavior:** Reads the transition matrix from the specified source (YAML file or AST dict literal in the function body). Verifies that the declared `from → to` transition exists in the matrix.

#### 6.6.3 `no_import`

**Purpose:** Detect forbidden imports.

**Configuration:**

```toml
[docpact.rn_patrones.RN-020]
type = "no_import"
patterns = ["os.system", "subprocess.call"]
en_archivo = "services/*.py"    # Optional: restrict to matching files
```

**Behavior:** AST-based check for prohibited import statements. If `en_archivo` is specified, only applies to files matching the glob pattern.

#### 6.6.4 `required_groups`

**Purpose:** Verify that group/permission authorization checks exist.

**Configuration:**

```toml
[docpact.rn_patrones.RN-010]
type = "required_groups"
allowed = ["is_superuser", "has_perm"]
forbidden = ["is_anonymous"]
```

**Behavior:** Checks the function body for authorization patterns (`groups.filter`, `is_superuser`, `has_perm`, or patterns in `allowed`). Fails if no check is detected. Also fails if any `forbidden` pattern is found.

#### 6.6.5 `tenant_safe`

**Purpose:** Detect unsafe multi-tenant patterns.

**Configuration:**

```toml
[docpact.rn_patrones.RN-030]
type = "tenant_safe"
forbid = [".objects.all()", ".objects.filter()"]
```

**Behavior:** AST-based attribute matching. Detects calls like `Model.objects.all()` without a tenant filter. The `forbid` list specifies patterns that are unsafe without tenant scoping.

---

### 6.7 Signature Checker

**Purpose:** Verify that the `input` parameters declared in the CONTRATO match the actual Python function signature.

**Method:** Compare CONTRATO input parameter names against the AST function signature. Omits `self` and `cls`. Detects virtual parameters from `kwargs.pop()` or `kwargs.get()` calls in the body.

**Warning Conditions:**

| Condition | Direction | Severity |
|-----------|-----------|----------|
| CONTRATO declares parameter not in real signature | CONTRATO → code | warning |
| Real parameter not declared in CONTRATO | code → CONTRATO | warning |

**Zero-Friction Mode:** If the CONTRATO is present but `input` or `output` is empty, `introspectar_firma()` extracts parameter names and return type annotations from the AST to fill the gaps. This is NOT a verification — it's a supplementation that allows minimal CONTRATOs.

---

### 6.8 RN Registry Check

**Purpose:** Verify RNs declared in CONTRATOs exist in the project's canonical REGISTRO.md.

**Method:** Load REGISTRO.md at project root. For each RN declared in a CONTRATO, check if it exists in the registry.

**Severity:** `info` if REGISTRO.md does not exist (cross-reference is optional). Findings are aggregated at the project level as `rns_fake`, `rns_huerfanas`, and `rns_placeholders`.

---

### 6.9 RN Test Checker

**Purpose:** Verify that each `RN-XXX` declared in a CONTRATO has a corresponding test file at `tests/rn/test_rn_XXX.py` and that the test is substantive.

**Checks:**
1. **File existence:** `tests/rn/test_rn_XXX.py` must exist.
2. **Test execution (optional):** If `config.run_tests` is `True`, run pytest on each test file.
3. **Test quality:** Detect placeholder tests — empty body, no asserts, trivial asserts like `assert True`.

**Error Conditions:**

| Condition | Severity |
|-----------|----------|
| Test file missing | error |
| Test file exists but contains only placeholder tests | warning (`campo=test_quality`) |

---

### 6.10 Marker Honesty Checker

**Purpose:** Detect decorative `# RN-XXX` markers placed on delegation lines where the function does not actually implement the rule.

**Method:** For each `# RN-XXX` comment in the function body, check if the comment is on a delegation line (e.g., `return Service.method()`, `x = Service.method()`). Distinguishes real implementation (ORM calls, field assignment) from delegation.

**Exclusions:** ORM methods (`.save`, `.create`, `.filter`, etc.) and cache methods are not considered delegation — markers on these lines are honest.

**Concentration Check:** If a function has more than `marker_honesty_max_rns` (default: 5) RN markers, a warning is emitted.

**Severity:** Always `warning`.

**Configuration:**

```toml
[docpact.marker_honesty]
enabled = true
max_rns_per_function = 5
```

---

### 6.11 Module Boundary Checker

**Purpose:** Enforce dependency rules between project modules.

**Method:** For each function with declared dependencies, determine the source module and dependency module from file paths. Check against the `modules` config for allowed/forbidden module pairs.

**Severity:** `error` if a dependency crosses a forbidden boundary.

**Configuration:**

```toml
[modules.services]
allowed = ["models", "utils"]
forbidden = ["views"]

[modules.views]
allowed = ["models", "services"]
```

Also loadable from a separate `modules.toml` file in the same directory as `docpact.toml`.

---

### 6.12 RN Cross-Reference Checker

**Purpose:** Verify that when function A declares `RN-XXX` and calls function B which also declares `RN-XXX`, function B has `# RN-XXX` as a comment in its body.

**Method:** Build a function map from all verified results. For each function with RNs, trace its calls. If the callee also declares the same RN, verify the marker exists in the callee's body.

**Scope:** Only warns when the destination function ALSO declares the same RN. This prevents false positives when a function calls code that doesn't claim to implement the rule.

**Severity:** `warning`.

---

### 6.13 Doctor (Self-Diagnosis)

**Purpose:** Verify the docpact ecosystem itself is properly configured.

**Checks (7 total):**

| Check | What It Verifies |
|-------|-----------------|
| CI workflow | `.github/workflows/` contains a docpact job |
| Pre-commit | `.pre-commit-config.yaml` includes docpact |
| Score threshold | `min_score` is configured in docpact.toml |
| RN registry | `REGISTRO.md` exists at project root |
| Test placeholders | No `assert True` or empty test bodies in `tests/rn/` |
| docpact version | Installed version matches project expectations |
| FastEmbed | `fastembed` package is available for semantic features |

---

## 7. Scoring

### 7.1 Legacy Score (DEPRECATED)

> **Deprecated since 2026-06-02.** This score is a "vanity metric" — it does not predict bugs avoided or real quality. Use Honest Metrics (§7.2) instead. Retained for backward compatibility with existing integrations.

**Formula:** `score = max(0, 100 - penalty_sin_contrato - penalty_errores - penalty_warnings)`

| Component | Calculation | Cap |
|-----------|-------------|-----|
| Missing contracts | `min(30, (sin_contrato / total) * 50)` | 30 |
| Weighted errors | `min(40, sum(PESOS_ERROR[h.campo] for h in errors))` | 40 |
| Weighted warnings | `min(15, sum(PESOS_WARNING[h.campo] for h in warnings))` | 15 |

**Error Weights (`PESOS_ERROR`):**

| Campo | Weight |
|-------|--------|
| `rn_tests` | 20 |
| `side_effects` | 15 |
| `presencia` | 12 |
| `rn` | 10 |
| `dependencias` | 5 |
| *(default)* | 10 |

**Warning Weights (`PESOS_WARNING`):**

| Campo | Weight |
|-------|--------|
| `side_effects` | 5 |
| `rn` | 3 |
| `dependencias` | 2 |
| *(default)* | 3 |

**Level Thresholds:**

| Score Range | Level | Label |
|-------------|-------|-------|
| 90–100 | L4 | AI-Optimized |
| 75–89 | L3 | AI-Native |
| 50–74 | L2 | AI-Friendly |
| 25–49 | L1 | AI-Aware |
| 0–24 | L0 | Human-Native |

### 7.2 Honest Metrics (RECOMMENDED)

The recommended quality signal. Derived from RN registry cross-reference.

| Metric | Description |
|--------|-------------|
| `rns_fake` | Count of RNs declared in CONTRATOs but absent from REGISTRO.md. Agents inventing rules. |
| `rns_huerfanas` | Count of RNs in REGISTRO.md but not declared in any CONTRATO. Rules without implementation. |
| `rns_placeholders` | Count of placeholder RN IDs (RN-XXX, RN-NO-APLICA). Stubs never completed. |
| `funciones_sin_contrato` | Public functions missing a CONTRATO. |
| `funciones_totales` | Total public functions found. |
| `score_legacy` | The deprecated score, included for transition. |

---

## 8. Gate Enforcement

### 8.1 CLI Gates

The `docpact check` command enforces gates in this order:

| Gate | Flag | Default | Exit Code |
|------|------|---------|-----------|
| RNs fake | `--max-rns-fake` | `0` | `1` if `rns_fake > max_rns_fake` |
| RNs huerfanas | `--max-rns-huerfanas` | `None` (disabled) | `1` if `rns_huerfanas > max_rns_huerfanas` |
| Legacy score | `--min-score` (DEPRECATED) | `75` | `1` if `score < min_score` |
| Errors present | *(always on)* | — | `1` if `total_errores > 0` |
| Strict mode missing contracts | `--strict` | `false` | `1` if strict and any function lacks CONTRATO |

### 8.2 Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Verification passed. All gates satisfied. |
| `1` | Verification failed. One or more gates exceeded. |
| `2` | Usage error (invalid arguments, config file not found). |

### 8.3 Pre-commit Behavior

`docpact validate` runs a fast subset:
- Only processes staged files (git diff --cached).
- Static analysis only (no pytest).
- Fails if any staged file has CONTRATOs that contradict implementation.
- Target latency: < 1 second.

---

## 9. Configuration

### 9.1 File Location

Configuration is loaded from `docpact.toml` (or `.docpact.toml`) in the project root. The search order:

1. `--config` flag (explicit path)
2. `{path}/docpact.toml`
3. `{path}/.docpact.toml`
4. `{cwd}/docpact.toml`
5. Built-in defaults (no config file)

Unknown keys are silently ignored (forward-compatible).

### 9.2 Full Schema

```toml
[docpact]
strict = false                    # If true, missing CONTRATO on public functions = error
min_score = 75                    # DEPRECATED: minimum legacy score gate
exclude = [                       # Paths to exclude from analysis
    "tests/", "migrations/", "__pycache__/",
    ".venv", "venv", "node_modules", ".git",
    ".pytest_cache", "__init__.py"
]
run_tests = true                  # Execute pytest for RN test verification
types_allowlist = []              # Type names that never generate warnings

[docpact.rules]
rn_prefix = "RN-"                 # Prefix for business rule IDs

[docpact.side_effects]            # Side-effect pattern categories
db_write = [".create", ".save", ".update", ".bulk_create", ".delete"]
email = ["send_mail", "EmailMessage"]
external = ["requests.", "httpx.", "urllib.request"]
audit = ["registrar_evento_bitacora"]
notification = ["_notificar_", "notificar_"]
# Custom categories can be added:
# my_category = ["pattern1", "pattern2"]

[docpact.warnings]
suppress = []                     # Message substrings to suppress (glob-style)

[docpact.marker_honesty]
enabled = true                    # Enable marker honesty detection
max_rns_per_function = 5          # Warn if a function has more than N RN markers

[docpact.rn_patrones]             # Semantic RN validators
# Each key is an RN ID. Each value has 'type' and validator-specific fields.

[docpact.rn_patrones.RN-010]
type = "required_groups"
allowed = ["is_superuser", "has_perm"]

[docpact.rn_patrones.RN-004]
type = "state_transition"
source = "transiciones.yaml"

[docpact.rn_patrones.RN-020]
type = "no_import"
patterns = ["os.system"]

[docpact.rn_patrones.RN-030]
type = "tenant_safe"
forbid = [".objects.all()"]

[docpact.rn_patrones.RN-050]
type = "has_pattern"
patron = "validate_token"

[modules]                         # Module boundary rules (also loadable from modules.toml)
[modules.services]
allowed = ["models", "utils"]
forbidden = ["views"]
```

### 9.3 Pattern Matching Semantics

**Side-effect patterns:**
- Patterns starting with `.`: compiled as `\.<escaped_pattern>\b` (word-boundary match on method calls).
- Patterns without `.`: compiled as exact substring match.
- All patterns are case-sensitive.
- Patterns are compiled once at config load and reused across all files.

**Suppression patterns:**
- Simple substring match against `Hallazgo.mensaje`.
- Any Hallazgo whose message contains a suppression string is removed.

**Exclude patterns:**
- Exact match on path components (directory names).
- Patterns ending with `*` match as prefix on path components.
- Non-directory files are excluded if their suffix is not in `.py, .ts, .tsx, .jsx`.

### 9.4 Semantic Validator Type Summary

| Type | Required Fields | Optional Fields |
|------|----------------|-----------------|
| `has_pattern` | `patron` | — |
| `state_transition` | `source` | — |
| `no_import` | `patterns` | `en_archivo` |
| `required_groups` | — | `allowed`, `forbidden` |
| `tenant_safe` | — | `forbid` |

---

## 10. Parallelism and Performance

### 10.1 Thread Pool

Per-file verification runs in `ThreadPoolExecutor(max_workers=4)`. File order is non-deterministic (uses `as_completed`). Errors in one file do not halt other files.

### 10.2 ContractIndex

Built once before parallel verification begins. Contains:
- All CONTRATOs indexed by `(module, function_name)`.
- All imports resolved via `ImportResolver` (AST visitor).
- Ambiguity detection: if the same short name maps to multiple modules, it's flagged as ambiguous and excluded from transitive resolution.

### 10.3 Diff-Only Mode

When `diff_only=True`:
- Only files changed vs `HEAD` (via `git diff`) are verified.
- The ContractIndex is still built from ALL project files (for transitive analysis).
- If no files changed, returns empty result immediately.

### 10.4 Framework Name Filtering

The ContractIndex filters generic framework method names (`save`, `create`, `delete`, `filter`, `update`, `get`, `all`, `first`, `last`, `count`, `exists`, `none`, `values`, `values_list`) from the short-name index to prevent false transitive matches.

---

## 11. Python API

### 11.1 Public Functions

```python
from docpact.api import check_file, check_proyecto, extract_contratos

# Single file
resultado: ResultadoArchivo = check_file("path/to/file.py", config)

# Full project
resultado: ResultadoProyecto = check_proyecto("path/to/project/", config, diff_only=False)

# Extract without verification
contratos: list[ContratoExtraido] = extract_contratos("path/to/file.py")
```

### 11.2 Result Inspection

```python
resultado = check_proyecto(".", config)

# Counts
resultado.total_funciones       # int: all public functions found
resultado.funciones_con_contrato # int: functions with valid CONTRATO
resultado.total_errores          # int: error-severity Hallazgos
resultado.total_warnings         # int: warning-severity Hallazgos
resultado.total_archivos         # int: files with at least one function

# Scoring
resultado.calcular_score()       # int: 0-100 (DEPRECATED)
resultado.nivel                  # str: "L0" through "L4"
resultado.metricas_honestas()    # dict: rns_fake, rns_huerfanas, etc.

# Per-file detail
for archivo in resultado.archivos:
    for func in archivo.funciones:
        func.nombre              # str
        func.tiene_contrato      # bool
        func.contrato            # Contrato | None
        func.hallazgos           # list[Hallazgo]
```

---

## 12. Invariants

The following invariants hold at all times during and after verification:

1. **Hallazgo immutability.** A `Hallazgo` is never mutated after creation. Suppression removes entries from lists; it does not modify them.

2. **Checker independence.** Each checker operates on the CONTRATO and source code independently. No checker reads another checker's output. Checker execution order does not affect individual results.

3. **Error accumulation.** A single function may produce multiple Hallazgos from multiple checkers. All are collected before suppression.

4. **Suppression is last.** Warning suppression is applied exactly once, after all checkers have run. It is never applied mid-pipeline.

5. **Private function exclusion.** Functions with names starting with `_` are never verified. They do not appear in results.

6. **ContractIndex freshness.** The ContractIndex is built from the current source tree at verification time. It is never cached across invocations.

7. **Score monotonicity.** The legacy score is monotonically non-increasing with respect to errors and warnings. More findings always mean a lower or equal score.

8. **Gate ordering.** Gates are checked in the order: rns_fake → rns_huerfanas → min_score → errors → strict. The first failing gate determines the exit code; remaining gates are still evaluated for reporting.

9. **Thread safety.** Per-file verification is thread-safe. Each `check_file()` call receives its own `ResultadoArchivo` and does not mutate shared state.

10. **Zero-Friction is additive only.** The introspection step fills missing `input`/`output` fields. It never overwrites fields that the CONTRATO already declares.

---

## 13. Conformance

An implementation is conformant with this specification if:

1. It executes all checkers described in §6 in the order specified in §4.3.
2. It produces `Hallazgo` objects with the fields defined in §3.3.
3. It computes the legacy score as defined in §7.1 and honest metrics as defined in §7.2.
4. It enforces gates as defined in §8.1.
5. It loads configuration from `docpact.toml` as defined in §9.2, with unknown keys silently ignored.
6. It respects the invariants in §12.
7. It uses exit codes as defined in §8.2.

---

## Appendix A: Checker Execution Order

The complete ordered list of checkers as executed per function:

| Order | Checker | Section | Scope | Required |
|-------|---------|---------|-------|----------|
| 1 | Side Effects | §6.1 | Per-function | Yes |
| 2 | Transitive Side Effects | §6.2 | Per-function | Yes (requires ContractIndex) |
| 3 | RN Marker (LEGACY) | §6.3 | Per-function | Yes (warning only) |
| 4 | Dependency | §6.4 | Per-function | Yes |
| 5 | Inline Import | §6.5 | Per-function | Yes |
| 6 | Semantic RN | §6.6 | Per-function | Yes (dispatches to configured validators) |
| 7 | Signature | §6.7 | Per-function | Yes |
| 8 | RN Registry | §6.8 | Per-function | Yes (degrades gracefully) |
| 9 | RN Test | §6.9 | Per-function | Yes (requires config.run_tests) |
| 10 | Marker Honesty | §6.10 | Per-function | Conditional (config.marker_honesty.enabled) |
| 11 | Module Boundary | §6.11 | Per-project | Conditional (config.modules non-empty) |
| 12 | RN Cross-Reference | §6.12 | Per-project | Yes (requires ContractIndex) |
| 13 | Doctor | §6.13 | Standalone | No (separate command) |

## Appendix B: Default Exclusion Set

Files and directories excluded from analysis by default:

```
__pycache__, .venv, venv, node_modules, .git,
migrations, .pytest_cache, __init__.py
```

## Appendix C: CLI Command Summary

| Command | Purpose | Static/Dynamic | Files |
|---------|---------|----------------|-------|
| `docpact check` | Full verification | Both (pytest optional) | All project files |
| `docpact lint` | Static analysis only | Static | All project files |
| `docpact validate` | Pre-commit hook | Static | Staged files only |
| `docpact verify-rn` | RN pattern verification | Static | All project files |
| `docpact doctor` | Ecosystem self-diagnosis | Static | Configuration files |

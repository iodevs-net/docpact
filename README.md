# docpact

Business rule verification for Python codebases.

```bash
pip install docpact
docpact report
```

## What it does

docpact reads business rules from a registry file (e.g. `REGISTRO.md`) and checks whether each rule has implementation evidence in the codebase: markers, tests, and configured validators.

```bash
docpact report
═══ DOC PACT REPORT ═══

RESUMEN:
  ✅ Implementadas: 64/85 (75%)
  🔶 Parciales:     3/85 (3%)
  ❌ No implement:  18/85 (21%)
```

## Commands

| Command | Purpose |
|---------|---------|
| `docpact report` | Delta: declared rules vs code evidence |
| `docpact report --ci` | CI gate: fails if implemented rules lack tests |
| `docpact report --json` | Structured output with implementation suggestions |
| `docpact check .` | Validate contracts, side effects, patterns |
| `docpact validate --staged` | Pre-commit hook: fast contract enforcement |
| `docpact extract` | Extract contracts as JSON |
| `docpact init` | Generate contract template for a function |

## Report

`docpact report` crosses the rule registry with the codebase index.

For each rule, it checks:
- **validador**: entry in `docpact.toml`
- **marcador**: `# RN-XXX` comment in code
- **test**: `tests/rn/test_rn_XXX.py` exists

States:
- **✅ IMPLEMENTADA** — marker + test + logic found
- **🔶 PARCIAL** — some evidence, not complete
- **❌ NO IMPLEMENTADA** — declared but no code

### CI mode

```yaml
# .github/workflows/docpact.yml
- name: Docpact report
  run: docpact report --ci
```

Fails if any rule has code but no test.

### JSON output

```bash
docpact report --json
```

For unimplemented rules, includes:
- `archivos_sugeridos` — files where similar rules are implemented
- `funciones_relacionadas` — functions handling similar rules
- `rn_similares` — implemented rules with the same prefix

## Contract format

```python
def crear_ticket(editor, cliente, titulo, descripcion):
    """Create a support ticket.

    CONTRATO:
      input:
        editor: AbstractUser — User creating the ticket
        cliente: Cliente — Client associated
        titulo: str — Ticket title
        descripcion: str — Problem description
      output: Ticket — Created ticket instance
      side_effects: db_write, email
      rn:
        - RN-001: Base ticket states
        - RN-FAC-003: Clients without contract can't create tickets
      borde:
        cliente_restringido: PermissionError
      dependencias:
        - soporte/services/audit.py::AuditService
    """
```

Rules:
1. `side_effects` is mandatory. Use `ninguno` if there are none.
2. `rn:` — each ID must have a `# RN-XXX` marker in the function body.
3. `dependencias:` — each path must exist. Format: `path/file.py::Symbol`.
4. Optional: `input`, `output`, `borde`.

## Configuration

```toml
# docpact.toml
[docpact]
strict = true

[docpact.rn_patrones]
"RN-FAC-003" = { patron = "contrato_activo", archivos = ["soporte/services/tickets.py"] }
"RN-SEG-002" = { patron = "puede_asignar_tareas", archivos = ["nucleo/services/colaborador.py"] }

[docpact.warnings]
suppress = [
    "duplica dependencia del CONTRATO",
]
```

## What docpact does not do

| Tool | Purpose |
|------|---------|
| ruff / pylint | Syntax, style, complexity |
| mypy / pyright | Type checking |
| pytest | Test execution |
| coverage | Test coverage |
| bandit | Security scanning |

docpact validates contracts and business rule implementation. It does not lint, type-check, or run tests.

## Installation

```bash
pip install docpact
```

Python 3.10+. No external dependencies.

## License

MIT

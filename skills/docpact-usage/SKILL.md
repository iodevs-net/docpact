---
name: docpact-usage
description: "Trigger: docpact, contratos, reglas de negocio, RN, verificacion, business rules. Use docpact correctly to verify code implements business rules."
license: Apache-2.0
metadata:
  author: "gentleman-programming"
  version: "1.0"
---

## Activation Contract

Use this skill when:
- Working on a project that uses docpact
- Verifying code implements business rules
- Creating or modifying CONTRATOs
- Checking for rule conflicts
- Explaining errors to non-technical stakeholders

## Hard Rules

- ALWAYS run `explicar_errores` BEFORE `check` — check only validates structure, explicar_errores validates behavior
- ALWAYS run `obtener_briefing` BEFORE writing any code — understand the rules first
- ALWAYS run `verificar_conflicto` BEFORE creating a new RN — prevent duplicates
- NEVER assume "0 errors" means "code is correct" — it only means "CONTRATO format is valid"
- NEVER skip the briefing — it contains all active rules the agent MUST respect

## Decision Gates

| Situation | Tool | Why |
|-----------|------|-----|
| Starting work on a project | `obtener_briefing` | Understand all active rules |
| Before writing code | `buscar_por_intencion` | Find existing patterns |
| After writing code | `explicar_errores` | Verify behavior, not just format |
| Creating a new RN | `verificar_conflicto` | Prevent duplicates/overrides |
| Explaining to stakeholder | `explicar_errores` + `explicar_rn` | Human-readable output |
| Committing changes | `validar_cambio` | Pre-commit verification |

## Execution Steps

### Step 1: Understand the project (MANDATORY)
```python
briefing = obtener_briefing()
# Read the briefing — it contains ALL active rules
# Never skip this step
```

### Step 2: Find relevant code
```python
results = buscar_por_intencion("what you're looking for")
# Shows existing implementations and their rules
```

### Step 3: Verify your changes
```python
# WRONG: only checks CONTRATO format
check(path)

# RIGHT: checks if code actually implements the rules
errors = explicar_errores()
# Shows errors by urgency with human-readable explanations
```

### Step 4: Create new rules safely
```python
# ALWAYS check for conflicts first
conflicts = verificar_conflicto("new rule description")

# Only create if no conflicts
if not conflicts["tiene_conflictos"]:
    crear_rn("RN-XXX", "rule description")
```

### Step 5: Commit with verification
```python
result = validar_cambio(path, diff)
# Blocks commit if rules are violated
```

## Common Mistakes

1. **Using `check` instead of `explicar_errores`**
   - `check` = format validation (weak)
   - `explicar_errores` = behavior validation (strong)

2. **Skipping the briefing**
   - Without it, the agent doesn't know what rules exist
   - May create conflicting rules

3. **Creating RNs without conflict check**
   - May duplicate existing rules
   - May override higher-priority rules

4. **Explaining "0 errors" to stakeholders**
   - "0 errors" from `check` ≠ "code is correct"
   - Run `explicar_errores` for real validation

## Output Contract

When using docpact:
- Always explain WHAT was checked and WHY
- Always show urgency levels (alta/media/baja)
- Always provide actionable fix steps
- Never say "everything is fine" without running `explicar_errores`

## References

- `DOCPACT_AGENT_GUIDE.md` — complete guide for agents
- `docs/spec/` — formal specifications
- `src/docpact/mcp_server.py` — all 19 MCP tools

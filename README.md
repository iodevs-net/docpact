# docpact

**docpact verifica que lo que tu código promete sea lo que realmente hace.**

Un linter estático que valida que los `CONTRATO:` en tus docstrings estén sincronizados con la implementación real. Pensado para codebases donde los agentes de IA son los principales escritores y lectores del código.

```bash
pip install docpact
docpact check .
```

```
📊 249 funciones públicas encontradas
✅ 7 contratos válidos
✅ 0 errores
Score: 70/100 — L2 (AI-Friendly)
```

---

## Estado actual

**MVP funcional.** El core está sólido y ya se usa en producción en ioDesk-3.

| Componente | Estado |
|------------|--------|
| Parser de CONTRATOS (Python) | ✅ Listo |
| `docpact check` — side_effects vs AST | ✅ Listo |
| `docpact check` — RN-XXX en comentarios | ✅ Listo |
| `docpact check` — dependencias existen | ✅ Listo |
| `docpact extract` | ✅ Listo |
| API Python (`docpact.api`) | ✅ Listo |
| MCP server para agentes | ✅ Listo |
| Procesamiento paralelo | ✅ Listo |
| 60 tests, cobertura 70% | ✅ Listo |
| `docpact init` — generar CONTRATOS | ⏳ No |
| Integración mypy | ⏳ No |
| Output SARIF | ⏳ No |
| Verificación cross-file | ⏳ No |

---

## Instalación

```bash
pip install docpact
```

Requiere Python 3.10+. Sin dependencias externas.

---

## Uso

```bash
# Verificar un archivo
docpact check soporte/services/tickets.py

# Verificar todo el proyecto
docpact check .

# Modo strict (falla si hay funciones sin CONTRATO)
docpact check . --strict

# Extraer todos los CONTRATOS como JSON
docpact extract soporte/services/tickets.py --format json
```

### Desde Python (API)

```python
from docpact.api import check_proyecto, check_file

# Verificar un archivo
resultado = check_file("soporte/services/tickets.py")
resultado.valido         # True/False
resultado.calcular_score()  # 0-100

# Verificar todo el proyecto
proyecto = check_proyecto(".", strict=True)
proyecto.total_errores
proyecto.nivel  # "L2 — AI-Friendly"
```

### Desde agentes (MCP)

```json
{
  "mcpServers": {
    "docpact": {
      "command": "docpact",
      "args": ["mcp"]
    }
  }
}
```

Herramientas expuestas: `docpact_check`, `docpact_extract`, `docpact_score`.

---

## Formato del CONTRATO

```python
def sumar_sesiones(tickets: list[Ticket]) -> HorasCalculadas:
    """
    CONTRATO:
      input:
        tickets: list[Ticket] — Tickets con sesiones precargadas
      output: HorasCalculadas(total_horas, total_segundos)
      side_effects: ninguno
      rn:
        - RN-002: solo sesiones completadas descuentan horas
      borde:
        - tickets vacío → HorasCalculadas(0, 0)
        - sesión sin fin → se ignora
      dependencias:
        - soporte/models/ticket.py::Ticket
    """
```

### Reglas

1. **`side_effects` es obligatorio.** `ninguno` si no hay efectos.
2. **`rn:`** — cada ID debe aparecer como `# RN-XXX` en el cuerpo.
3. **`dependencias:`** — cada ruta debe existir. Formato: `ruta/archivo.py::Simbolo`.
4. **Campos opcionales:** `input`, `output`, `borde`.

---

## Qué verifica docpact

| Verificación | Método | ¿Qué pasa si falla? |
|---|---|---|
| `side_effects: ninguno` pero hay llamadas reales | AST walker busca patrones de `.create`, `send_mail`, etc. | ❌ Error |
| Dependencia apunta a archivo/símbolo que no existe | `ast.walk` + resolución de rutas | ❌ Error |
| strict: función pública sin CONTRATO | Detecta funciones sin bloque CONTRATO | ❌ Error |
| RN-XXX declarada sin `# RN-XXX` en el cuerpo | Extrae comentarios de la fuente | ⚠️ Warning |

**Limitación conocida:** El AST walker busca strings literales (`".create"`, `"send_mail"`).
No detecta llamadas dinámicas como `getattr(Model, 'create')()` o `Model.objects. create()` con espacio.
Para el uso esperado (agentes que escriben código directo, no ofuscado) es suficiente.

---

## Configuración

```toml
# docpact.toml
[docpact]
strict = false
min_score = 75
exclude = ["tests/", "migrations/"]

[docpact.side_effects]
db_write = [".create", ".save", ".update", ".delete"]
email = ["send_mail", "EmailMessage"]

[docpact.rules]
rn_prefix = "RN-"
```

---

## Integración CI/CD

```yaml
# .github/workflows/docpact.yml
name: docpact
on: [push, pull_request]
jobs:
  docpact:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - name: Install docpact
        run: pip install docpact
      - name: Check contracts
        run: docpact check . --config docpact.toml
```

---

## Score AI-Native

| Nivel | Score | Nombre |
|-------|-------|--------|
| L0 | 0–24 | Human-Native |
| L1 | 25–49 | AI-Aware |
| L2 | 50–74 | AI-Friendly |
| L3 | 75–89 | AI-Native |
| L4 | 90–100 | AI-Optimized |

---

## Base evidencia

- [Agentless (arXiv:2407.01489)](https://arxiv.org/abs/2407.01489): ~60% de fallos de agentes ocurren en localización, no generación
- [SWE-bench](https://www.swebench.com/): el scaffold importa más que el modelo
- [THE AGENT CODE MANIFESTO](https://github.com/tu-org/agent-code-manifesto): las reglas que docpact implementa
- [Hidden Cost of Readability (arXiv:2508.13666)](https://arxiv.org/abs/2508.13666): el formateo humano cuesta 25% de tokens sin aportar señal

---

## Licencia

MIT

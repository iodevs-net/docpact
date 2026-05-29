# docpact — AICDD (AI Contract-Driven Development)

**docpact verifica que lo que tu código promete sea lo que realmente hace.**

Un verificador de CONTRATOS embebidos en docstrings, para codebases donde
los agentes de IA son los principales escritores y lectores del código.
Backend Python y frontend TypeScript con el mismo formato.

```bash
pip install docpact
docpact check .
```

```
📊 682 funciones públicas encontradas
✅ 616 contratos válidos
⚠️  0 warnings
✅ 0 errores
Score: 96/100 — L4 — AI-Optimized
```

## ¿Qué es AICDD?

**AI Contract-Driven Development.** Un modelo donde:

1. Cada función pública declara un **CONTRATO** en su docstring:
   qué recibe, qué devuelve, qué efectos secundarios tiene, qué reglas
   de negocio implementa, y de qué depende.
2. **docpact verifica** que el CONTRATO no mienta — cruza lo declarado
   contra el código fuente real (AST walker), los imports, y los comentarios.
3. **3 capas de verificación** evitan que el agente pueda saltarse el control:
   - **Estática** — pre-commit + `make check`
   - **Dinámica** — sandbox Docker + Hypothesis PBT + trap loop PASS/FAIL
   - **Gobernanza** — CI/CD en GitHub Actions (infranqueable para el agente)

AICDD no es TDD. No escribes tests primero. Escribes el CONTRATO primero
(como metadata en el docstring) y docpact verifica que el código lo cumpla.

## Estado actual

**v0.4.2 — Production-ready en ioDesk-3 (Django 6 + React 19).**

| Componente | Estado |
|------------|--------|
| Parser de CONTRATOS (Python) | ✅ |
| Parser de CONTRATOS (TypeScript/JSX) | ✅ |
| `docpact check` (+ strict, + fix) | ✅ |
| `docpact extract` (Python + TS) | ✅ |
| `docpact run` (sandbox Docker + PBT) | ✅ |
| `docpact init` (generación automática) | ✅ |
| RN test checker (`tests/rn/test_rn_XXX.py`) | ✅ |
| Side effects checker (Python + TS) | ✅ |
| Dependencias checker | ✅ |
| Signature checker (input/output vs firma) | ✅ |
| API Python (`docpact.api`) | ✅ |
| MCP server para agentes | ✅ |
| 128 tests, mypy --strict (0 errores) | ✅ |

## Instalación

```bash
pip install docpact
```

Requiere Python 3.10+, Sin dependencias externas.
Para `docpact run`: requiere Docker.

## Uso

```bash
# Verificar un archivo
docpact check soporte/services/tickets.py

# Verificar todo el proyecto
docpact check .

# Modo strict (falla si hay funciones sin CONTRATO)
docpact check . --strict

# Auto-corregir side_effects
docpact check . --fix

# Extraer todos los CONTRATOS como JSON
docpact extract soporte/services/tickets.py --format json

# Verificación dinámica en sandbox Docker
docpact run solution.py --tests tests/

# Generar CONTRATO automático
docpact init soporte/services/tickets.py --function crear_ticket
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
2. **`rn:`** — cada ID debe aparecer como `# RN-XXX` en el código.
   Y debe existir `tests/rn/test_rn_XXX.py` con tests de esa regla.
3. **`dependencias:`** — cada ruta debe existir. Formato: `ruta/archivo.py::Simbolo`.
4. **Campos opcionales:** `input`, `output`, `borde`.

## Qué verifica docpact

| Verificación | Método | ¿Qué pasa si falla? |
|---|---|---|
| `side_effects: ninguno` pero hay llamadas reales | AST walker busca `.create`, `send_mail`, etc. | ❌ Error |
| Dependencia apunta a archivo que no existe | Resolución de rutas | ❌ Error |
| strict: función pública sin CONTRATO | Detecta funciones sin bloque CONTRATO | ❌ Error |
| RN-XXX declarada sin `# RN-XXX` en el cuerpo | Extrae comentarios de la fuente | ⚠️ Warning |
| RN-XXX declarada sin `tests/rn/test_rn_XXX.py` | Verifica existencia del archivo de test | ❌ Error |
| TypeScript/JSX: side_effects no declarados | Regex sobre `api.post`, `fetch(`, etc. | ❌ Error |
| TypeScript/JSX: CONTRATO en JSDoc | Parser de comentarios `//` y `/** */` | ❌ Error |
| Signature: input/output CONTRATO vs firma real | Comparación de tipos | ⚠️ Warning |

### Limitaciones conocidas

1. **AST walker (Python):** Busca strings literales (`".create"`, `"send_mail"`).
   No detecta `getattr(Model, 'create')()`. Suficiente para agentes no adversariales.

2. **Parser TypeScript:** Regex, no AST. No detecta funciones sin CONTRATO
   (solo lee lo que está comentado). No verifica tipos (eso lo hace tsc).

3. **Side effects en TypeScript:** Detecta `api.post`, `fetch(`, `axios.`.
   Cubre ~80%. No detecta llamadas dinámicas.

4. **RN checker TypeScript:** Busca `RN-XXX` en código fuente. Requiere
   comentario explícito. No verifica implementación real.

## Verificación en Tiempo de Ejecución (Sentinelas de Runtime)

A partir de la versión 0.4.2, `docpact` incluye un plugin de Pytest que ejecuta verificación dinámica para evitar la **falsificación de contratos**.

Si una función promete `side_effects: ninguno` pero durante la suite de pruebas ejecuta operaciones prohibidas, el test fallará automáticamente con una violación de contrato (`ContractViolationError`).

### Configuración en `docpact.toml`

```toml
[docpact.runtime]
modo = "strict"  # strict (falla el test) | warning (avisa en consola) | disabled (desactivado)
interceptar_servicios = true
interceptar_vistas = true
```

### Sentinelas Interceptados
1. **Base de Datos (`db_write`):** Intercepta consultas de escritura SQL (`INSERT`, `UPDATE`, `DELETE`, etc.) en caliente vía Django `connection.execute_wrapper`.
2. **Sistema de Archivos (`escribe_archivo`):** Parchea `builtins.open` para detectar aperturas en modo de escritura (`'w'`, `'a'`, `'x'`).
3. **Correo Electrónico (`email`):** Intercepta el outbox de pruebas de Django y `smtplib.SMTP.sendmail`.

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

## Score AI-Native

| Nivel | Score | Nombre |
|-------|-------|--------|
| L0 | 0–24 | Human-Native |
| L1 | 25–49 | AI-Aware |
| L2 | 50–74 | AI-Friendly |
| L3 | 75–89 | AI-Native |
| L4 | 90–100 | AI-Optimized |

## Filosofía

AICDD no es una herramienta — es un **protocolo de comunicación** entre
agentes y código. El CONTRATO es una interfaz que tres actores pueden leer:
humanos, agentes, y parsers. docpact es la implementación de referencia
del verificador.

- **Los agentes escriben código + CONTRATO**
- **docpact verifica que el CONTRATO no mienta**
- **3 capas de verificación impiden que el agente se salte el control**
- **El resultado es código auto-documentado y verificable**

## Base evidencia

- [Agentless (arXiv:2407.01489)](https://arxiv.org/abs/2407.01489): ~60% de fallos de agentes ocurren en localización, no generación
- [EvilGenie](https://github.com/JonathanGabor/EvilGenie): benchmark de reward hacking
- [SpecBench (arXiv:2605.21384)](https://arxiv.org/abs/2605.21384): taxonomía de reward hacking
- [PBT-Bench (arXiv:2605.15229)](https://arxiv.org/abs/2605.15229): Property-Based Testing para agentes
- [THE AGENT CODE MANIFESTO](https://github.com/tu-org/agent-code-manifesto): reglas AI-Native
- [Hidden Cost of Readability (arXiv:2508.13666)](https://arxiv.org/abs/2508.13666): formateo humano cuesta 25% de tokens

## Licencia

MIT

# docpact

**docpact verifica que lo que tu código promete sea lo que realmente hace.**

Un linter estático que valida que los `CONTRATO:` en tus docstrings estén sincronizados con la implementación real. Pensado para codebases donde los agentes de IA son los principales escritores y lectores del código.

```bash
pip install docpact
docpact check .
```

```
📊 42 funciones públicas encontradas
✅ 38 contratos válidos
⚠️  3 contratos desactualizados
❌  1 side effect no declarado en TicketService.crear()

Score: 91/100 — AI-Friendly
```

---

## El problema

Un `CONTRATO:` en un docstring es documentación. Documentación que nadie verifica. Documentación que miente.

```python
def crear_ticket(user: User, datos: TicketDTO) -> Ticket:
    """
    CONTRATO:
      output: Ticket
      side_effects: ninguno      # ← mentira
      rn: [RN-001]               # ← nunca se implementó
    """
    BitacoraEntry.objects.create(...)   # side effect no declarado
    # RN-001 ausente del código
```

Cuando un agente lee ese contrato y confía en él, rompe el sistema.

**docpact convierte el contrato en un test verificable estáticamente.**

---

## Instalación

```bash
pip install docpact
```

Requiere Python 3.10+. Sin dependencias externas obligatorias. `mypy` opcional para verificación de tipos avanzada.

---

## Uso

```bash
# Verificar un archivo
docpact check soporte/services/tickets.py

# Verificar todo el proyecto
docpact check .

# Generar CONTRATO skeleton para funciones sin contrato
docpact init soporte/services/tickets.py --function crear_ticket

# Generar contratos para todo un módulo
docpact init soporte/services/ --batch

# Modo strict (falla si hay funciones sin contrato)
docpact check . --strict

# Reporte detallado con sugerencias
docpact check . --report
```

---

## Formato del CONTRATO

docpact entiende el siguiente formato en docstrings:

```python
def sumar_sesiones(tickets: list[Ticket]) -> HorasCalculadas:
    """
    CONTRATO:
      input:  tickets con .prefetch_related("sesiones")
              Sin prefetch → N+1 queries
      output: HorasCalculadas(total_horas, total_segundos, cantidad_sesiones)
      side_effects: ninguno
      rn:
        - RN-002: solo sesiones completadas descuentan horas
      borde:
        - tickets vacío → HorasCalculadas(0, 0, 0)
        - sesión sin fin → se ignora
      dependencias:
        - soporte.models.Ticket
    """
```

No necesitás reescribir tu código. Si ya tenés docstrings, `docpact init` los convierte.

---

## Qué verifica

| Campo         | Verificación                                               | Método              |
|---------------|------------------------------------------------------------|---------------------|
| `input`       | ¿Los parámetros coinciden en nombre y tipo?                | AST + mypy          |
| `output`      | ¿El tipo de retorno declarado coincide con la firma?       | AST + mypy          |
| `side_effects`| ¿Las llamadas en el cuerpo coinciden con lo declarado?     | AST walker          |
| `rn`          | ¿Los IDs de reglas de negocio aparecen en el cuerpo?       | grep semántico      |
| `borde`       | ¿Los casos borde tienen cobertura en tests?                | pytest integration  |
| presencia     | ¿Toda función pública tiene CONTRATO?                      | scan de módulo      |

---

## Niveles de madurez

docpact clasifica tu repositorio en una escala AI-Native Readiness:

| Nivel | Nombre         | Score   |
|-------|----------------|---------|
| L0    | Human-Native   | 0–24    |
| L1    | AI-Aware       | 25–49   |
| L2    | AI-Friendly    | 50–74   |
| L3    | AI-Native      | 75–89   |
| L4    | AI-Optimized   | 90–100  |

---

## Integración CI/CD

```yaml
# GitHub Actions
- name: docpact
  run: |
    pip install docpact
    docpact check . --strict
```

```toml
# pre-commit
repos:
  - repo: https://github.com/tu-org/docpact
    rev: v0.1.0
    hooks:
      - id: docpact
```

Salida compatible con SARIF para integración con GitHub Code Scanning.

---

## Configuración

```toml
# .docpact.toml
[docpact]
strict = false
min_score = 75
exclude = ["tests/", "migrations/"]

[docpact.side_effects]
# patrones que docpact reconoce como side effects
db_write   = ["objects.create", "objects.update", "save()", "delete()"]
email      = ["send_mail", "EmailMessage"]
external   = ["requests.post", "requests.get", "httpx"]

[docpact.rules]
# prefijo de tus IDs de reglas de negocio
rn_prefix = "RN-"
```

---

## Por qué existe docpact

Los agentes de IA ya son los principales escritores y lectores de código en muchos equipos. Pero leen contratos que nadie verifica y confían en ellos para modificar el sistema.

El resultado son bugs silenciosos: side effects no declarados que se rompen, reglas de negocio que nunca se implementaron, tipos que mienten.

docpact parte de una premisa simple: **un contrato que no se verifica no es un contrato — es un comentario.**

La evidencia que motivó esta herramienta:
- [Agentless (arXiv:2407.01489)](https://arxiv.org/abs/2407.01489): el 60% de los fallos de agentes ocurren en la fase de localización, no de generación
- [SWE-bench](https://www.swebench.com/): el scaffold importa más que el modelo
- [THE AGENT CODE MANIFESTO](https://github.com/tu-org/agent-code-manifesto): las reglas que docpact implementa

---

## Estado actual

> **⚠️ Work in progress.** El spike técnico está completo. El MVP está en desarrollo activo.

| Fase | Estado | Descripción |
|------|--------|-------------|
| Fase 0 — Spike | ✅ completo | Parser extrae CONTRATO, walker detecta side effects locales |
| Fase 1 — MVP | 🔄 en progreso | `check` + `init`, verificación de tipos y side effects básicos |
| Fase 2 — CI | ⏳ pendiente | pre-commit, SARIF, score de madurez, `--strict` mode |
| Fase 3 — Inter-archivo | ⏳ pendiente | Análisis cross-file, cadena de side effects, watch mode |
| Fase 4 — Ecosistema | ⏳ pendiente | PyPI estable, plugin system, documentación completa |

---

## Contribuir

```bash
git clone https://github.com/tu-org/docpact
cd docpact
pip install -e ".[dev]"
make test
```

Issues y PRs bienvenidos. Si encontrás un caso donde docpact falla en silencio (falso negativo) o grita innecesariamente (falso positivo), abrí un issue con el snippet mínimo que lo reproduce.

---

## Licencia

MIT

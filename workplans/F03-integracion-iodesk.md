# Fase 3 — Integración ioDesk-3 (pre-commit + CI)

**Objetivo:** Cerrar el ciclo de verificación. docpact se integra en el flujo
de desarrollo de ioDesk-3 como pre-commit hook y GitHub Action. Cuando un agente
modifica código y su CONTRATO miente, `make check` falla. El agente aprende — no
por buena voluntad, sino porque le duele.

**Principio Pareto:** La integración más valiosa no es tener docpact instalado
— es tenerlo en el **gate de verificación** que el agente no puede esquivar.
Sin CI, docpact es una biblioteca más. Con CI, es un compilador de contratos.

**Duración estimada:** 1-2 días.
**Depende de:** Fase 2 (CLI funcional).

---

## 1. Integración pre-commit

### 1.1 Hook personalizado

```yaml
# .pre-commit-config.yaml en ioDesk-3
repos:
  - repo: https://github.com/tu-org/docpact
    rev: v0.1.0
    hooks:
      - id: docpact
        args: ["check", "--strict"]
        stages: [pre-commit]
```

### 1.2 Hook local (sin depender de repo externo)

Para desarrollo temprano, antes de que docpact esté en GitHub:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: docpact
        name: docpact check
        entry: docpact check --strict
        language: python
        types: [python]
        stages: [pre-commit]
```

---

## 2. Integración Makefile

```makefile
# En ioDesk-3/Makefile

.PHONY: docpact
docpact:
	@echo "🔍 Verificando contratos..."
	@docpact check . --strict --config docpact.toml

# Modificar el gate existente para incluir docpact
check: lint typecheck test docpact
	@echo "✅ All gates passed"
```

---

## 3. Integración GitHub Actions

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
        with:
          python-version: "3.12"
      - name: Install docpact
        run: pip install docpact
      - name: Check contracts
        run: docpact check . --strict --config docpact.toml
```

---

## 4. Configuración de ioDesk-3

### 4.1 docpact.toml para ioDesk-3

```toml
[docpact]
strict = false
min_score = 75
exclude = [
    "tests/",
    "migrations/",
    "__pycache__/",
    ".venv/",
    "node_modules/",
    "static/",
    "templates/",
    "media/",
]

[docpact.side_effects]
db_write = [
    ".create(", ".save()", ".update(", ".bulk_create(",
    ".delete()", "transaction.atomic(",
]
email = ["send_mail", "EmailMessage", "_enviar_email", "enviar_email_async"]
external = ["requests.", "httpx.", "urllib.request"]
audit = [
    "registrar_evento_bitacora", "AuditService.log",
    "BitacoraEntry.objects.create",
]
notification = [
    "NotificacionService.", "_notificar_", "notificar_",
    "_notificar_inicio_trabajo", "_notificar_cliente",
    "_notificar_cliente_resolucion", "_notificar_tecnico_resolucion",
]
sesion = ["SesionTrabajo.objects.", "SessionService.", "iniciar_sesion", "detener_sesion"]
gasto = ["Gasto.objects.", "registrar_gastos_traslado"]
checklist = ["ChecklistRespuesta.objects.", "ChecklistService"]

[docpact.rules]
rn_prefix = "RN-"
```

### 4.2 Score base de ioDesk-3

Ejecutar `docpact check .` sobre ioDesk-3 y documentar el score actual.
Este es el baseline contra el cual medir mejora.

---

## 5. Feedback loop

El ciclo de verificación completo:

```
1. Agente escribe código + CONTRATO
2. git add .
3. pre-commit → docpact check --strict
   ├── ✅ Pasa → commit permitido
   └── ❌ Falla → agente debe corregir:
         a. Leer el error específico (línea, tipo, sugerencia)
         b. Corregir el CONTRATO O corregir el código
         c. git add . → pre-commit → repetir
4. git push
5. GitHub Action corre docpact check --strict
   ├── ✅ Pasa → PR puede mergear
   └── ❌ Falla → PR bloqueado
```

Este loop es lo que hace que el agente **aprenda**. No es castigo — es
retroalimentación inmediata. Cada vez que el agente miente en un CONTRATO
y el pre-commit lo rechaza, el agente internaliza que mentir es más caro
que decir la verdad.

---

## 6. Criterios de éxito

1. `pre-commit run docpact` en ioDesk-3 detecta un CONTRATO inválido
2. `make check` incluye docpact y falla si hay errores
3. GitHub Action reporta score en cada PR
4. Se documenta el score base para tracking

---

## 7. Check-list

```
☐ Instalar docpact en ioDesk-3 (pip install -e ../docpact o similar)
☐ Crear docpact.toml en ioDesk-3 con config del proyecto
☐ Ejecutar docpact check . --report → documentar score base
☐ Agregar hook pre-commit local en .pre-commit-config.yaml
☐ Agregar target docpact en Makefile
☐ Modificar target check para incluir docpact
☐ Crear .github/workflows/docpact.yml
☐ Verificar que pre-commit rechaza un CONTRATO inválido
☐ Verificar que GitHub Action corre en push
☐ docs/caso-de-estudio-iodesk.md (documentar la integración)
```

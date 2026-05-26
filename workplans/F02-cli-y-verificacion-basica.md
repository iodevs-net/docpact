# Fase 2 — CLI + Verificación básica (side_effects + RN)

**Objetivo:** Implementar el comando `docpact check` que verifica que los
CONTRATOS no mientan. Específicamente: que `side_effects` declarados coincidan
con las llamadas reales en el cuerpo de la función, y que los IDs `RN-XXX`
declarados en `rn:` efectivamente aparezcan en el código.

**Principio Pareto:** De todas las verificaciones posibles, verificar
`side_effects` es la que atrapa los bugs más silenciosos (efectos no declarados
que rompen el sistema) con el menor costo de implementación. Verificar `rn:`
es la segunda prioridad. Juntos cubren ~70% de las mentiras en contratos.

**Duración estimada:** 3-4 días.
**Depende de:** Fase 1 (parser funcional).

---

## 1. Verificador de side_effects

### 1.1 Qué verifica

Toma el valor de `side_effects` del CONTRATO y lo compara contra las llamadas
reales en el cuerpo de la función usando un AST walker.

**Declaración → Verificación:**

| `side_effects` declara | Walker busca |
|------------------------|--------------|
| `ninguno` | Ninguna llamada a funciones de la lista de "efectos" |
| `Crea ticket en BD` | `.create(`, `.save()`, `bulk_create` |
| `registra bitácora` | `BitacoraEntry.objects.create`, `registrar_evento_bitacora` |
| `envía notificaciones` | `send_mail`, `NotificacionService`, `_enviar_email` |
| `sincroniza sesiones` | `SesionTrabajo.objects.`, `SessionService` |

### 1.2 Base de conocimiento de side_effects

El verificador necesita saber QUÉ llamadas constituyen un side effect. Esto se
configura en `docpact.toml`:

```toml
[side_effects]
# Patrones que indican escritura en BD
db_write = [
    ".create(", ".save()", ".update(", ".bulk_create(",
    ".delete()", "transaction.atomic(",
]
# Patrones que indican envío de email
email = [
    "send_mail", "EmailMessage", "_enviar_email",
]
# Patrones que indican llamadas externas
external = [
    "requests.", "httpx.", "urllib.request",
]
# Patrones que indican logging/bitácora
audit = [
    "registrar_evento_bitacora", "AuditService.log",
    "BitacoraEntry.objects.create",
]
# Notificaciones
notification = [
    "NotificacionService.", "_notificar_",
    "notificar_",
]
```

Si `side_effects` es `ninguno` y el walker encuentra MATCH con algún patrón
→ **error: side effect no declarado**.

Si `side_effects` lista "envía notificaciones" y el walker NO encuentra
ningún patrón de notificación → **warning: side effect declarado pero no
encontrado** (no es error, porque podría ser condicional).

### 1.3 Funcionamiento del AST walker

```
Cuerpo de la función (nodo AST)
    │
    ▼
[AST Walker]  ← recorre recursivamente todos los nodos
    │
    ▼
[Call Detector]  ← extrae todos los Call nodes
    │
    ▼
[Pattern Matcher]  ← compara cada call contra patrones configurados
    │
    ▼
[SideEffect Report] ← lista de efectos encontrados + no declarados
```

El walker debe ser recursivo y soportar:
- Llamadas directas: `crear_ticket(...)`
- Llamadas encadenadas: `Ticket.objects.create(...)`
- Llamadas anidadas: dentro de `if`, `for`, `with`, `try/except`
- Métodos de instancia: `self._auditar_transicion(...)`
- Funciones importadas: `registrar_evento_bitacora(...)`

### 1.4 Casos borde

```python
# Caso 1: Side effect condicional (NO debe reportar error si está en un if)
def crear_ticket():
    """
    CONTRATO:
      side_effects: ninguno
    """
    if enviar_notificacion:          # Esta llamada sí está condicionada
        NotificacionService.notificar(...)
    # → WARNING: side effect condicional, no error
```

```python
# Caso 2: Side effect no declarado (DEBE reportar error)
def crear_ticket():
    """
    CONTRATO:
      side_effects: ninguno
    """
    BitacoraEntry.objects.create(...)  # ← NO declarado en side_effects
    # → ERROR: side effect 'registra bitácora' no declarado
```

```python
# Caso 3: Side effect declarado pero ausente (DEBE reportar warning)
def crear_ticket():
    """
    CONTRATO:
      side_effects: envía notificaciones
    """
    ticket = Ticket.objects.create(...)  # no hay notificación aquí
    # → WARNING: 'envía notificaciones' declarado pero no encontrado
```

---

## 2. Verificador de RN (reglas de negocio)

### 2.1 Qué verifica

Toma los IDs `RN-XXX` del campo `rn:` y confirma que cada ID aparezca como
comentario en el cuerpo de la función (no solo en el CONTRATO).

```python
def suspender(ticket, editor, motivo, data):
    """
    CONTRATO:
      rn:
        - RN-004: No se permite saltar entre estados de trabajo
        - RN-005: Suspendido permite reanudar a cualquier estado de trabajo
    """
    # RN-004: esta llamada verifica la transición
    can_transition_to(ticket, Ticket.Estado.SUSPENDIDO)
    # RN-005
    ...
```

El verificador busca `# RN-004` o `# RN-005` como comentario en el cuerpo.
Si el ID está en el CONTRATO pero no aparece como comentario en el cuerpo
→ **warning: RN declarada pero no referenciada en el código**.

### 2.2 Por qué esto funciona

El patrón `# RN-XXX` es fácil de buscar con regex y no requiere entender
la semántica de la regla de negocio. Si el agente implementa una RN pero
no la referencia con el ID, es una bandera roja de que la regla podría
no estar implementada realmente.

---

## 3. Verificador de dependencias

### 3.1 Qué verifica

Toma el campo `dependencias:` y confirma que:
1. Cada ruta de módulo existe (el archivo referenciado está en el proyecto)
2. Cada símbolo referenciado (después de `::`) existe en ese módulo (análisis
   superficial: `grep -rn "def Simbolo\|class Simbolo"`)
3. No hay dependencias circulares entre módulos (A depende de B y B depende de A)

### 3.2 Formato

```
dependencias:
  - soporte/models/ticket.py::Ticket
  - clientes/services.py::obtener_resumen_bolsa
  - soporte/constants.py::EstadoTicket
```

---

## 4. Comando `docpact check`

### 4.1 Interfaz

```bash
# Verificar un archivo
docpact check soporte/services/tickets.py

# Verificar todo un proyecto (busca todos los .py)
docpact check .

# Con configuración personalizada
docpact check . --config docpact.toml

# Modo strict (falla si hay funciones públicas sin CONTRATO)
docpact check . --strict

# Reporte detallado
docpact check . --report

# Solo side effects (útil para debug)
docpact check . --only side_effects
```

### 4.2 Salida

```
📊 42 funciones públicas encontradas
✅ 38 contratos válidos
⚠️  3 warnings:
    - tickets.py::TicketService.suspender: RN-005 declarada pero no referenciada
    - sesiones.py::SessionService.start: side_effects 'envía notificaciones' no encontrado
    - tickets.py::TicketService.cancelar: no tiene CONTRATO
❌  1 error:
    - tickets.py::TicketService.crear: side_effect 'registra bitácora' no declarado

Score: 91/100 — AI-Friendly
```

### 4.3 Códigos de salida

| Código | Significado |
|--------|-------------|
| 0 | Sin errores (puede tener warnings) |
| 1 | Errores de verificación |
| 2 | Error de configuración o I/O |

---

## 5. Configuración (docpact.toml)

```toml
[docpact]
strict = false           # false: permite funciones sin CONTRATO
min_score = 75           # Score mínimo para pasar CI
exclude = [              # Patrones a excluir
    "tests/",
    "migrations/",
    "__pycache__/",
    ".venv/",
]

[docpact.side_effects]
db_write = [".create(", ".save()", ".update(", ".bulk_create(", ".delete()"]
email = ["send_mail", "EmailMessage", "_enviar_email"]
external = ["requests.", "httpx.", "urllib.request"]
audit = ["BitacoraEntry.objects.create", "AuditService.log", "registrar_evento_bitacora"]
notification = ["NotificacionService.", "_notificar_", "notificar_"]
sesion = ["SesionTrabajo.objects.", "SessionService."]

[docpact.rules]
rn_prefix = "RN-"        # Prefijo opcional para personalizar IDs
```

---

## 6. Criterios de éxito

1. `docpact check tests/fixtures/contrato_completo.py` → 0 errores, 0 warnings
2. `docpact check tests/fixtures/contrato_invalido.py` → 1 error (side effect no declarado)
3. `docpact check soporte/services/tickets.py` (ioDesk-3) → reporta al menos 1 hallazgo real
4. Errores y warnings tienen línea exacta y sugerencia de corrección
5. `--strict` detecta funciones públicas sin CONTRATO

---

## 7. Check-list

```
☐ src/docpact/checker/__init__.py
☐ src/docpact/checker/side_effects.py (AST walker + pattern matcher)
☐ src/docpact/checker/rn_checker.py (regex RN-XXX en cuerpo)
☐ src/docpact/checker/deps_checker.py (existencia de archivos y símbolos)
☐ src/docpact/checker/orchestrator.py (coordina todos los checkers)
☐ src/docpact/config.py (lectura de docpact.toml)
☐ src/docpact/report.py (formateo de salida)
☐ src/docpact/cli/main.py (comando check)
☐ tests/test_side_effects.py
☐ tests/test_rn_checker.py
☐ tests/test_deps_checker.py
☐ tests/test_orchestrator.py
☐ tests/test_config.py
☐ tests/fixtures/side_effects_violation.py (archivo con side effect no declarado)
☐ tests/fixtures/side_effects_ok.py (archivo sin violaciones)
☐ tests/fixtures/rn_violation.py (archivo con RN no referenciada)
☐ docpact check soporte/services/tickets.py (ioDesk-3) funciona
☐ docs/configuracion.md
```

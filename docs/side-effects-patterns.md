# Side Effects Patterns — docpact

## ¿Qué son los side effects?

Los side effects son operaciones que una función realiza fuera de su ámbito
local: escribir en base de datos, enviar emails, hacer requests HTTP, etc.
docpact verifica que los side effects declarados en el CONTRATO coincidan con
los que realmente ejecuta la función.

## Patrones por defecto

Definidos en `config.py:PATRONES_DEFECTO`:

| Categoría | Patrones | Descripción |
|-----------|----------|-------------|
| `db_write` | `.create`, `.save`, `.update`, `.bulk_create`, `.delete`, `transaction.atomic` | Escritura en base de datos |
| `email` | `send_mail`, `EmailMessage` | Envío de correos |
| `external` | `requests.`, `httpx.`, `urllib.request` | Llamadas HTTP externas |
| `audit` | `registrar_evento_bitacora` | Registro de auditoría |
| `notification` | `_notificar_`, `notificar_` | Notificaciones al usuario |

## Cómo funciona el matching

El checker de side effects (`checker/side_effects.py`) recorre el AST de la
función y clasifica cada llamada usando `config.patrones_compilados`.

### Convención de patrones

- **Prefijo `.`** — coincide como *sufijo de método*: `.create` matchea
  `obj.create(...)` pero no `created_at`. Se compila como `\.create\b`.
- **Sin prefijo** — coincide como substring exacto: `send_mail` matchea
  cualquier llamada a `send_mail(...)`.

### Ejemplo

```python
def enviar_reporte(reporte):
    """...
        CONTRATO:
        input:
          reporte: Reporte — ...
        output: bool
        side_effects: email
    """
    send_mail( ... )  # ← detectado por patrón "send_mail"
    return True
```

## Runtime Sentinels

Cuando se ejecutan tests con `docpact check` (sin `--no-runtime`), docpact
envuelve cada función que tiene CONTRATO con tres sentinelas que interceptan
side effects **en tiempo de ejecución**:

### 1. DB Sentinel (`sentinela_db`)

Intercepta consultas SQL vía `django.db.connection.execute_wrapper`. Si detecta
un INSERT/UPDATE/DELETE/CREATE/DROP y `"db_write"` no está en `side_effects`,
lanza `ContractViolationError` en modo `strict` (o warning en modo `warning`).

### 2. Disk Sentinel (`sentinela_disco`)

Monkey-patcha `builtins.open`. Si un archivo se abre en modo
write/append/create (`w`, `a`, `x`, `w+`, etc.) y `"escribe_archivo"` no está
permitido, lanza error.

### 3. Email Sentinel (`sentinela_email`)

Monkey-patcha `smtplib.SMTP.sendmail`. También revisa `django.core.mail.outbox`
después de ejecutar la función.

### Modos de operación

Configurable en `docpact.toml`:

```toml
[docpact.runtime]
modo = "strict"    # Lanza ContractViolationError (default)
modo = "warning"   # Solo advierte, no bloquea
modo = "disabled"  # No intercepta nada
```

## Side effects transitivos

El `transitive_effects` checker sigue llamadas a otras funciones que tengan
CONTRATO y verifica que la cadena de side effects sea correcta.

Ejemplo: si `A()` llama a `B()` y `B()` declara `db_write`, entonces `A()`
también debe declarar `db_write` (a menos que `B()` sea una dependencia
permitida).

Usa `ContractIndex` para resolver contratos de funciones llamadas sin
importarlas (análisis estático).

## Configuración de patrones custom en docpact.toml

```toml
[docpact.side_effects]
db_write = [".create", ".save", ".update", ".bulk_create", ".delete"]
email = ["send_mail", "EmailMessage"]
mi_servicio = ["mi_servicio.", "call_external_api"]
```

## TypeScript side effects

Para archivos TS/JSX, el checker (`checker/ts_sidefx.py`) usa patrones
heurísticos:

| Categoría | Patrones |
|-----------|----------|
| HTTP | `api.*`, `axios.*`, `fetch` |
| Mutación | `mutate`, `setState`, `dispatch` |
| Navegación | `router.*`, `window.open` |
| Almacenamiento | `localStorage`, `sessionStorage` |

Los side effects en TS son solo warnings (no errores) porque el análisis
heurístico puede dar falsos positivos.

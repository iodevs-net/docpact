# Marker Honesty Check

## Problema

Un marker `# RN-XXX` en el body de una función solo indica **presencia**,
no que la función realmente implemente la regla. Esto crea falsa seguridad:

```python
def cancelar(ticket, editor, motivo):
    """CONTRATO:
    rn: [RN-TKT-003]  # "Ticket incorrecto puede ser anulado por supervisión"
    """
    return TicketService.cancelar(ticket, editor, motivo)  # RN-TKT-003
```

Aquí la función solo delega a `TicketService.cancelar()`. Si esa otra
función no implementa RN-TKT-003, nadie lo hace. El marker es decorativo.

## Solución

`docpact.checker.marker_honesty` detecta dos patrones sospechosos usando
AST de Python (sin dependencias nuevas):

### 1. Marker en línea de delegación

Detecta si un `# RN-XXX` está en una línea que es solo una llamada a otro
método (`return X.y(...)` o `x = X.y(...)`).

```
WARN: 'cancelar': RN-TKT-003 marcada en línea de delegación (línea 6).
La función no parece implementar la lógica de la regla, solo delega a
otro método. Verificar manualmente.
```

### 2. Concentración sospechosa

Detecta funciones con demasiadas RNs declaradas (default: >5). Probable
responsabilidad mal asignada o comments decorativos.

```
WARN: 'TicketCreateView.post' declara 17 RNs (umbral: 5). Sospechoso:
probable responsabilidad mal asignada o comments decorativos.
```

## Configuración

En `docpact.toml`:

```toml
[docpact.marker_honesty]
enabled = true              # default: true
max_rns_per_function = 5    # default: 5
```

Para desactivar todo el módulo:

```toml
[docpact.marker_honesty]
enabled = false
```

## Filosofía

docpact **no reemplaza** a las herramientas de testing/linting:

- **ruff** valida estilo y complejidad → docpact no hace eso
- **pytest** valida comportamiento → docpact no ejecuta tests
- **bandit** valida seguridad → docpact no hace eso

docpact ocupa el nicho único de **mapeo regla ↔ código honesto**. El
marker honesty check es una capa de detección estática (sin ejecutar
código) que complementa los tests existentes.

## Limitaciones

- KISS: no intentamos resolver símbolos (X.y → ¿es service externo o
  función local?). Asumimos que `X.y()` con `X` siendo atributo es
  probablemente delegación.
- Solo Python por ahora. TypeScript/JavaScript pendiente.
- WARN, no ERROR: el agente decide si es válido. docpact no bloquea
  commits por esto (todavía).

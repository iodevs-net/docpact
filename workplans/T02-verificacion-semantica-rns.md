# T02 — Verificación semántica de RNs (sin markers)

**Tipo:** Feature + deprecación de check ruidoso
**Prioridad:** Alta — el check de markers genera 80+ falsos positivos en ioDesk-3
**Plan:** 2 releases (Fase A → Fase C)
**Estado actual:** **Fase A implementada y testeada** ✅
**Descubierto en:** ioDesk-3, auditoría RNs 2026-06-03

---

## Principio arquitectónico

**La verificación de RN debe ser estructural, no cosmética.**

El check viejo `check_rn` validaba que existiera un comment string `# RN-XXX`
en el cuerpo. Eso es **mentira como verificación**: el string no prueba que
la regla se implemente. Un agente (o humano) puede escribir el comment sin
tocar la lógica.

**Solución real**: el código se lee y la regla se valida estructuralmente
(state machine, imports, grupos, multi-tenant, patrones).

---

## Plan de releases

### ✅ Release N — Fase A (implementado 2026-06-03)

**Objetivo**: introducir verificación semántica sin romper proyectos
existentes que usan markers.

Cambios en docpact:
- Nuevo módulo `src/docpact/checker/semantic_rn.py` con 5 validadores
  canónicos: `state_transition`, `no_import`, `required_groups`,
  `tenant_safe`, `has_pattern`.
- Orquestador dispatcha a validador semántico por spec (key `type`).
- Markers legacy se mantienen como `warning [LEGACY]` con sugerencia
  explícita de migrar.
- Si CONTRATO declara `rn: [RN-XXX]` pero el proyecto no tiene
  `[docpact.rn_patrones]` configurado, se emite `info` (no error) para
  guiar al agente.
- 253 tests pasando (20 nuevos del dispatcher + 2 de integración + 231
  legacy).

**Impacto en ioDesk-3**: aún no se configuraron validadores semánticos
en su `docpact.toml`. La auditoría debe hacerse en una iteración
posterior (siguiente sesión o PR de iodesk-3).

**Backward compat**:
- Proyectos con markers legacy: siguen funcionando, ven `warning [LEGACY]`.
- Proyectos con `rn_patrones` viejo (sin `type`): fallback a `has_pattern`,
  ven `warning [LEGACY has_pattern]`.
- Proyectos que migren: configuran `type` en cada spec y obtienen
  verificación real.

### ⏳ Release N+1 — Fase C (pendiente)

**Objetivo**: eliminar `check_rn` de markers como fuente de verdad.

Cambios:
- Eliminar `_check_rn_con_fuente` del orquestador.
- Eliminar dependencia de `rn: [RN-XXX]` como string en el cuerpo.
- Solo validadores semánticos (con `type` explícito) son aceptados.
- Proyectos que no hayan migrado: sus RNs no se validan, con un
  `warning` final de migración vencida.

**Gaps conocidos a resolver en Fase C**:
- `state_transition` no resuelve variables en `+ _VAR` (solo flatten BinOp).
  Patrón `EstadoTicket.ATENDER: [...] + _ESTADOS_CON_SALIDA_SUSPENDER_RESOLVER`
  muestra `_ESTADOS_CON_SALIDA_SUSPENDER_RESOLVER` como token literal.
  Fix: leer módulo, resolver Name lookups, sustituir antes de validar.
- Auditoría de ioDesk-3 confirmó: RN-004/005/006 funcionan para checks
  directos (no requieren variable resolution), pero listados completos
  necesitan Fase C.

---

### ✅ Release N — Fase A.5 (2026-06-03)

**Objetivo**: hacer `state_transition` funcional contra código real (no
solo ejemplos sintéticos del test suite).

**Gaps atacados** (descubiertos al aplicar Fase A en ioDesk-3):

1. **`ast.Attribute` como key** — el código real usa `EstadoTicket.ATENDER`,
   no strings. `_dict_literal_a_python` los skipeaba. Fix: extraer
   `node.attr` (último segmento del Attribute).
2. **`ast.AnnAssign`** — el código real usa anotación de tipo:
   `TRANSICIONES_PERMITIDAS: dict[str, list[str]] = {...}`. Eso es
   `ast.AnnAssign`, no `ast.Assign`. Fix: soportar ambos.
3. **`ast.BinOp(Add)` para listas concatenadas** — el código real
   concatena con `+ _ESTADOS_CON_SALIDA_SUSPENDER_RESOLVER`. Fix: aplanar
   recursivamente el BinOp.
4. **Normalización lowercase** — `EstadoTicket.ATENDER` tiene atributo
   `"ATENDER"` (mayúscula), pero el spec del usuario es `"atender"`
   (lowercase, el valor real de la constante en runtime). Fix: lowercase
   en la comparación.

**Limitación documentada**: variables referenciadas (`+ _VAR`) no se
resuelven a nivel AST — queda como gap de Fase C.

**Impacto**: `state_transition` ahora valida correctamente contra la
matriz `TRANSICIONES_PERMITIDAS` de ioDesk-3 para transiciones directas.
3 tests nuevos (25/25 verde, 0 regresiones).

---

## Validadores canónicos (Fase A)

| Tipo | Caso de uso | Spec en docpact.toml |
|---|---|---|
| `state_transition` | Validar que la matriz de transiciones contenga la regla | `from_estado`, `to_estado` o `to_cualquiera`, `modulo`, `matriz_attr` |
| `no_import` | Prohibir imports peligrosos | `patterns` (lista con wildcards `*`), `en_archivo` opcional |
| `required_groups` | Validar que la función chequee grupo/permisos | `allowed` o `forbidden` (lista de grupos) |
| `tenant_safe` | Detectar escapes multi-tenant | `forbid` (default: `unfiltered_objects`) |
| `has_pattern` | Búsqueda de substring (legado compatible) | `patron` (soporta `\|` para OR) |

API pública:
```python
from docpact.checker.semantic_rn import validar_rn, validadores_disponibles
```

---

## Métricas de éxito

- **Fase A (este release)**:
  - 253 tests pasando, 0 regresiones ✅
  - 5 validadores canónicos implementados ✅
  - ioDesk-3 sin migrar todavía (próxima sesión)
- **Fase C (release N+1)**:
  - ioDesk-3 con 232 warnings → ≤ 20 warnings reales
  - Cero markers inline agregados a ioDesk-3
  - Validadores cubren ≥ 70% de las 84 RNs del REGISTRO

---

## Cambios en la API

### Para usuarios de docpact

`docpact.toml`:
```toml
[docpact.rn_patrones]
# Antes (legacy):
"RN-005" = { patron = "suspendido" }

# Ahora (semántico):
"RN-005" = {
    type = "state_transition",
    from_estado = "suspendido",
    to_estado = "atender",
    modulo = "soporte/services/ticket_estados.py",
}
```

Si un spec no tiene `type`, docpact avisa:
> [LEGACY has_pattern] Mueve a validación semántica agregando `type` al spec.

---

## Out of scope

- Reescribir REGISTRO.md en formato estructurado (YAML/TOML).
- Implementar validadores para todas las RNs del ioDesk-3 (siguiente PR).
- Cambiar el formato del CONTRATO (mantener compatibilidad).

---

## Referencias

- Discusión origen: ioDesk-3 sesión 2026-06-03.
- Trabajo previo: T01 (mejora embeddings sparse doc).
- Implementación: rama `feat/t02-fase-a` en repo docpact.

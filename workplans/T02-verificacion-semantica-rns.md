# T02 — Verificación semántica de RNs (sin markers inline)

**Tipo:** Feature + deprecación de check ruidoso
**Prioridad:** Alta — el check actual genera 80+ falsos positivos en ioDesk-3
**Esfuerzo:** Alto — refactor del checker + nuevo módulo semántico + tests
**Descubierto en:** ioDesk-3, auditoría RNs 2026-06-03

---

## Problema

El check `check_rn` (`src/docpact/checker/rn_checker.py`) requiere que cada RN
declarada en el campo `rn: [RN-XXX]` del CONTRATO tenga un **comment marker
inline** `# RN-XXX` en el cuerpo de la función. Esto produce:

1. **Ruido visual en código** — 80+ líneas tipo `# RN-001` repartidas por
   funciones que ya son claras por su nombre y CONTRATO.
2. **Falsos positivos en wrappers** — una vista que delega a `XService.metodo()`
   debe repetir la marker en su cuerpo aunque el marker ya está en el servicio.
3. **Falsos positivos en formato inline-lista** — `# RN-001, RN-002, RN-003`
   ya era detectado correctamente (verificado 2026-06-03), pero el patrón
   "marker dedicado por línea" no es la convención universal.
4. **No verifica nada real** — el marker es un string. Su presencia no prueba
   que la regla de negocio se implemente correctamente.

**Cita del usuario (ioDesk-3, 2026-06-03):**
> "no tiene sentido llenar de marcadones que digan RN XXXX eso no le sirve
> a nadie"

---

## Causa raíz

`check_rn` se diseñó asumiendo que:
- El programador mantiene manualmente la trazabilidad CONTRATO ↔ código.
- El marker es la "prueba" de que la regla se implementó.

Ambas asunciones son falsas en proyectos 100% IA-developed:
- El programador es un agente que escribe CONTRATOs prolijo pero rara vez
  piensa en duplicar el ID como comment.
- La trazabilidad real debe ser **semántica**: ¿el código hace lo que la regla
  dice? (no ¿está el string en algún lugar?).

---

## Solución propuesta: verificación semántica

Reemplazar el check de "marker presente" por un **checker semántico** que
**lee el código y valida la regla directamente**.

### Fase 1: Catálogo de validores por tipo de regla

Cada RN del REGISTRO debería tener un `validador` que docpact sabe cómo
verificar. Tipos iniciales:

| Tipo de regla | Validador | Ejemplo |
|---|---|---|
| **Transición de estado** | Busca la state machine, valida transiciones permitidas | RN-005: `suspendido` → `atender` permitido |
| **Ausencia de integración externa** | Busca imports/librerías prohibidas | RN-FAC-001: no debe haber `from facturacion_erp import` |
| **Restricción de grupo** | Busca `required_groups` y valida whitelist | RN-CL-005: solo admin puede borrar |
| **Multi-tenant** | Busca `TenantModel` y `para_usuario` en queries | RN-DAT-001: no debe haber `unfiltered_objects` salvo escape |
| **Side effect declarado** | Ya existe parcialmente (sentinels runtime) | continúa igual |
| **Inmutable / no delete** | Busca `delete()` en modelos marcados | RN-DAT-001: no debe haber Celery con `.delete()` |

### Fase 2: Mapping RN → validador

Agregar al REGISTRO.md (o `docpact.toml`) qué validador aplica a cada RN:

```toml
[docpact.rn_validators]
"RN-005" = "state_transition: { from: 'suspendido', to_any: ['atender', 'asignado'] }"
"RN-FAC-001" = "no_import: { patterns: ['facturacion_erp', '*sii*'] }"
"RN-DAT-001" = "no_celery_delete: { exclude: ['adjuntos_expirados'] }"
```

### Fase 3: Implementación del runner

Módulo nuevo `src/docpact/checker/semantic_rn.py`:

```python
def check_rn_semantica(
    rn_id: str,
    validador_spec: dict,
    archivos: list[Path],
) -> list[Hallazgo]:
    """Lee el código y valida la regla de negocio."""
    # dispatch al validador apropiado
```

### Fase 4: Deprecar check_rn (markers)

- Mantener `check_rn` por 1 release con `enabled: false` por default
- Comunicar deprecation
- En release siguiente: eliminar la dependencia de markers

---

## Trade-offs

**Pro**:
- Cero ruido en código (no más markers inline)
- Verificación real (¿se cumple la regla? no ¿está el string?)
- El usuario lee código limpio, docpact verifica la regla

**Contra**:
- Esfuerzo alto (estimado 2-3 días de implementación)
- Requiere mantener el mapping RN → validador (work extra al agregar RNs)
- Validadores mal escritos pueden dar falsos negativos (regresión silenciosa)

**Riesgo principal**: cobertura incompleta. Si una RN no tiene validador
definido, docpact no la verifica. Mitigación: warning explícito "RN sin
validador" en el output.

---

## Success criteria

1. ioDesk-3 con 232 warnings → 0-20 warnings (los reales)
2. Cero markers inline agregados a ioDesk-3 (validar con grep)
3. Validadores cubren ≥ 70% de las 84 RNs del REGISTRO
4. Tests E2E: para cada validador implementado, caso positivo + negativo
5. Backward compatible: `rn: [RN-XXX]` sigue funcionando, solo cambia el
   criterio de validación

---

## Out of scope (no en este workplan)

- Reescribir REGISTRO.md en formato estructurado (YAML/TOML)
- Implementar validadores para todas las RNs (empezar por 5-10 críticas)
- Cambiar el formato del CONTRATO (mantener compatibilidad)

---

## Referencias

- Discusión origen: ioDesk-3 sesión 2026-06-03 (memoria `feedback/audit-vs-implement`)
- Trabajo previo: T01 (mejora embeddings sparse doc)
- ioDesk-3 PR relacionado: `fix/rn-huerfanas-a-contrato` (rama actual, declarado
  solo RN-DEV-003 en CONTRATO)

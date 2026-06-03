# T01 — Mejora del input semántico del indexer

**Tipo:** Bug + mejora (no es fase nueva — ver [workplans/README.md](./README.md))
**Prioridad:** Media — búsqueda semántica funciona pero devuelve resultados ruidosos
**Esfuerzo:** Bajo — refactor acotado a una función + pruebas
**Descubierto en:** ioDesk-3, auditoría RNs 2026-06-03 (rama `fix/docpact-rn-comments`)

---

## Problema

La búsqueda semántica de docpact (MCP `buscar_por_intencion`) devuelve resultados
con scores altos pero **baja relevancia** cuando la función tiene nombre genérico
o docstring vacío. Ejemplo real verificado:

```
Query: "crear un ticket de soporte para un cliente"
Top 5 devueltos (todos con score 0.96x):
  - get_tickets_para_usuario
  - paginar_tickets
  - get                    ← (un método .get() genérico)
  - obtener_filtro_tenant
  - iodesk_ticket_actividad_desde
FUNCIÓN REAL QUE QUERÍAMOS ENCONTRAR:
  - soporte/services/tickets.py:147 — TicketService.create (rn: [RN-001, RN-008, RN-PRI-001])
    Nombre indexado: "create"  ← demasiado genérico para semántica
```

## Causa raíz

En `src/docpact/index.py` líneas 88-101, la función `_generate_embeddings()`
arma el documento de embedding así:

```python
parts = [
    f["funcion"],                                      # nombre solo
    f["contrato"].get("output_descripcion", "") or "", # suele estar vacío
    " ".join(f.get("rn_ids", [])),                     # solo IDs
    Path(f["archivo"]).name,                           # filename
]
doc = " ".join(p for p in parts if p)
```

Para `create` con `rn: [RN-001, RN-008]` el input al embedder es literalmente:

```
"create RN-001 RN-008 tickets.py"
```

Con ese input, **ningún modelo semántico** puede hacer buen retrieval — falta
contexto de QUÉ hace la función.

## Por qué importa

- Búsqueda semántica es feature de productividad clave del MCP.
- Sin buen input, el `busqueda_tipo: "semantica"` del response miente sobre
  la calidad del resultado.
- Con buen input, el mismo modelo `intfloat/multilingual-e5-small` (384 dims)
  puede dar resultados MUCHO mejores sin cambiar nada más.

## Solución propuesta

Enriquecer el doc de embedding con todo el CONTRATO disponible. Priorizar
lo que ya está parseado en el índice (no requiere re-parsear).

### Cambio 1: función indexada por el nombre completo de path

En `index.py` líneas 92-97, expandir el doc a:

```python
def _build_func_doc(f: dict[str, Any], rns_index: dict[str, dict]) -> str:
    """Arma el doc semántico para una función a partir de su índice."""
    parts: list[str] = [f["funcion"]]

    # 1. Descripción del output (CONTRATO)
    output_desc = f["contrato"].get("output_descripcion", "")
    if output_desc:
        parts.append(output_desc)

    # 2. Descripciones de CADA parámetro de input
    for param_name, param_meta in f["contrato"].get("input", {}).items():
        if isinstance(param_meta, dict) and param_meta.get("descripcion"):
            parts.append(f"{param_name}: {param_meta['descripcion']}")

    # 3. Side effects como texto (CONTRATO)
    side_effects = f["contrato"].get("side_effects", [])
    if side_effects:
        parts.append("efectos: " + ", ".join(side_effects))

    # 4. RN IDs + sus descripciones del registro
    for rn_id in f.get("rn_ids", []):
        rn_meta = rns_index.get(rn_id, {})
        rn_desc = rn_meta.get("descripcion", "")
        if rn_desc:
            parts.append(f"{rn_id}: {rn_desc}")
        else:
            parts.append(rn_id)

    # 5. Path relativo del archivo (mantiene locality)
    parts.append(f["archivo"])

    return " ".join(p for p in parts if p)
```

### Cambio 2: misma mejora para RNs

En `index.py` líneas 103-110, expandir el doc de cada RN para que el matching
`función ↔ RN` mejore en ambos lados:

```python
# Antes:
doc = f"{rn_id} {rn['descripcion']}"

# Después:
parts = [rn_id, rn["descripcion"]]
# Agregar primeros 300 chars de la sección "Regla:" del REGISTRO si existe
if "regla_completa" in rn:  # ya parseado en rns_index
    parts.append(rn["regla_completa"][:300])
# Archivos donde se implementa
for f in rn.get("implementada_en", []):
    parts.append(f)
doc = " ".join(parts)
```

### Cambio 3: bonus — incluir firma de función

En `index.py`, agregar la firma de la función (parámetros con tipos) al índice
durante el parse. Esto da al embedder pistas como:
```
"create(cliente_id: int, titulo: str, descripcion: str, prioridad: str, usuario_asignado_id: int | None)"
```

Requiere un cambio mínimo en `parser/` para emitir la firma. Es opcional — los
cambios 1 y 2 ya darían la mayor parte del beneficio.

## Criterios de éxito

Tras aplicar cambios 1 y 2 (mínimo viable):

1. **Re-generar el índice** en ioDesk-3:
   ```bash
   cd /home/lvergara/dev/proyectos/helpdesk-ionet/iodesk-3
   docpact index --force
   ```
   `has_embeddings: true` debe seguir siendo true.

2. **Verificar que `TicketService.create` aparece en top-3** para queries
   relacionadas a creación de tickets. Test sugerido:
   ```python
   # tests/test_semantic_search.py
   def test_crear_ticket_semantic():
       """Verificar que 'crear ticket' retorna la función real de creación."""
       resultados = buscar_por_intencion("crear un ticket de soporte")
       nombres_top3 = [r["funcion"] for r in resultados["resultados"][:3]]
       assert "create" in nombres_top3, \
           f"create no apareció en top 3: {nombres_top3}"
   ```

3. **Re-verificar el doctor** — no debe romper nada:
   ```bash
   docpact doctor
   ```

4. **Tests existentes pasan**: `pytest tests/test_*semantic*` (si existen) +
   `pytest tests/test_index.py` (cubren serialización del índice).

## Lo que NO cambia

- **Modelo**: sigue `intfloat/multilingual-e5-small` (multilingüe, suficiente).
- **Storage**: el JSON del índice crece ~3-5x pero sigue siendo manejable
  (5 MB actual → ~15-20 MB esperado).
- **API del MCP**: ningún breaking change. Los campos del response son los mismos.

## Trade-offs conocidos

- **Tamaño del índice**: ~3-5x más grande. Si el repo tiene 10k+ funciones,
  pasar de 50 MB a 200 MB podría ser problema. Verificar en proyectos grandes.
- **Tiempo de indexado**: lineal con la cantidad de texto embedido. Probablemente
  2-3x más lento (de ~10s a ~30s para ioDesk-3 con 543 funciones).
- **Costo de RAM del embedder**: sin cambios.

## Contexto adicional (descubierto en la misma sesión)

**Bug de instalación relacionado** (ya arreglado por el usuario en ioDesk-3):
el CLI `docpact` tiene shebang `#!/usr/bin/python3` y fastembed debe estar
instalado en ese Python específico. Si no, `has_embeddings: false` y la
búsqueda cae silenciosamente a keyword. `docpact doctor` lo detecta.

**Limitación de Claude Code**: el MCP server de docpact inicializa el embedder
una sola vez al arrancar (`mcp_server.py:52-53`). Si fastembed se instala DESPUÉS
de iniciar la sesión, hay que reiniciar Claude Code para que tome el cambio.
No es responsabilidad de docpact arreglar esto.

## Verificación independiente

Antes de mergear, regenerar el índice en ioDesk-3 (que ya tiene el fix de
instalación hecho) y correr manualmente:

```python
from docpact.mcp_server import tool_buscar_por_intencion
print(tool_buscar_por_intencion("crear un ticket"))
print(tool_buscar_por_intencion("validar permisos de usuario"))
print(tool_buscar_por_intencion("facturar horas de un cliente"))
```

Comparar el ranking antes/después. La función correcta debe subir al top 3.

## Archivos a tocar

- `src/docpact/index.py` — función `_generate_embeddings()` y/o helper
  `_build_func_doc()` (cambio 1 y 2)
- `src/docpact/parser/` — opcional, agregar firma al output parseado (cambio 3)
- `tests/test_index.py` — agregar test de regresión semántico
- (Opcional) actualizar `docs/protocolo-v1.md` si se cambia el schema del
  embedding doc — pero NO es schema público, es interno.

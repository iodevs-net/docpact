# Better Code for Agents

> **Qué es:** Prácticas concretas, basadas en evidencia, para que el código fuente
> sea más fácil de leer y modificar por agentes de IA. Sin humo académico, sin
> lenguajes experimentales, sin rewrites imposibles.
>
> **Para quién:** ioDesk-3 y cualquier proyecto que quiera ser "AI-native" de verdad.
>
> **Base:** 9 informes de investigación: Claude + ChatGPT 5.4 + DeepSeek + Perplexity +
> Gemini 3.5 Flash + Qwen + Minimax + Gemini 3.1 Pro + Perplexity-ChatGPT 5.4 + 40+ papers +
> SWE-bench + ProgramBench +
> auditoría directa de ioDesk-3 (27 hallazgos, 22 corregidos en 90 min).

---

## EVIDENCIA CENTRAL: Los agentes NO piensan como humanos

Siete hallazgos que explican POR QUÉ el código para humanos no funciona para
agentes:

### 1. ProgramBench: Los agentes rechazan naturalmente la modularidad humana

Cuando se les pide generar software desde cero sin restricciones, los agentes
producen proyectos con una mediana de **3 archivos** (vs. 15 en código humano).
Las funciones son **1.46x a 1.62x más largas**. Profundidad máxima de directorio: 1.

**Conclusión:** Forzar modularidad estilo humano (DRY, herencia, muchas capas
de abstracción) es antinatural para un agente. El costo de saltar entre archivos
es mayor que el costo de leer código repetitivo.

### 2. Context Rot: El contexto largo degrada la precisión ~30%

La atención cuadrática de los Transformers causa que la información en segmentos
intermedios del contexto pierda precisión ("lost in the middle"). Esto se agrava
en diálogos multi-turno, donde la caída llega a ~39%.

**Conclusión:** Archivos pequeños y módulos auto-contenidos no son lujo — son
necesidad estructural para que el agente no "olvide" lo que leyó al principio.

### 3. SWE-bench: El scaffold importa más que el modelo

Cambiando solo cómo se presenta el código al agente (estructura, información
incluida, formato de prompts) se altera drásticamente el rendimiento, incluso
con el mismo modelo base.

**Conclusión:** ioDesk puede mejorar el rendimiento de sus agentes sin cambiar
de modelo — solo mejorando cómo estructura su código.

**Corolario práctico:** Addy Osmani (2026) documentó que la presencia de un
archivo AGENTS.md bien estructurado reduce el wall-clock runtime de los agentes
en **28.64%**. El agente no pierde tiempo entendiendo el proyecto — lo lee en
el AGENTS.md y empieza a trabajar.

### 4. Hidden Cost: El formateo humano consume 25-35% de tokens sin aportar señal

Eliminar indentación, espacios y saltos de línea reduce ~24.5-34.9% de tokens
en tareas de completado (Fill-in-the-Middle) sobre 4 lenguajes y 10 LLMs, con
cambios en precisión ≤4.2% (a menudo no significativos estadísticamente).

**Conclusión:** La legibilidad humana tiene un costo directo en tokens. No es
gratis. Cada línea en blanco, cada nivel de indentación, cada espacio que hace
el código "lindo" para humanos es ruido para el agente.

**Matiz importante:** Para ioDesk, donde humanos y agentes comparten el código,
no se trata de eliminar el formateo. Se trata de **no agregar formateo que no
sirva a ambos lectores.** Las líneas en blanco entre funciones son útiles. La
indentación excesiva (6+ niveles) no lo es.

### 5. Agentless: El cuello de botella no es generar código — es encontrar el archivo correcto

**Hallazgo:** El paper Agentless (Xia et al., 2024) demuestra que ~60% de los
fallos en SWE-bench ocurren porque el agente **no encuentra los archivos
correctos**, no porque no sepa escribir el fix. Un pipeline que optimiza la
fase de localización de archivos supera a sistemas complejos de agentes.

**Conclusión:** La prioridad #1 para ioDesk no es hacer el código más "legible
por IA" — es hacer que el agente pueda **encontrar** el archivo que necesita
sin explorar 20 carpetas. Las RELACIONES en los módulos, los docstrings de
directorio, y los CONTEXT.md por módulo no son lujo — son lo que resuelve el
60% del problema.

**Fuente:** arXiv:2407.01489 — Agentless: Demystifying LLM-based Software
Engineering Agents

### 6. CodeStruct: AST nombrado reduce errores de 46.6% a 7.2%

**Hallazgo:** AWS AI Labs (arXiv 2604.05407, 2026) demostró que operar sobre
**entidades AST nombradas** en lugar de spans de texto reduce los fallos de
parche vacío de 46.6% a 7.2%. GPT-5-nano mejoró 20.8% al usar este método.

**Qué significa:** No es lo mismo decirle al agente "cambia la línea 42" que
"cambia el método `validar_rut()` en la clase `ClienteValidator`." El agente
entiende y ejecuta mejor cuando el contrato se expresa en términos de la
estructura del código (AST), no de su posición textual.

**Conclusión para ioDesk:** Las referencias a funciones, clases y métodos
deben hacerse por nombre simbólico, no por ubicación. Los CONTRATOS y las
instrucciones a agentes deben decir "modificar `TicketService.crear()`" no
"modificar la línea 47 de tickets.py".

**Fuente:** arXiv:2604.05407 — CodeStruct: AST-based Code Editing

### 7. Los nombres de variables NO deben ser cortos — deben ser semánticos

**Hallazgo:** Un estudio de ablación controlada (arXiv 2508.06414) muestra que
eliminar nombres significativos de variables y funciones causa caídas de hasta
**30 puntos porcentuales** en generación de código. Los LLMs priorizan
identificadores con significado semántico sobre convenciones de formato.

**Qué significa:** La recomendación de "variables cortas para ahorrar tokens"
es incorrecta. El costo de tokens de un nombre largo se paga muchas veces en
alucinaciones evitadas. `cliente_con_tickets_pendientes` es mejor que `c_ctp`.

**Actualización a la Práctica #1:** En los CONTRATOS y en el código, usar
nombres explícitos y semánticos. No abreviar para ahorrar tokens.

**Fuente:** arXiv 2508.06414 — What Builds Effective In-Context Examples for
Code Generation?

---

## LAS 10 PRÁCTICAS

### 1. CONTRATOS EXPLÍCITOS > DOCSTRINGS NARRATIVOS
#### (Y eventualmente: metadatos JSON incrustados > texto libre)

Los docstrings narrativos fuerzan al agente a **inferir** límites, side effects,
y excepciones. Los agentes son malos infiriendo — alucinan.

```python
# ❌ PARA HUMANOS: el agente tiene que inferir límites, errores, side effects
def sumar_sesiones(tickets: list) -> float:
    """Calcula horas totales a partir de lista de tickets con sesiones prefetched."""
    total = 0.0
    for t in tickets:
        for s in t.sesiones.all():
            if s.fin:
                total += (s.fin - s.inicio).total_seconds()
    return round(total / 3600, 2)

# ✅ NIVEL 1 — PARA AGENTES: bloque CONTRATO estructurado
def sumar_sesiones(tickets: list[Ticket]) -> HorasCalculadas:
    """
    CONTRATO:
      Input:  tickets con .prefetch_related("sesiones")
              Sin prefetch → N+1 queries
      Output: HorasCalculadas(total_horas, total_segundos, cantidad_sesiones)
      Side effects: Ninguno
      RN: RN-002 (solo sesiones completadas descuentan)
      Borde: tickets vacio → HorasCalculadas(0,0,0)
             sesion sin fin → se ignora
    """

# ✅✅ NIVEL 2 — EVOLUCIÓN: metadatos JSON en vez de texto
# {"input": {"tickets": "list[Ticket] (prefetch_related sesiones)"},
#  "output": {"type": "HorasCalculadas", "fields": ["total_horas","total_segundos","cantidad_sesiones"]},
#  "side_effects": null,
#  "rn": ["RN-002"],
#  "borde": {"tickets_vacio": "HorasCalculadas(0,0,0)",
#            "sesion_sin_fin": "ignorada"}}
def sumar_sesiones(tickets: list[Ticket]) -> HorasCalculadas:
    total = 0.0
    ...
```

**Evidencia:** SWE-bench (scaffold > modelo). GrammarCoder (reglas gramaticales
> composición probabilística). ChatGPT 5.4 (metadatos JSON reducen alucinaciones).

---

### 2. WET > DRY PARA AGENTES

DRY fuerza al agente a saltar entre archivos. Cada abstracción es un contexto
nuevo que cargar. WET mantiene toda la información local.

| Estilo | Costo para el agente |
|---|---|
| DRY | Leer A → inferir abstracción → saltar a B → volver a A |
| WET | Leer una vez. Todo está ahí. |

**Evidencia:** ProgramBench (3 archivos vs 15). Kang et al. 2024 (código
monolítico supera consistentemente al modular en generación).

**En la práctica para ioDesk:**
- No más de 2 niveles de abstracción. Si necesitás 3, la función merece su CONTRATO
- Si una abstracción existe solo para evitar repetir 3 líneas, no vale la pena
- El WET natural de los LLMs (tienden a repetir código) no es un bug — es una
  señal de cómo procesan información. Trabajar con eso, no contra eso.
- **Atención:** el paper DeRep (arXiv:2504.12608) advierte que la repetición
  excesiva también daña la calidad. El objetivo no es repetir sin límite — es
  mantener el contexto local sin llegar a la redundancia patológica.

---

### 3. DTOs COMO CONTRATOS, NO COMO TYPING

`@dataclass(frozen=True)` evita que un agente invente campos. Si el DTO no tiene
el campo, Python explota en import time — no en producción.

**Reglas:**
- **Todo** lo que cruza una frontera (view→service→selector→frontend) tiene un DTO
- **No existen** `dict` sueltos en returns públicos
- Cada DTO tiene: nombre, tipo en cada campo, y propósito

```python
@dataclass(frozen=True)
class HorasCalculadas:
    """Contrato: esto es lo único que devuelve sumar_sesiones()."""
    total_horas: float
    total_segundos: float
    cantidad_sesiones: int
    cantidad_tickets_procesados: int
```

**ioDesk ya lo hace bien** — 42 DTOs. El paso siguiente: asegurar que no haya
returns sin DTO.

---

### 4. REGLAS DE NEGOCIO CON ID EN EL CÓDIGO

```python
# RN-010: Bloqueo al 100% sin aprobación de interlocutor
if resumen.disponibles <= 0 and not ticket.horas_extra_aprobadas:
    raise PermissionError("Bolsa de horas agotada.")
```

Cada línea que toca una regla de negocio lleva su ID. Referencia bidireccional:
el código documenta la regla, la regla documenta el código.

---

### 5. LOCALIDAD DE CONTEXTO

Un agente no explora — **lee secuencialmente.** Cada salto entre archivos gasta
tokens y contexto. Context Rot garantiza ~30% de pérdida si la información
crítica está en segmentos medios.

**Reglas:**
- Cada módulo tiene RELACIONES declaradas:
```python
# RELACIONES:
#   Depende de: soporte/models/ticket.py, soporte/constants.py
#   Usado por: soporte/views/tickets.py, soporte/views/ticket_resolver.py
```
- Si una función necesita contexto externo, se declara en el CONTRATO
- **Chunking por AST, no por líneas:** no dividir funciones/clases entre
  archivos. Cada archivo debe contener unidades semánticas completas.
  (Evidencia: cAST, AST-T5 — chunking AST-aware da 2-4x mejora vs ventana fija)

**ioDesk ya hace** `[Contiene/NO contiene]` ✅. Falta agregar RELACIONES.

---

### 6. ERRORES EXPLÍCITOS, NO SILENCIOSOS

```python
# ❌ El agente no sabe qué falló
except Exception as e:
    return JsonResponse({"error": str(e)}, status=400)

# ✅ El agente sabe exactamente qué pasó y cómo manejarlo
except Ticket.DoesNotExist:
    return JsonResponse({"error": "Ticket no encontrado"}, status=404)
except ValidationError as e:
    return JsonResponse({"error": e.message}, status=400)
except Exception:
    logger.error("Error inesperado creando ticket", exc_info=True)
    return JsonResponse({"error": "Error interno"}, status=500)
```

---

### 7. ARCHIVOS < 300 LÍNEAS CON CHUNKING POR AST

No 300 líneas arbitrarias — 300 líneas de **unidades semánticas completas.**
Si una función tiene 200 líneas y es una unidad cohesiva, no se divide. El
límite es: cada archivo contiene funciones/clases completas, y ninguna función
debería exceder ~50 líneas.

| Tamaño | Precisión del agente |
|---|---|
| < 100 líneas | Muy alta |
| 100-300 | Alta |
| 300-500 | Media — considerar dividir por AST |
| > 500 | Baja — dividir YA |

**ioDesk viola:** `soporte/services/tickets.py` (594), `soporte/selectors/dtos.py` (~700).

---

### 8. PRIMERO DTOs, LUEGO FUNCIÓN, LUEGO IMPLEMENTACIÓN

```python
# ✅ ORDEN AI-NATIVE:
# 1. DTOs
@dataclass(frozen=True)
class HorasCalculadas:
    total_horas: float
    total_segundos: float

# 2. Función con CONTRATO
def sumar_sesiones(tickets: list[Ticket]) -> HorasCalculadas:
    """CONTRATO: ..."""
    # 3. Implementación
```

El agente construye el modelo mental antes de leer los detalles.

---

### 9. COMENTARIOS COMO PIVOTES LÓGICOS, NO COMO NARRATIVA

El paper MANGO demuestra que los comentarios en línea funcionan mejor cuando
actúan como **pasos lógicos** (no como descripciones de lo que el código hace).
Cuando el agente ve `# Paso 1: validar entrada`, entiende la estructura del
algoritmo antes de leer el código.

```python
# ❌ Narrativa: describe lo que el código ya dice
# Suma todas las sesiones completadas
total = sum(s.duracion for s in sesiones if s.fin)

# ✅ Pivote lógico: estructura el razonamiento
# RN-002: solo sesiones completadas descuentan horas del contrato
total = sum(s.duracion for s in sesiones if s.fin)
```

**En la práctica:**
- Los comentarios son para estructurar el **razonamiento**, no para describir
  la **sintaxis**
- Cada comentario debería responder "¿por qué?" o "¿qué regla aplica aquí?",
  no "¿qué hace esta línea?"
- Si podés eliminar el comentario y el código sigue siendo igual de claro,
  el comentario sobra

---

## CHECKLIST VERIFICABLE POR MÁQUINA

| # | Práctica | Cómo verificarlo |
|---|---|---|
| 1 | CONTRATO o metadatos JSON en funciones públicas | `grep -rn "CONTRATO:\|# {" ` |
| 2 | DTO frozen en toda frontera | `grep -rn "@dataclass"` debe cubrir todos los returns públicos |
| 3 | RN-XXX en reglas de negocio | `grep -rn "RN-" --include="*.py"` |
| 4 | RELACIONES en módulos | `grep -rn "^#.*\(Depende\|Usado\|No depende\)"` |
| 5 | except Exception con exc_info | `grep -rn "except Exception" \| grep -v "exc_info"` → 0 |
| 6 | Archivos < 300 líneas | Archivos > 300 líneas → evaluar división por AST |
| 7 | Funciones < 50 líneas | `ruff check --select C90` |
| 8 | Side effects declarados | CONTRATO dice "Side effects: ..." o JSON equivalente |
| 9 | Chunking por AST (no partir funciones) | Ninguna función aparece en 2 archivos |
| 10 | Navegabilidad (sin utils.py, con __init__.py declarativo) | `grep -rn "utils\.py\|helpers\.py\|common\.py" \| wc -l` → 0 |

---

## LO QUE SÍ ESTÁ PROBADO (implementable MAÑANA)

| Práctica | Evidencia | Esfuerzo |
|---|---|---|
| CONTRATOS explícitos | SWE-bench, GrammarCoder, ChatGPT 5.4 | Bajo |
| WET sobre DRY | ProgramBench, Kang et al. 2024 | Medio |
| DTOs frozen | ioDesk (42 DTOs funcionando) | Bajo |
| RN-XXX en código | ioDesk ya lo hace parcialmente | Muy bajo |
| Archivos < 300 líneas por AST | Context Rot + cAST (2-4x mejora) | Medio |
| Errores explícitos | Sentry + exc_info | Bajo |
| LOCALIDAD + RELACIONES | ioDesk ya hace "Contiene/NO contiene" | Muy bajo |
| Orden AI-native (DTO → fn) | Sentido común + papers | Bajo |
| Comentarios como pivotes lógicos | MANGO (Pass@k mejora vs CoT) | Muy bajo |

---

## LO QUE NO ESTÁ PROBADO (no implementar en ioDesk)

| Idea | Por qué no |
|---|---|
| **AST serializado como source of truth** | Paper-only. Overhead > beneficio para equipos chicos. |
| **Mono-archivo (MACS)** | Colisiona con límites de contexto. Impracticable > 5K líneas. |
| **Lenguaje AI-native (lenguaje A)** | No existe ecosistema. |
| **TOON / Token Sugar** | Experimental. Requieren formatos que ningún developer conoce. |
| **S-expressions como formato intermedio** | Interesante académicamente. Impracticable con humanos. |
| **Eliminar toda indentación y espacios** | Funciona en benchmarks, pero en equipo mixto humano+IA la legibilidad humana sigue importando. |

**Casos frontera:**
- **Agentis** (DAG binario como storage, "todo es prompt"): existe como prototipo.
  No está maduro para producción, pero es el proyecto más cercano a un "lenguaje
  AI-native" real. Vale la pena seguirle el rastro.
- **Dana** (keyword `agent` en el lenguaje): mismo caso. Interesante, inmaduro.

---

## VALIDACIÓN CRUZADA: QWEN vs 8 INFORMES

Qwen propone una arquitectura (ANCF) con 7 ideas centrales. ¿Cuáles resisten el
cruce con la evidencia empírica de los otros 8 informes?

| Idea de Qwen | Validación cruzada | Veredicto |
|---|---|---|
| **Metadatos estructurados obligatorios** (> docstrings) | ChatGPT 5.4: contratos JSON. Claude: 60% localization. DeepSeek: CodeStruct 46.6%→7.2% | ✅ **VÁLIDO** — 3 informes confirman |
| **Grafo de dependencias como metadata** | Claude: 60% localization. DeepSeek: L-SDF 110K→8K. ProgramBench: 3 vs 15 archivos | ✅ **VÁLIDO** — 3 informes confirman |
| **Vericoding: pre/post condiciones** | DeepSeek: CodeStruct 46.6%→7.2%. ChatGPT 5.4: MANGO mejora Pass@k | ✅ **VÁLIDO** (parcial — no al nivel de prueba formal completa) |
| **Validation Oracles post-cambio** | SWE-bench: scaffold > modelo. Claude: localización es bottleneck | 🟡 **PARCIAL** — la idea es correcta pero Qwen no propone implementación |
| **Execution Registry (log de agente)** | Ningún informe lo cubre. No hay paper. | 🔴 **ESPECULATIVO** — interesante pero sin respaldo |
| **Formato .ancf separado** | Agentis/Dana existen como prototipos. Ninguno probado en producción. | 🔴 **NO VÁLIDO** — no hay evidencia de que un formato nuevo supere a código bien estructurado |

**Conclusión del cruce:** 3 ideas validades, 1 parcial, 2 especulativas. Qwen
aporta visión arquitectónica pero necesita el respaldo de los otros informes
para ser creíble. Y los otros informes aportan evidencia pero necesitan la
visión de Qwen para organizarse en un plan coherente. La síntesis de ambos es
más fuerte que cualquiera de los dos por separado.

---

## CONCLUSIÓN

Los 9 informes convergen en el mismo diagnóstico: **el código para humanos no
es óptimo para agentes.** Pero difieren en el extremo de la solución.

Los informes más prácticos (Perplexity, ChatGPT 5.4) recomiendan: contratos
explícitos, WET sobre DRY, DTOs, chunking por AST, y eliminar ruido visual.
Los más radicales (Gemini 3.1 Pro, ChatGPT 5.4 en su versión "post-humana")
proponen rewrites completos (mono-archivo, serialización AST, lenguajes nuevos).

La postura de este documento es: **ioDesk no necesita un rewrite. Necesita
aplicar sistemáticamente las 9 prácticas.** Ninguna requiere cambiar de lenguaje,
reestructurar el proyecto, o adoptar formatos experimentales. Todas se pueden
implementar progresivamente, verificando con un `grep` que se hayan aplicado.

La ventaja competitiva no está en las prácticas (ninguna es nueva). Está en **la
decisión de aplicarlas todas, consistentemente, y verificar que se mantengan.**
Eso es lo que ningún proyecto hace hoy.

---

*Documento consolidado a partir de 8 informes de investigación:*
- *Perplexity — investigación general (70% señal útil)*
- *ChatGPT 5.4 — Hidden Cost, MANGO, contratos JSON (75% señal útil)*
- *Perplexity-ChatGPT 5.4 — Agentis/Dana, chunking AST, DeRep (65% señal útil)*
- *Gemini 3.5 Flash — ProgramBench, Context Rot (50% señal útil)*
- *Gemini 3.1 Pro — ideas perdidas en ruido (20% señal útil)*
- *Claude — Agentless (60% localización), calidad de evidencia [EMP]/[INF]/[DEB] (80% señal útil)*
- *DeepSeek — CodeStruct (46.6%→7.2%), nombres semánticos (30pp drop), L-SDF (75% señal útil)*
- *Minimax — AGENTS.md reduce 28.64% runtime, RePOMIX (60% señal útil)*
- *Destilación y síntesis: DeepSeek TUI v0.8.24*

> **Nota sobre calidad de evidencia:** Claude fue el único informe que etiquetó
> cada hallazgo como [EMP] (empírico), [INF] (inferencia razonada) o [DEB]
> (debate abierto). Los otros informes presentaron inferencias como evidencia.
> Este documento destilado prioriza hallazgos [EMP] sobre [INF], y marca
> explícitamente los debates abiertos. No todo lo que suena a "estudio muestra"
> está realmente medido.

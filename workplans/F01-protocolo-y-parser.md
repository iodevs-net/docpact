# Fase 1 — Protocolo CONTRATO + Parser Python

**Objetivo:** Definir formalmente el formato CONTRATO e implementar un parser
que lo extraiga de archivos Python. Al final de esta fase, docpact puede leer
CONTRATOS de cualquier archivo `.py` y validar su estructura sintáctica.

**Principio Pareto:** El 80% del valor de docpact viene de *poder leer
contratos*. Sin parser no hay verificador. Un parser bien diseñado permite
todas las fases siguientes. El parser además ya es útil como herramienta
independiente: "extraer contratos de un módulo para que un agente los lea".

**Duración estimada:** 2-3 días de trabajo agentic.
**Depende de:** Nada (es la primera fase).
**Precuela técnica:** El spike técnico en ioDesk-3 demostró que el formato
CONTRATO en docstrings funciona. Ahora hay que formalizarlo.

---

## 1. Definición del Protocolo CONTRATO (spec)

### 1.1 Formato canónico

```
CONTRATO:
  input:
    param1: type — descripción
    param2: type | None — descripción
  output: type — descripción
  side_effects: lista de efectos separados por coma, o "ninguno"
  rn:
    - RN-XXX: descripción corta (opcional)
    - RN-YYY: descripción corta
  borde:
    - condición: comportamiento esperado
    - condición: comportamiento esperado
  dependencias:
    - modulo/archivo.py::Simbolo
    - modulo/archivo.py::Clase.metodo
```

### 1.2 Reglas del protocolo

1. **`CONTRATO:` es obligatorio** como palabra clave. Distingue un contrato de
   un docstring narrativo normal.
2. **Los campos son:**
   - `input:` — Opcional. Cada línea es un parámetro: nombre, tipo, descripción.
   - `output:` — Opcional. Tipo y descripción del retorno.
   - `side_effects:` — **Obligatorio** para funciones con efectos. Valor
     especial `ninguno` cuando no hay efectos.
   - `rn:` — Opcional. Lista de IDs de reglas de negocio que la función implementa.
   - `borde:` — Opcional. Casos borde documentados.
   - `dependencias:` — Opcional. Referencias a otros módulos/símbolos.
3. **Indentación:** 2 espacios bajo cada campo. Estilo YAML-like.
4. **Ubicación:** Dentro del docstring de la función, después de la descripción
   narrativa (si existe), antes del `return` del docstring.
5. **Una función = un CONTRATO.** No hay contratos multi-función.

### 1.3 Schema JSON del protocolo (para validación)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://docpact.dev/schemas/contrato-v1.json",
  "title": "CONTRATO",
  "type": "object",
  "properties": {
    "input": {
      "type": "object",
      "patternProperties": {
        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
          "type": "object",
          "properties": {
            "type": { "type": "string" },
            "description": { "type": "string" }
          },
          "required": ["type"]
        }
      },
      "additionalProperties": false
    },
    "output": {
      "type": "object",
      "properties": {
        "type": { "type": "string" },
        "description": { "type": "string" }
      },
      "required": ["type"]
    },
    "side_effects": {
      "oneOf": [
        { "type": "string", "pattern": "^ninguno$" },
        {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1
        }
      ]
    },
    "rn": {
      "type": "array",
      "items": {
        "oneOf": [
          { "type": "string", "pattern": "^RN-[0-9]{3,}$" },
          {
            "type": "object",
            "properties": {
              "id": { "type": "string", "pattern": "^RN-[0-9]{3,}$" },
              "description": { "type": "string" }
            },
            "required": ["id"]
          }
        ]
      }
    },
    "borde": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "condition": { "type": "string" },
          "behavior": { "type": "string" }
        },
        "required": ["condition", "behavior"]
      }
    },
    "dependencias": {
      "type": "array",
      "items": {
        "type": "string",
        "pattern": "^[a-zA-Z0-9_/.\\-]+(::[a-zA-Z_][a-zA-Z0-9_.]*)?$"
      }
    }
  },
  "required": ["side_effects"],
  "additionalProperties": false
}
```

---

## 2. Arquitectura del Parser

### 2.1 Funcionamiento

```
Archivo .py
    │
    ▼
[AST Module Parser]  ← usa ast module de stdlib
    │
    ▼
[Docstring Extractor]  ← extrae docstrings de funciones/clases públicas
    │
    ▼
[CONTRATO Lexer]  ← busca bloque CONTRATO: dentro del docstring
    │
    ▼
[CONTRATO Parser]  ← parsea campos YAML-like → dict estructurado
    │
    ▼
[Schema Validator]  ← valida contra JSON Schema
    │
    ▼
ContratoExtraido {
    funcion: str,
    tipo: "function" | "method" | "class",
    archivo: str,
    linea: int,
    campos: dict,
    raw_text: str,
    errores: list[ErrorParser]
}
```

### 2.2 Estructura del proyecto

```
docpact/
├── pyproject.toml
├── src/
│   └── docpact/
│       ├── __init__.py
│       ├── parser/
│       │   ├── __init__.py
│       │   ├── extractor.py    ← Extrae docstrings del AST
│       │   ├── lexer.py        ← Tokeniza bloque CONTRATO
│       │   └── parser.py       ← Convierte tokens a dict
│       ├── schema/
│       │   ├── __init__.py
│       │   ├── validator.py    ← Valida contra JSON Schema
│       │   └── contrato-v1.json
│       ├── models/
│       │   ├── __init__.py
│       │   └── contrato.py     ← Dataclasses del dominio
│       └── cli/
│           ├── __init__.py
│           └── main.py         ← CLI (argparse, punto de entrada)
├── tests/
│   ├── test_parser.py
│   ├── test_lexer.py
│   ├── test_validator.py
│   ├── fixtures/
│   │   ├── contrato_completo.py
│   │   ├── contrato_minimo.py
│   │   ├── sin_contrato.py
│   │   └── contrato_invalido.py
│   └── __init__.py
└── docs/
    ├── protocolo-v1.md         ← Spec para humanos
    └── schema/
        └── contrato-v1.json    ← Schema navegable
```

### 2.3 Decisiones técnicas

| Decisión | Opción elegida | Por qué |
|----------|----------------|---------|
| Parser de docstrings | YAML-like manual (no PyYAML) | PyYAML es permisivo con tipos; queremos control estricto. |
| AST parsing | `ast` de stdlib | Zero dependencias externas. Suficiente para funciones públicas. |
| Schema validation | `jsonschema` opcional | Sin dependencia obligatoria. Validación básica con asserts. |
| CLI framework | `argparse` de stdlib | Zero dependencias. Suficiente para MVP. |
| Dataclasses | `@dataclass(frozen=True)` | Inmutables, hashables, serializables. Mismo patrón que ioDesk. |
| Testing | `pytest` | Única dependencia dev. Suficiente. |

---

## 3. Entregables

### 3.1 Código

- [ ] `src/docpact/models/contrato.py` — Dataclasses `Contrato`, `CampoInput`,
      `SideEffect`, `ReglaNegocio`, `CasoBorde`, `Dependencia`
- [ ] `src/docpact/parser/extractor.py` — `extraer_docstrings(archivo: str) -> list[tuple[int, str, str]]`
      (línea, nombre_función, docstring_raw)
- [ ] `src/docpact/parser/lexer.py` — `tokenizar(docstring: str) -> list[Token]`
      (detecta bloque CONTRATO:, extrae secciones indentadas)
- [ ] `src/docpact/parser/parser.py` — `parsear(tokens: list[Token]) -> Contrato`
      (convierte tokens a estructura)
- [ ] `src/docpact/schema/validator.py` — `validar(contrato: dict) -> list[ErrorSchema]`
- [ ] `src/docpact/cli/main.py` — `docpact extract archivo.py` (extrae y muestra contratos)

### 3.2 Tests

- [ ] `tests/fixtures/contrato_completo.py` — Función con todos los campos
- [ ] `tests/fixtures/contrato_minimo.py` — Solo `side_effects: ninguno`
- [ ] `tests/fixtures/sin_contrato.py` — Función sin CONTRATO
- [ ] `tests/fixtures/contrato_invalido.py` — CONTRATO con campos mal formateados
- [ ] `tests/test_lexer.py` — Tokenización: bloque encontrado, bloque ausente, múltiples bloques
- [ ] `tests/test_parser.py` — Parseo: cada campo, errores, casos borde
- [ ] `tests/test_validator.py` — Validación: contrato válido, campo faltante, tipo incorrecto
- [ ] `tests/test_extractor.py` — Extracción: función pública, método de clase, función privada

### 3.3 Documentación

- [ ] `docs/protocolo-v1.md` — Especificación completa del formato CONTRATO para
      humanos y agentes. Debe incluir ejemplos en Python, TypeScript y JSON.
- [ ] `docs/schema/contrato-v1.json` — Schema navegable (copia del spec)

---

## 4. Criterios de éxito

1. `docpact extract tests/fixtures/contrato_completo.py` imprime el contrato
   como JSON válido con todos los campos parseados.
2. `docpact extract tests/fixtures/sin_contrato.py` imprime `[]` (sin contratos).
3. `docpact extract tests/fixtures/contrato_invalido.py` imprime el contrato
   con errores de validación.
4. `pytest tests/` pasa con cobertura > 90% en parser/.
5. El parser puede extraer los CONTRATOS reales de `soporte/services/tickets.py`
   de ioDesk-3 y produce estructuras válidas.

---

## 5. Notas técnicas para el agente implementador

### 5.1 El bloque CONTRATO es indentado, no tokenizado por palabras clave

El formato usa indentación (2 espacios) para delimitar secciones. No uses
regex para parsear — usa un lexer línea por línea con estado:

```
ESTADO_INICIAL → detecta "CONTRATO:" → ESTADO_CONTRATO
ESTADO_CONTRATO → detecta "  campo:" → ESTADO_CAMPO
ESTADO_CAMPO → acumula líneas indentadas hasta línea sin indentación
```

### 5.2 El bloque puede tener descripción narrativa antes

```python
def foo():
    """Esta es la descripción narrativa.
    Puede tener múltiples líneas.
    
    CONTRATO:
      side_effects: ninguno
    """
```

El extractor debe separar la descripción del CONTRATO. El CONTRATO empieza
en la línea que contiene "CONTRATO:" como texto completo (no "CONTRATO_DOS:").

### 5.3 Funciones públicas vs privadas

Por defecto, `docpact extract` solo extrae funciones públicas (no `_` prefixed)
y métodos de clases públicas. Flag `--include-private` para incluir todas.

### 5.4 Manejo de errores

Si el bloque CONTRATO está presente pero mal formado:
1. Extraer lo que se pueda (partial parsing)
2. Reportar errores específicos por campo
3. No fallar silenciosamente — el error es información valiosa para el agente

---

## 6. Check-list de implementación

```
☐ pyproject.toml con config básica (name, version, deps)
☐ src/docpact/__init__.py
☐ src/docpact/models/__init__.py
☐ src/docpact/models/contrato.py (dataclasses)
☐ src/docpact/parser/__init__.py
☐ src/docpact/parser/extractor.py
☐ src/docpact/parser/lexer.py
☐ src/docpact/parser/parser.py
☐ src/docpact/schema/__init__.py
☐ src/docpact/schema/validator.py
☐ src/docpact/schema/contrato-v1.json
☐ src/docpact/cli/__init__.py
☐ src/docpact/cli/main.py
☐ tests/__init__.py
☐ tests/fixtures/*.py (4 archivos)
☐ tests/test_lexer.py
☐ tests/test_parser.py
☐ tests/test_validator.py
☐ tests/test_extractor.py
☐ docs/protocolo-v1.md
☐ docs/schema/contrato-v1.json
☐ tests pasan con cobertura > 90%
☐ docpact extract soporte/services/tickets.py (ioDesk-3) funciona
```

# Fase 4 — Especificación Universal (Protocolo Agnóstico)

**Objetivo:** Separar el protocolo CONTRATO de la implementación Python.
El formato debe ser usable por proyectos TypeScript, Go, Rust, o cualquier
lenguaje. publicamos el schema JSON como fuente de verdad y ejemplos en
múltiples lenguajes.

**Principio Pareto:** El schema JSON es el 20% que permite el 80% de la
adopción cross-language. No necesitamos verificadores en cada lenguaje — 
necesitamos que **cualquier lenguaje pueda definir CONTRATOS** y que el
verificador Python pueda leerlos (o que cada lenguaje tenga su propio
verificador ligero).

**Duración estimada:** 2-3 días.
**Depende de:** Fase 1 (protocolo definido y validado).

---

## 1. JSON Schema como fuente de verdad

El schema `contrato-v1.json` (definido en Fase 1) se convierte en el
**documento normativo** del protocolo. Todo lo demás (parsers, validadores,
documentación) son implementaciones de referencia.

### 1.1 Publicación

```
docs/
└── schema/
    ├── contrato-v1.json       ← Schema normativo
    └── ejemplos/
        ├── python/            ← Ejemplos en Python
        ├── typescript/        ← Ejemplos en TypeScript
        ├── go/                ← Ejemplos en Go
        └── json/              ← Ejemplos de contratos serializados
```

### 1.2 Ejemplo TypeScript

```typescript
/**
 * Calcula el total de horas facturables para un contrato.
 *
 * CONTRATO:
 *   input:
 *     contratoId: number — ID del contrato
 *     mes: string — Mes en formato YYYY-MM
 *   output: number — Total de horas facturables
 *   side_effects: ninguno
 *   rn:
 *     - RN-002: solo sesiones completadas descuentan horas
 *   borde:
 *     - contratoId inválido: throws NotFoundError
 *     - mes sin sesiones: retorna 0
 *   dependencias:
 *     - src/services/sesiones.ts::getSesionesFacturables
 */
export function calcularHorasFacturables(
  contratoId: number,
  mes: string
): number {
  // RN-002: filtrar solo sesiones completadas
  const sesiones = getSesionesFacturables(contratoId, mes);
  return sesiones
    .filter((s) => s.completada)
    .reduce((total, s) => total + s.horas, 0);
}
```

### 1.3 Ejemplo Go

```go
// CONTRATO:
//   input:
//     ticketID: int64 — ID del ticket a resolver
//     userID: int64 — ID del usuario que resuelve
//   output: *Ticket — Ticket resuelto
//   side_effects: Actualiza estado del ticket, registra bitácora, envía notificación
//   rn:
//     - RN-010: solo administradores pueden resolver tickets
//   borde:
//     - ticket no encontrado: returns error
//     - usuario sin permisos: returns ErrForbidden
//   dependencias:
//     - internal/store/ticket.go::ResolveTicket
func (s *TicketService) ResolveTicket(ctx context.Context, ticketID, userID int64) (*Ticket, error) {
    // RN-010: verificar permisos
    user, err := s.store.GetUser(ctx, userID)
    if err != nil {
        return nil, fmt.Errorf("get user: %w", err)
    }
    if !user.IsAdmin {
        return nil, ErrForbidden
    }
    ticket, err := s.store.ResolveTicket(ctx, ticketID, userID)
    if err != nil {
        return nil, fmt.Errorf("resolve ticket: %w", err)
    }
    s.audit.Log(ctx, "ticket_resolved", ticketID, userID)
    s.notifier.Notify(ctx, ticket.ClientID, "Tu ticket ha sido resuelto")
    return ticket, nil
}
```

---

## 2. Verificador Python como implementación de referencia

El CLI de docpact (Fase 2) se documenta como "implementación de referencia".
El protocolo no depende de Python — el verificador Python es solo una
implementación.

### 2.1 Cómo otros lenguajes verifican

Cada lenguaje puede implementar su propio verificador, o usar el CLI de
docpact via subprocess (para CI/CD):

```yaml
# .github/workflows/docpact-typescript.yml
- name: Check contracts
  run: |
    pip install docpact
    docpact check src/ --config docpact.toml
```

---

## 3. docpact init — generación de contratos

Comando que analiza una función sin CONTRATO y genera el esqueleto basado
en su firma y cuerpo:

```bash
# Generar CONTRATO para una función específica
docpact init soporte/services/tickets.py --function crear_ticket

# Generar CONTRATOS para todas las funciones públicas sin contrato
docpact init soporte/services/ --batch

# Output: inserta el bloque CONTRATO en el docstring de cada función
```

### 3.1 Lógica de generación

Para `side_effects`, `docpact init` corre el AST walker (Fase 2) y propone
los side effects que detecta. El agente/humano confirma o corrige.

Para `output`, lee el type hint de retorno.
Para `input`, lee los type hints de los parámetros.
Para `rn`, deja comentario `# TODO: agregar RN-XXX`.
Para `dependencias`, busca imports en el módulo.

---

## 4. Criterios de éxito

1. Schema JSON publicado en `docs/schema/contrato-v1.json`
2. Ejemplo TypeScript con CONTRATO en `docs/schema/ejemplos/typescript/`
3. Ejemplo Go con CONTRATO en `docs/schema/ejemplos/go/`
4. `docpact init --batch` genera esqueletos correctos para ioDesk-3
5. Cualquier persona puede leer el schema y entender el protocolo sin
   saber Python

---

## 5. Check-list

```
☐ docs/schema/contrato-v1.json (normativo, versión final)
☐ docs/schema/ejemplos/typescript/ejemplo.ts
☐ docs/schema/ejemplos/go/ejemplo.go
☐ docs/schema/ejemplos/python/ejemplo.py (el de Fase 1)
☐ docs/schema/ejemplos/json/contrato-serializado.json
☐ src/docpact/cli/init.py (comando init)
☐ docs/protocolo-v1.md actualizado con ejemplos cross-language
☐ Verificar schema con ejemplos en 3 lenguajes
```

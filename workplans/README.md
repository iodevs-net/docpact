# Workplans — docpact

Este directorio contiene los planes de implementación de docpact.
Cada plan describe una fase con objetivos, entregables, criterios de éxito y
dependencias. Están escritos para que **un agente pueda ejecutarlos sin supervisión**.

## Índice

| Archivo | Fase | Estado |
|---------|------|--------|
| `F01-protocolo-y-parser.md` | Fase 1 — Protocolo CONTRATO + Parser Python | 🟢 En progreso |
| `F02-cli-y-verificacion-basica.md` | Fase 2 — CLI + side_effects + RN | ⏳ Pendiente |
| `F03-integracion-iodesk.md` | Fase 3 — Integración ioDesk-3 (pre-commit, CI) | ⏳ Pendiente |
| `F04-especificacion-agnostica.md` | Fase 4 — Spec universal + schema JSON | ⏳ Pendiente |

## Principios de diseño

1. **Pareto primero.** Cada fase entrega el 80% del valor con el 20% del esfuerzo.
   No hay fase que requiera semanas de trabajo sin resultados intermedios.
2. **Integración desde el día 1.** docpact verifica ioDesk-3 desde la Fase 2,
   no cuando esté "completo".
3. **Protocolo antes que herramienta.** Primero definimos QUÉ es un CONTRATO
   (especificación), luego CÓMO se verifica (implementación).
4. **Agnóstico por diseño.** El formato CONTRATO no asume Python. Los parsers
   pueden ser específicos de lenguaje, pero el protocolo es universal.
5. **Verificable por humanos y máquinas.** Todo CONTRATO debe poder validarse
   tanto por un humano leyendo el código como por un script en CI.

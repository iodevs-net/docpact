"""Parser de CONTRATOS en comentarios TypeScript/JSX.

Soporta dos formatos de comentario:
  // CONTRATO:
  //   input: ...
  //   output: ...

  /**
   * CONTRATO:
   *   input: ...
   *   output: ...
   */

Usa regex — no necesita AST porque TS se verifica con tsc.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# ─── expresión regular para campos simples ──────────────────

_RE_CAMPO_SIMPLE = re.compile(
    r"^\s{2,}(?P<campo>output|side_effects)\s*:\s*(?P<valor>.+?)\s*$"
)

_RE_INPUT_PARAM = re.compile(
    r"^\s{4,}(?P<param>\w[\w\d_]*)\s*:\s*(?P<tipo>[^\s]+(?:\s*—\s*.+)?)\s*$"
)

_RE_ITEM_LISTA = re.compile(
    r"^\s{4,}-\s+(?P<item>.+?)\s*$"
)

_RE_ITEM_BORDE = re.compile(
    r"^\s{4,}-\s+(?P<cond>.+?)\s*:\s*(?P<comp>.+?)\s*$"
)

_RE_CONTRATO_INICIO = re.compile(r"CONTRATO\s*:")


def extraer_contratos_ts(archivo: str) -> list[dict]:
    """Extrae bloques CONTRATO de comentarios TypeScript/JSX.

    Args:
        archivo: Ruta al archivo .ts, .tsx o .jsx.

    Returns:
        Lista de dicts con:
          - nombre_funcion: str
          - linea: int  (línea donde empieza el bloque CONTRATO)
          - input: dict[str, dict]  {"param": {"tipo": str, "descripcion": str}}
          - output: str | None
          - side_effects: list[str]
          - rn: list[dict]  [{"id": str, "descripcion": str}]
          - borde: list[dict]  [{"condicion": str, "comportamiento": str}]
          - dependencias: list[str]
    """
    path = Path(archivo)
    lineas = path.read_text(encoding="utf-8").splitlines(keepends=False)

    bloques = _encontrar_bloques(lineas)
    contratos: list[dict] = []

    for linea_inicio, bloque in bloques:
        contrato = _parsear_bloque(bloque)
        if contrato is None:
            continue
        nombre = _extraer_funcion(lineas, linea_inicio + len(bloque))
        contrato["nombre_funcion"] = nombre or "<desconocida>"
        contrato["linea"] = linea_inicio + 1  # 1-indexed
        contratos.append(contrato)

    return contratos


# ─── detección de bloques ───────────────────────────────────


def _encontrar_bloques(lineas: list[str]) -> list[tuple[int, list[str]]]:
    """Encuentra todos los bloques CONTRATO.

    Devuelve [(linea_0_index, [lineas_limpias_del_bloque]), …]
    Cada línea limpia tiene los marcadores de comentario ya removidos.
    """
    bloques: list[tuple[int, list[str]]] = []
    i = 0
    while i < len(lineas):
        linea = lineas[i]

        # ── single‑line (// CONTRATO:) ──
        if _es_inicio_single(linea):
            inicio = i
            raw: list[str] = []
            while i < len(lineas) and _es_linea_comentario(lineas[i]):
                raw.append(_limpiar_single(lineas[i]))
                i += 1
            bloques.append((inicio, raw))
            continue

        # ── multi‑line (/** … */) ──
        if _es_inicio_multi(linea):
            inicio = i
            raw = [linea]
            i += 1
            tiene_contrato = "CONTRATO" in linea
            while i < len(lineas) and "*/" not in lineas[i]:
                if "CONTRATO" in lineas[i]:
                    tiene_contrato = True
                raw.append(lineas[i])
                i += 1
            if i < len(lineas):  # línea con */
                raw.append(lineas[i])
                i += 1

            if tiene_contrato:
                limpias = [_limpiar_multi(l) for l in raw]
                bloques.append((inicio, limpias))
            continue

        i += 1

    return bloques


# ── helpers de detección de comentarios ──────────────────────


def _es_inicio_single(linea: str) -> bool:
    return bool(re.search(r"//\s*CONTRATO\s*:", linea))


def _es_linea_comentario(linea: str) -> bool:
    return bool(re.match(r"^\s*//", linea))


def _es_inicio_multi(linea: str) -> bool:
    return bool(re.match(r"^\s*/\*\*", linea))


def _limpiar_single(linea: str) -> str:
    """Remueve '//' y espacios iniciales, conservando indentación relativa."""
    return re.sub(r"^\s*//\s?", "", linea)


def _limpiar_multi(linea: str) -> str:
    """Remueve '/**', '*', '*/' y espacios alrededor."""
    l = re.sub(r"^\s*/\*\*?\s*", "", linea)
    l = re.sub(r"\s*\*/\s*$", "", l)
    l = re.sub(r"^\s*\*\s?", "", l)
    return l


# ─── parseo del contenido del bloque ────────────────────────


def _parsear_bloque(bloque: list[str]) -> Optional[dict]:
    """Parsea un bloque de líneas limpias y extrae los campos CONTRATO.

    Devuelve un dict con input, output, side_effects, rn, borde, dependencias,
    o None si el bloque no es un CONTRATO válido.
    """
    # Unir todo en una sola cadena y dividir en líneas significativas
    texto = "\n".join(bloque)

    if not _RE_CONTRATO_INICIO.search(texto):
        return None

    # Estado del parseo
    resultado: dict = {
        "input": {},
        "output": None,
        "side_effects": [],
        "rn": [],
        "borde": [],
        "dependencias": [],
    }
    campo_actual: Optional[str] = None
    en_subseccion: Optional[str] = None  # input, rn, borde, dependencias

    for raw_linea in bloque:
        linea = raw_linea.strip()

        if not linea or linea == "CONTRATO:":
            continue

        # ── campo simple (output / side_effects) ──
        m = _RE_CAMPO_SIMPLE.match(raw_linea)
        if m:
            campo = m.group("campo")
            valor = m.group("valor").strip()
            if campo == "output":
                resultado["output"] = valor
            elif campo == "side_effects":
                resultado["side_effects"] = (
                    [] if valor.strip().lower() == "ninguno"
                    else [s.strip() for s in valor.split(",") if s.strip()]
                )
            campo_actual = campo
            en_subseccion = None
            continue

        # ── subsección con sangría (input, rn, borde, dependencias) ──
        if re.match(r"^\s{2,}(input|rn|borde|dependencias)\s*:$", raw_linea):
            campo_actual = m.group(1) if (m := re.match(r"^\s{2,}(input|rn|borde|dependencias)\s*:$", raw_linea)) else None
            en_subseccion = m.group(1) if m else None
            continue

        # ── dentro de input: "param: type — desc" ──
        if en_subseccion == "input":
            m = _RE_INPUT_PARAM.match(raw_linea)
            if m:
                param = m.group("param")
                raw_tipo = m.group("tipo").strip()
                partes = raw_tipo.split("—", 1)
                tipo = partes[0].strip()
                desc = partes[1].strip() if len(partes) > 1 else ""
                resultado["input"][param] = {"tipo": tipo, "descripcion": desc}
                continue

        # ── dentro de rn, borde, dependencias ──
        if en_subseccion in ("rn", "borde", "dependencias"):
            # borde tiene formato "- condicion: comportamiento"
            if en_subseccion == "borde":
                m = _RE_ITEM_BORDE.match(raw_linea)
            else:
                m = _RE_ITEM_LISTA.match(raw_linea)

            if m:
                if en_subseccion == "rn":
                    item = m.group("item").strip()
                    partes_rn = item.split(":", 1)
                    rid = partes_rn[0].strip()
                    rdesc = partes_rn[1].strip() if len(partes_rn) > 1 else ""
                    resultado["rn"].append({"id": rid, "descripcion": rdesc})
                elif en_subseccion == "borde":
                    resultado["borde"].append({
                        "condicion": m.group("cond").strip(),
                        "comportamiento": m.group("comp").strip(),
                    })
                elif en_subseccion == "dependencias":
                    resultado["dependencias"].append(m.group("item").strip())

    return resultado


# ─── extracción del nombre de la función ────────────────────


def _extraer_funcion(lineas: list[str], desde: int) -> Optional[str]:
    """Busca la declaración de la función justo después del bloque CONTRATO.

    Escanea desde la línea `desde` (0‑indexed) hacia adelante saltando
    líneas en blanco y comentarios.

    Patrones detectados:
      - function nombre(… / export function nombre(…
      - export default function() {} / default function() {} → "default"
      - const X = () => {} / let X = …
      - class X { foo() { … } } → "foo"
      - class Nombre
      - export default () => {}
      - método en objeto/class literal: nombre(…
    """
    for i in range(desde, len(lineas)):
        linea = lineas[i].strip()

        if not linea or linea.startswith("//") or linea.startswith("/*") or linea.startswith("*"):
            continue

        # export default function() / default function() (anonymous)
        m = re.match(r"(?:export\s+)?default\s+(?:async\s+)?function\s*\(", linea)
        if m:
            return "default"

        # function nombre(…
        m = re.match(r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w[\w\d_$]*)", linea)
        if m:
            return m.group(1)

        # const nombre = (… / const nombre = function…
        m = re.match(r"(?:export\s+)?(?:const|let|var)\s+(\w[\w\d_$]*)\s*=", linea)
        if m:
            return m.group(1)

        # inline method inside class: class X { foo() { … }
        m = re.match(r"(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+\w[\w\d_$]*\s*\{\s*(\w[\w\d_$]*)\s*\(", linea)
        if m:
            return m.group(1)

        # class Nombre
        m = re.match(r"(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w[\w\d_$]*)", linea)
        if m:
            return m.group(1)

        # export default () => {} / export default async () => {}
        m = re.match(r"export\s+default\s+(?:async\s+)?\([^)]*\)\s*=>", linea)
        if m:
            return "default"

        # método en objeto/class literal: nombre(…
        m = re.match(r"(\w[\w\d_$]*)\s*\([^)]*\)\s*\{", linea)
        if m:
            return m.group(1)

        return None  # primera línea no comentario, sin firma de función

    return None

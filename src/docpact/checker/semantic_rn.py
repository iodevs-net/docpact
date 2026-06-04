"""Validadores semánticos de RN (reglas de negocio).

Reemplaza el viejo check de markers por verificación real: lee el código
y valida la regla directamente. El programador (o agente) declara
`rn: [RN-XXX]` en el CONTRATO; docpact ejecuta el validador asociado
y reporta error si la regla NO se cumple.

CONTRATO:
input:
  codigo_fuente: str — Cuerpo de la función a validar.
  rn_id: str — ID de la RN declarada (ej: "RN-005").
  spec: dict — Especificación del validador (leída de docpact.toml).
  contexto: dict — Contexto adicional (path archivo, línea inicio, AST, etc.)
output: list[ErrorParser] — Lista de errores (vacía = regla cumplida)
side_effects: ninguno

API pública:
  validar_rn(codigo_fuente, rn_id, spec, contexto) -> list[ErrorParser]
  Validadores disponibles:
    - state_transition: valida matrices de transición de estado
    - no_import: detecta imports prohibidos
    - required_groups: valida whitelist de grupos requeridos
    - tenant_safe: detecta usos inseguros de modelos sin tenant
    - has_pattern: validador genérico de patrón (compat con rn_patterns)
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Callable

from docpact.models.contrato import ErrorParser


# ─────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────


def validar_rn(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict | None = None,
) -> list[ErrorParser]:
    """Dispatcher principal: ejecuta el validador apropiado para la RN.

    Args:
        codigo_fuente: Código fuente de la función.
        rn_id: ID de la RN (ej: "RN-005"). Se incluye en el mensaje.
        spec: Dict con la especificación del validador. Debe contener
              la clave "type" (ej: "state_transition", "no_import").
              El resto de claves son específicas del validador.
        contexto: Dict con datos adicionales (archivo, línea, AST pre-parseado).

    Returns:
        Lista de ErrorParser. Vacía = RN cumplida.
    """
    contexto = contexto or {}
    tipo = spec.get("type")
    if not tipo:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: spec sin clave 'type' (validador indefinido)",
                sugerencia="Agrega 'type' al spec en docpact.toml [docpact.rn_patrones]",
            )
        ]

    validador = _VALIDADORES.get(tipo)
    if validador is None:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: validador '{tipo}' desconocido",
                sugerencia=f"Validadores disponibles: {sorted(_VALIDADORES.keys())}",
            )
        ]

    return validador(codigo_fuente, rn_id, spec, contexto)


def validadores_disponibles() -> list[str]:
    """Lista los nombres de validadores registrados (para diagnóstico)."""
    return sorted(_VALIDADORES.keys())


# ─────────────────────────────────────────────────────────────────────
# Validador 1: state_transition
# ─────────────────────────────────────────────────────────────────────


def _validar_state_transition(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict,
) -> list[ErrorParser]:
    """Valida que una matriz/dict de transiciones de estado contenga la transición esperada.

    Spec esperado:
        type = "state_transition"
        from_estado = "suspendido"      # estado origen
        to_cualquiera = ["atender", "asignado"]  # al menos uno debe estar permitido
        # Alternativa (transición específica):
        to_estado = "remoto"            # estado destino exacto (opcional)
        matriz_attr = "TRANSICIONES_PERMITIDAS"  # nombre de la variable/dict en el módulo
        modulo = "soporte/services/ticket_estados.py"  # path del módulo

    Estrategia:
    1. Lee el archivo del módulo.
    2. Parsea AST, busca una asignación a `matriz_attr` que sea dict.
    3. Verifica que `from_estado` exista en el dict y que sus valores
       contengan `to_estado` o algún elemento de `to_cualquiera`.
    """
    from_estado = spec.get("from_estado")
    to_estado = spec.get("to_estado")
    to_cualquiera = spec.get("to_cualquiera", [])
    matriz_attr = spec.get("matriz_attr", "TRANSICIONES_PERMITIDAS")
    modulo_path = spec.get("modulo")

    if not from_estado or (not to_estado and not to_cualquiera):
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: state_transition sin 'from_estado' o 'to_estado/to_cualquiera'",
                sugerencia="Verifica el spec en docpact.toml",
            )
        ]

    if not modulo_path:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: state_transition sin 'modulo' (path al archivo con la matriz)",
                sugerencia="Agrega 'modulo = \"ruta/al/archivo.py\"' al spec",
            )
        ]

    # Resolver path: si es relativo, respecto al proyecto_root en contexto
    modulo = Path(modulo_path)
    if not modulo.is_absolute():
        proyecto_root = contexto.get("proyecto_root")
        if proyecto_root:
            modulo = Path(proyecto_root) / modulo_path

    if not modulo.exists():
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: módulo '{modulo_path}' no encontrado",
                sugerencia=f"Verifica que el archivo existe: {modulo}",
            )
        ]

    try:
        fuente_modulo = modulo.read_text(encoding="utf-8")
        tree = ast.parse(fuente_modulo, filename=str(modulo))
    except (SyntaxError, UnicodeDecodeError) as e:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: no se pudo parsear {modulo_path}: {e}",
            )
        ]

    matriz = _extraer_dict_ast(tree, matriz_attr)
    if matriz is None:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: no se encontró dict '{matriz_attr}' en {modulo_path}",
                sugerencia=f"Verifica que '{matriz_attr}' está definido como dict literal",
            )
        ]

    # Normalizar keys a lowercase: en runtime `EstadoTicket.ATENDER == "atender"`,
    # pero a nivel AST solo tenemos el nombre del atributo ("ATENDER"). Comparamos
    # ambos lados en lowercase para que el spec (`from_estado = "atender"`)
    # coincida con la key real del dict.
    matriz_lower = {k.lower(): v for k, v in matriz.items()}
    from_estado_lower = from_estado.lower()

    transiciones = matriz_lower.get(from_estado_lower, [])
    if not transiciones:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: estado origen '{from_estado}' no existe en {matriz_attr}",
                sugerencia=f"Estados disponibles: {sorted(matriz.keys())}",
            )
        ]

    destinos_esperados = [to_estado] if to_estado else to_cualquiera
    destinos_lower = {d.lower() for d in transiciones}
    destinos_match = [d for d in destinos_esperados if d.lower() in destinos_lower]

    if not destinos_match:
        destinos_str = (
            ", ".join(transiciones)
            if isinstance(transiciones, list)
            else str(transiciones)
        )
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: transición '{from_estado}' → {destinos_esperados} no encontrada "
                f"en {matriz_attr}. Permitidos desde '{from_estado}': {destinos_str}",
                sugerencia=f"Agrega {destinos_esperados} a {matriz_attr}['{from_estado}']",
            )
        ]

    return []


def _extraer_dict_ast(tree: ast.AST, nombre: str) -> dict | None:
    """Extrae un dict literal asignado a `nombre` a nivel de módulo.

    Soporta tanto `=` (ast.Assign) como asignación anotada `: T = ...`
    (ast.AnnAssign), p.ej. `M: dict[str, list[str]] = {...}`.
    """
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == nombre:
                    if isinstance(node.value, ast.Dict):
                        return _dict_literal_a_python(node.value)
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == nombre
                and isinstance(node.value, ast.Dict)
            ):
                return _dict_literal_a_python(node.value)
    return None


def _dict_literal_a_python(node: ast.Dict) -> dict:
    """Convierte un ast.Dict con keys/values a dict Python.

    Soporta keys/values que sean string literal (`"x"`), Name (`Foo`) o
    Attribute (`Mod.X`). Para Attribute, devuelve el último segmento (`X`),
    que es el patrón típico de `Constante.ATENDER` donde la constante es
    un string que coincide con su nombre.

    Los valores que sean listas concatenadas con `+` (ast.BinOp(Add)) se
    aplanan recursivamente para resolver el patrón común `[...] + OTRA_LISTA`.
    """
    resultado: dict = {}
    for key, value in zip(node.keys, node.values):
        k = _extract_str_or_name(key)
        if k is None:
            continue
        resultado[k] = _flatten_list(value)
    return resultado


def _flatten_list(node: ast.AST) -> list[str]:
    """Extrae strings de una lista, incluyendo concatenaciones `lst1 + lst2 + ...`.

    Si el nodo no es representable como lista de strings, devuelve [].
    """
    elts = _flatten_binop(node)
    resultado: list[str] = []
    for e in elts:
        s = _extract_str_or_name(e)
        if s is not None:
            resultado.append(s)
    return resultado


def _flatten_binop(node: ast.AST) -> list[ast.AST]:
    """Aplana un `ast.BinOp(Add)` en una lista de nodos hoja.

    `a + b + c` se representa como `BinOp(BinOp(a, b), c)`. Esta función
    lo aplana a `[a, b, c]`. Cualquier nodo que no sea lista ni BinOp
    se devuelve como una lista de un solo elemento.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _flatten_binop(node.left) + _flatten_binop(node.right)
    if isinstance(node, ast.List):
        return list(node.elts)
    return [node]


def _extract_str_or_name(node: ast.AST) -> str | None:
    """Extrae string de Constant, Name.id, o último segmento de Attribute.

    Devuelve None si el nodo no es representable como string simple (ej:
    llamadas a función, expresiones complejas).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


# ─────────────────────────────────────────────────────────────────────
# Validador 2: no_import
# ─────────────────────────────────────────────────────────────────────


def _validar_no_import(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict,
) -> list[ErrorParser]:
    """Detecta imports prohibidos por patrón.

    Spec esperado:
        type = "no_import"
        patterns = ["facturacion_erp", "*sii*", "stripe"]   # globs
        en_archivo = "soporte/services/facturacion.py"        # opcional, limita el check

    Si `en_archivo` está definido y la función NO está en ese archivo, pasa.
    Si no está definido, se chequea en el cuerpo de la función.
    """
    patterns = spec.get("patterns", [])
    en_archivo = spec.get("en_archivo")

    if not patterns:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: no_import sin 'patterns'",
            )
        ]

    # Si hay restricción de archivo, validar que la función esté en ese archivo
    if en_archivo:
        archivo_actual = contexto.get("archivo", "")
        if en_archivo not in archivo_actual:
            return []  # La función no es responsable de esta regla

    # Compilar patterns a regex (soporta * wildcard)
    regexes = [re.compile(p.replace(".", r"\.").replace("*", ".*")) for p in patterns]

    # Buscar imports
    try:
        tree = ast.parse(codigo_fuente)
    except SyntaxError:
        return []

    errores: list[ErrorParser] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _match_any(regexes, alias.name):
                    errores.append(
                        ErrorParser(
                            "rn_semantica",
                            f"RN {rn_id}: import prohibido '{alias.name}'",
                            linea=node.lineno,
                            sugerencia=f"Patrones prohibidos: {patterns}",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            modulo = node.module or ""
            if _match_any(regexes, modulo):
                errores.append(
                    ErrorParser(
                        "rn_semantica",
                        f"RN {rn_id}: import prohibido 'from {modulo} import ...'",
                        linea=node.lineno,
                        sugerencia=f"Patrones prohibidos: {patterns}",
                    )
                )

    return errores


def _match_any(regexes: list[re.Pattern], texto: str) -> bool:
    return any(r.search(texto) for r in regexes)


# ─────────────────────────────────────────────────────────────────────
# Validador 3: required_groups
# ─────────────────────────────────────────────────────────────────────


def _validar_required_groups(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict,
) -> list[ErrorParser]:
    """Valida que la función solo aplique si el usuario pertenece a grupos autorizados.

    Spec esperado:
        type = "required_groups"
        allowed = ["administracion", "supervision"]   # whitelist
        # o, en negativo:
        forbidden = ["cliente"]                        # blacklist

    Estrategia: busca checks tipo `groups.filter(name=...)` o
    `is_superuser` en el código. Si la función no chequea NADA, falla
    (asumimos que falta la validación).
    """
    allowed = spec.get("allowed", [])
    forbidden = spec.get("forbidden", [])

    if not allowed and not forbidden:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: required_groups sin 'allowed' o 'forbidden'",
            )
        ]

    if not _has_group_check(codigo_fuente):
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: no se detectó validación de grupo en la función",
                sugerencia=(
                    "Agrega `usuario.groups.filter(name=...)` o "
                    "`getattr(usuario, 'is_superuser', False)` al inicio"
                ),
            )
        ]

    return []


_GROUP_CHECK_PATTERNS = re.compile(
    r"groups\.filter|is_superuser|has_perm|grupo|group", re.IGNORECASE
)


def _has_group_check(codigo_fuente: str) -> bool:
    return bool(_GROUP_CHECK_PATTERNS.search(codigo_fuente))


# ─────────────────────────────────────────────────────────────────────
# Validador 4: tenant_safe
# ─────────────────────────────────────────────────────────────────────


def _validar_tenant_safe(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict,
) -> list[ErrorParser]:
    """Detecta usos inseguros de modelos multi-tenant.

    Spec esperado:
        type = "tenant_safe"
        forbid = ["unfiltered_objects", ".objects.all()", ".objects.filter()"]
            # substrings prohibidos (default: ["unfiltered_objects"])

    Estrategia: busca usos directos de managers sin `para_usuario()` o
    escapes inseguros. Es heurístico — el agente debe declarar
    explícitamente cuándo un escape es legítimo.
    """
    forbid = spec.get("forbid", ["unfiltered_objects", ".objects.all", ".objects.filter"])
    errores: list[ErrorParser] = []

    try:
        tree = ast.parse(codigo_fuente)
    except SyntaxError:
        return []

    # Deduplicar por (linea, token) — ast.walk recorre padres e hijos,
    # y muchos nodos contienen la misma substring prohibida.
    vistos: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            continue
        # Match por nombre de atributo (ej: unfiltered_objects)
        if isinstance(node, ast.Attribute) and node.attr in forbid:
            key = (node.lineno, node.attr)
            if key in vistos:
                continue
            vistos.add(key)
            errores.append(
                ErrorParser(
                    "rn_semantica",
                    f"RN {rn_id}: uso de '{node.attr}' detectado (posible escape multi-tenant)",
                    linea=node.lineno,
                    sugerencia="Si es legítimo, agrega comentario '# docpact: tenant-escape'",
                )
            )
            continue
        # Match por substring del código unparseado (ej: ".raw(")
        try:
            rendered = ast.unparse(node)
        except Exception:
            continue
        for token in forbid:
            if token in rendered and not isinstance(node, ast.Attribute):
                lineno = getattr(node, "lineno", 0)
                key = (lineno, token)
                if key in vistos:
                    continue
                vistos.add(key)
                errores.append(
                    ErrorParser(
                        "rn_semantica",
                        f"RN {rn_id}: uso de '{token}' detectado (escape multi-tenant)",
                        linea=lineno,
                        sugerencia="Si es legítimo, agrega comentario '# docpact: tenant-escape'",
                    )
                )
                break

    return errores


# ─────────────────────────────────────────────────────────────────────
# Validador 5: has_pattern (compat con rn_patterns viejo)
# ─────────────────────────────────────────────────────────────────────


def _validar_has_pattern(
    codigo_fuente: str,
    rn_id: str,
    spec: dict,
    contexto: dict,
) -> list[ErrorParser]:
    """Validador genérico: el código de la función contiene un patrón dado.

    Spec esperado:
        type = "has_pattern"
        patron = "INTERVALO_RE_RECORDATORIO"  # string a buscar (soporta | para OR)
        line_offset = 0  # opcional, offset para mensajes

    Este validador es el sucesor directo de `verificar_rn_patrones` y
    mantiene retrocompatibilidad con configs `docpact.toml` existentes.
    """
    patron = spec.get("patron", "")
    if not patron:
        return [
            ErrorParser(
                "rn_semantica",
                f"RN {rn_id}: has_pattern sin 'patron'",
            )
        ]

    lineas = codigo_fuente.split("\n")
    line_offset = spec.get("line_offset", 0)

    for i, linea in enumerate(lineas, 1):
        for p in patron.split("|"):
            if p.strip() and p.strip() in linea:
                return []  # Encontrado — regla cumplida

    return [
        ErrorParser(
            "rn_semantica",
            f"RN {rn_id}: patrón '{patron}' no encontrado en el cuerpo de la función",
            linea=line_offset,
            sugerencia=f"Agrega una línea que contenga '{patron}'",
        )
    ]


# ─────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────


_VALIDADORES: dict[str, Callable] = {
    "state_transition": _validar_state_transition,
    "no_import": _validar_no_import,
    "required_groups": _validar_required_groups,
    "tenant_safe": _validar_tenant_safe,
    "has_pattern": _validar_has_pattern,
}

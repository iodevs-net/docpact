"""Procesamiento individual de funciones — lógica de verificación de CONTRATO."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from docpact.checker._checks import to_hallazgo
from docpact.checker.models import (
    Hallazgo,
    ResultadoArchivo,
    ResultadoFuncion,
    _suprimir_hallazgos,
)
from docpact.checker.side_effects import check_side_effects
from docpact.checker.rn_checker import (
    extraer_comentarios_desde_fuente,
    _extraer_ids_rn,
)
from docpact.checker.marker_honesty import (
    check_marker_honesty,
    check_marcador_concentrado,
)
from docpact.checker.deps_checker import check_deps
from docpact.checker.import_checker import check_inline_imports
from docpact.checker.signature_checker import (
    check_signature,
    introspectar_firma,
    find_project_root,
)

try:
    from docpact.checker.rn_registry_checker import check_rn_against_registry  # type: ignore[import-untyped]
except ImportError:
    check_rn_against_registry = None
from docpact.checker.rn_test_checker import check_rn_tests, check_rn_tests_pasan
from docpact.config import DocpactConfig
from docpact.models.contrato import (
    Contrato,
    ErrorParser,
)
from docpact.parser.lexer import tokenizar
from docpact.parser.parser import parsear
from docpact.checker.contract_index import ContractIndex
from docpact.checker.transitive_effects import check_transitive_effects


def procesar_funcion(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    archivo: str,
    fuente: str,
    config: DocpactConfig,
    doc_map: dict[str, tuple[int, str, str]],
    resultado: ResultadoArchivo,
    tiene_future_annotations: bool = False,
    index: Optional[ContractIndex] = None,
    imports: Optional[dict[str, str]] = None,
    modulo_actual: str = "",
    clase_actual: Optional[str] = None,
) -> None:
    """Procesa una función: extrae CONTRATO y ejecuta checkers."""
    nombre = node.name

    # Ignorar privadas
    if nombre.startswith("_"):
        return

    # Obtener docstring
    info = doc_map.get(f"{nombre}:{node.lineno}")
    tiene_doc = info is not None

    if not tiene_doc:
        # Función sin docstring ni CONTRATO
        res = ResultadoFuncion(
            nombre=nombre,
            archivo=archivo,
            linea=node.lineno,
            tiene_contrato=False,
        )
        if config.strict:
            res.hallazgos.append(
                Hallazgo(
                    tipo="error",
                    campo="presencia",
                    funcion=nombre,
                    archivo=archivo,
                    linea=node.lineno,
                    mensaje=f"Función pública '{nombre}' sin CONTRATO",
                    sugerencia="Agrega un bloque CONTRATO al docstring",
                )
            )
        resultado.funciones.append(res)
        return

    if info is None:
        return

    _, _, doc = info

    # Parsear CONTRATO del docstring
    tokens = tokenizar(doc)
    contrato, parse_errors = parsear(tokens)

    # Introspectar firma si no se declararon inputs o output en el docstring (Zero-Friction)
    if "CONTRATO:" in doc and (not contrato.input or not contrato.output):
        inputs_intro, output_intro = introspectar_firma(node)
        contrato = Contrato(
            input=contrato.input if contrato.input else inputs_intro,
            output=contrato.output if contrato.output else output_intro,
            output_descripcion=contrato.output_descripcion,
            side_effects=contrato.side_effects,
            rn=contrato.rn,
            borde=contrato.borde,
            dependencias=contrato.dependencias,
        )

    hay_contrato = bool(
        contrato.side_effects or contrato.rn or contrato.input or contrato.output
    )
    # CONTRATO minimal (solo side_effects: ninguno + rn: []) también cuenta
    if not hay_contrato and "CONTRATO:" in doc:
        hay_contrato = True

    if not hay_contrato and config.strict:
        res = ResultadoFuncion(
            nombre=nombre,
            archivo=archivo,
            linea=node.lineno,
            tiene_contrato=False,
            hallazgos=[
                Hallazgo(
                    tipo="error",
                    campo="presencia",
                    funcion=nombre,
                    archivo=archivo,
                    linea=node.lineno,
                    mensaje=f"Función pública '{nombre}' sin CONTRATO",
                    sugerencia="Agrega un bloque CONTRATO al docstring",
                )
            ],
        )
        resultado.funciones.append(res)
        return
    elif not hay_contrato:
        # No strict y no hay CONTRATO — lo registramos pero sin error
        resultado.funciones.append(
            ResultadoFuncion(
                nombre=nombre,
                archivo=archivo,
                linea=node.lineno,
                tiene_contrato=False,
            )
        )
        return

    # Hay CONTRATO — ejecutar verificadores
    hallazgos: list[Hallazgo] = []

    # Parse errors first
    for pe in parse_errors:
        hallazgos.append(to_hallazgo(pe, nombre, archivo, node.lineno, tipo="warning"))

    # Side effects
    se_errores = check_side_effects(node, contrato, config, nombre, archivo)
    for se in se_errores:
        tipo = "error" if "pero se detectaron" in se.mensaje else "warning"
        hallazgos.append(to_hallazgo(se, nombre, archivo, node.lineno, tipo=tipo))

    # Side effects transitivos
    if index is not None and imports is not None:
        trans_errores = check_transitive_effects(
            node,
            contrato,
            imports,
            index,
            nombre,
            archivo,
            modulo_actual,
            clase_actual,
        )
        for te in trans_errores:
            # La falsificación de contratos es un error crítico
            hallazgos.append(to_hallazgo(te, nombre, archivo, node.lineno, tipo="error"))

    # RN check — usa la fuente original para extraer comentarios
    # T02 Fase A: marker check se mantiene activo, pero como warning [LEGACY].
    # En la Fase C (próximo release) será eliminado. Los agentes deben migrar
    # a validadores semánticos configurando [docpact.rn_patrones] en docpact.toml.
    rn_errores = _check_rn_con_fuente(node, contrato, fuente, config.rn_prefix, nombre)
    for rn in rn_errores:
        hallazgos.append(
            Hallazgo(
                tipo="warning",
                campo=rn.campo,
                funcion=nombre,
                archivo=archivo,
                linea=rn.linea or node.lineno,
                mensaje=f"[LEGACY] {rn.mensaje}",
                sugerencia=(
                    f"{rn.sugerencia} | T02: configura un validador semántico en "
                    f"docpact.toml [docpact.rn_patrones] con 'type' para validar "
                    f"la regla de verdad."
                ),
            )
        )

    # Dependencias
    deps_errores = check_deps(contrato, archivo, nombre)
    for dep in deps_errores:
        hallazgos.append(to_hallazgo(dep, nombre, archivo, node.lineno))

    # Imports inline que duplican dependencias del CONTRATO
    lineas_f = fuente.splitlines()
    linea_fin_f = getattr(node, "end_lineno", len(lineas_f))
    codigo_funcion = "\n".join(lineas_f[node.lineno - 1 : linea_fin_f])
    imp_errores = check_inline_imports(
        codigo_funcion,
        [d.ref for d in contrato.dependencias],
        nombre,
        archivo,
        node.lineno,
    )
    for imp in imp_errores:
        hallazgos.append(to_hallazgo(imp, nombre, archivo, node.lineno, tipo="warning"))

    # T02 Fase A: dispatch a validadores semánticos. Cada RN declarada en
    # CONTRATO se valida ejecutando el validador configurado en
    # [docpact.rn_patrones] de docpact.toml. Los errores semánticos son
    # errores REALES (no markers), porque el código se lee y la regla
    # se valida estructuralmente.
    #
    # Si NO hay rn_patrones configurados pero el CONTRATO declara RNs,
    # emitimos info para guiar al agente a configurar validadores.
    #
    # Backward compat: si un spec NO tiene clave 'type', se asume
    # has_pattern (compat con el viejo verificar_rn_patrones).
    _validar_rn_semantica(
        archivo, contrato, config, codigo_funcion, nombre, node, hallazgos
    )

    # Verificar firma: input/output del CONTRATO vs firma real de Python
    check_signature(node, contrato, nombre, archivo, hallazgos,
                    tiene_future_annotations=tiene_future_annotations)

    # RN registry check
    _check_rn_registry(archivo, contrato, nombre, node, hallazgos)

    # RN test checker: cada RN-XXX debe tener tests/rn/test_rn_XXX.py
    _check_rn_tests(contrato, config, archivo, nombre, node, hallazgos)

    hallazgos = _suprimir_hallazgos(hallazgos, config)

    resultado.funciones.append(
        ResultadoFuncion(
            nombre=nombre,
            archivo=archivo,
            linea=node.lineno,
            tiene_contrato=True,
            contrato=contrato,
            hallazgos=hallazgos,
            codigo_funcion=codigo_funcion,
        )
    )


# ---------------------------------------------------------------------------
# Helpers extraídos para claridad
# ---------------------------------------------------------------------------


def _validar_rn_semantica(
    archivo: str,
    contrato: Contrato,
    config: DocpactConfig,
    codigo_funcion: str,
    nombre: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    hallazgos: list[Hallazgo],
) -> None:
    """Dispatch a validadores semánticos de RNs."""
    if archivo and contrato.rn and not config.rn_patrones:
        # Sin validadores configurados: avisar al agente
        for rn in contrato.rn:
            hallazgos.append(
                Hallazgo(
                    tipo="info",
                    campo="rn",
                    funcion=nombre,
                    archivo=archivo,
                    linea=node.lineno,
                    mensaje=(
                        f"RN {rn.id} declarada pero sin validador semántico "
                        f"configurado en docpact.toml"
                    ),
                    sugerencia=(
                        f"Agrega [docpact.rn_patrones] '{rn.id}' = "
                        f"{{ type = '...', ... }} en docpact.toml. "
                        f"Tipos: state_transition, no_import, required_groups, "
                        f"tenant_safe, has_pattern."
                    ),
                )
            )
    elif config.rn_patrones and archivo and contrato.rn:
        from docpact.checker.semantic import validar_rn
        from docpact.checker.rn_patterns import verificar_rn_patrones

        # Resolver proyecto_root una sola vez para validadores que lo necesitan
        proyecto_root = find_project_root(archivo)
        contexto_base = {
            "archivo": archivo,
            "proyecto_root": str(proyecto_root) if proyecto_root else None,
        }

        for rn in contrato.rn:
            spec = config.rn_patrones.get(rn.id)
            if not spec:
                # RN declarada en CONTRATO pero sin validador configurado.
                # Emitir info para que el agente sepa que debe configurar uno.
                hallazgos.append(
                    Hallazgo(
                        tipo="info",
                        campo="rn",
                        funcion=nombre,
                        archivo=archivo,
                        linea=node.lineno,
                        mensaje=(
                            f"RN {rn.id} declarada pero sin validador "
                            f"semántico configurado en docpact.toml"
                        ),
                        sugerencia=(
                            f"Agrega [docpact.rn_patrones] '{rn.id}' = "
                            f"{{ type = '...', ... }} en docpact.toml. "
                            f"Tipos: state_transition, no_import, required_groups, "
                            f"tenant_safe, has_pattern."
                        ),
                    )
                )
                continue

            # Si el spec no tiene 'type', fallback al comportamiento legacy (has_pattern)
            if "type" not in spec:
                _errores_legacy = verificar_rn_patrones(
                    Path(archivo),
                    codigo_funcion,
                    {rn.id: spec},
                    line_offset=node.lineno,
                )
                for ep in _errores_legacy:
                    hallazgos.append(
                        Hallazgo(
                            tipo="warning",
                            campo="rn",
                            funcion=nombre,
                            archivo=archivo,
                            linea=ep.linea,
                            mensaje=f"[LEGACY has_pattern] {ep.mensaje}",
                            sugerencia=(
                                f"{ep.sugerencia} | T02: agrega 'type' al spec "
                                f"para migrar a validación semántica."
                            ),
                        )
                    )
                continue

            # Dispatcher semántico
            contexto = {**contexto_base, "line_offset": node.lineno}
            errores_sem = validar_rn(codigo_funcion, rn.id, spec, contexto)
            for es in errores_sem:
                # T02 Fase A: errores semánticos son errores reales
                hallazgos.append(to_hallazgo(es, nombre, archivo, node.lineno, tipo="error"))


def _check_rn_registry(
    archivo: str,
    contrato: Contrato,
    nombre: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    hallazgos: list[Hallazgo],
) -> None:
    """Verifica RNs contra el registro global."""
    if check_rn_against_registry is None or not archivo:
        return
    if not contrato.rn:
        return

    proyecto_root = find_project_root(archivo)
    if proyecto_root is None:
        return

    rn_reg_errors, rn_reg_infos = check_rn_against_registry(
        proyecto_root, contrato.rn
    )
    for e in rn_reg_errors:
        hallazgos.append(to_hallazgo(e, nombre, archivo, node.lineno))
    for i in rn_reg_infos:
        hallazgos.append(to_hallazgo(i, nombre, archivo, node.lineno, tipo="info"))


def _check_rn_tests(
    contrato: Contrato,
    config: DocpactConfig,
    archivo: str,
    nombre: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    hallazgos: list[Hallazgo],
) -> None:
    """Verifica que cada RN-XXX tenga tests/rn/test_rn_XXX.py y que pasen."""
    rn_ids = [r.id for r in contrato.rn]
    if not rn_ids or not archivo:
        return

    proyecto_root = find_project_root(archivo)
    if proyecto_root is None:
        return

    rn_test_errors = check_rn_tests(rn_ids, proyecto_root, nombre)
    for e in rn_test_errors:
        hallazgos.append(to_hallazgo(e, nombre, archivo, node.lineno))

    # Verificar que los tests existentes PASEN
    if config.run_tests:
        rn_test_fallos = check_rn_tests_pasan(rn_ids, proyecto_root, nombre)
        for e in rn_test_fallos:
            hallazgos.append(to_hallazgo(e, nombre, archivo, node.lineno))


def _check_rn_con_fuente(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    contrato: Contrato,
    fuente: str,
    prefix: str,
    nombre: str,
    config: Optional[DocpactConfig] = None,
) -> list[ErrorParser]:
    """Verifica RNs usando la fuente original para extraer comentarios."""
    if not contrato.rn:
        return []

    # Extraer comentarios de la fuente
    linea_inicio = node.lineno
    linea_fin = getattr(node, "end_lineno", node.lineno + 50) or (node.lineno + 50)
    comentarios = extraer_comentarios_desde_fuente(fuente, linea_inicio, linea_fin)
    ids_en_codigo = set(_extraer_ids_rn(comentarios, prefix))

    errores: list[ErrorParser] = []
    for rn in contrato.rn:
        if rn.id not in ids_en_codigo:
            errores.append(
                ErrorParser(
                    "rn",
                    f"'{nombre}': RN '{rn.id}' declarada pero no encontrada "
                    f"como comentario en el código",
                    sugerencia=f"Agrega '# {rn.id}' en el lugar donde se implementa",
                )
            )

    # Marker honesty: detectar # RN-XXX en líneas de delegación
    rn_ids = [rn.id for rn in contrato.rn]
    honesty_enabled = getattr(config, "marker_honesty_enabled", True)
    honesty_max = getattr(config, "marker_honesty_max_rns", 5)
    honesty_errors = check_marker_honesty(
        node, rn_ids, fuente, nombre, prefix, enabled=honesty_enabled
    )
    errores.extend(honesty_errors)

    # Concentración sospechosa: >umbral RNs en una función
    concentrado = check_marcador_concentrado(
        rn_ids, nombre, umbral=honesty_max, enabled=honesty_enabled
    )
    if concentrado is not None:
        errores.append(concentrado)

    return errores

"""Orquestador — coordina la verificación completa de un archivo o proyecto.

Flujo por archivo:
1. Parsear el archivo con AST
2. Por cada función pública:
   a. Extraer docstring + CONTRATO
   b. Verificar side_effects (AST walker)
   c. Verificar RN (comentarios en cuerpo)
   d. Verificar dependencias (archivos/símbolos existentes)
3. Acumular resultados y calcular score
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional
from docpact.checker.models import (
    Hallazgo,
    ResultadoArchivo,
    ResultadoFuncion,
    ResultadoProyecto,
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
from docpact.checker.ts_checker import check_file_ts
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
from docpact.parser.extractor import extraer_docstrings
from docpact.parser.lexer import tokenizar
from docpact.parser.parser import parsear
from docpact.checker.contract_index import ContractIndex, ImportResolver
from docpact.checker.transitive_effects import check_transitive_effects


def check_file(
    archivo: str | Path,
    config: DocpactConfig,
    index: Optional[ContractIndex] = None,
) -> ResultadoArchivo:
    """Verifica un archivo Python, TypeScript o JSX.

    Args:
        archivo: Ruta al archivo.
        config: Configuración de docpact.
        index: Índice global de contratos.

    Returns:
        ResultadoArchivo con todas las funciones y sus hallazgos.
    """
    path = Path(archivo)
    proyecto_root = find_project_root(str(path))
    if proyecto_root is not None:
        try:
            rel_path = path.resolve().relative_to(proyecto_root.resolve())
            if config.debe_excluir(rel_path):
                return ResultadoArchivo(archivo=str(path))
        except ValueError:
            if config.debe_excluir(path):
                return ResultadoArchivo(archivo=str(path))
    else:
        if config.debe_excluir(path):
            return ResultadoArchivo(archivo=str(path))

    if path.suffix in (".ts", ".tsx", ".jsx"):
        return check_file_ts(path, config)

    # ── Python ──
    try:
        with open(path, "r", encoding="utf-8") as f:
            fuente = f.read()
        tree = ast.parse(fuente, filename=str(path))
    except (SyntaxError, FileNotFoundError, UnicodeDecodeError):
        return ResultadoArchivo(archivo=str(path))

    resultado = ResultadoArchivo(archivo=str(path))

    doc_funciones = extraer_docstrings(path)

    doc_map: dict[str, tuple[int, str, str]] = {}
    for linea, nombre, tipo, doc in doc_funciones:
        # Usar (nombre, linea) para evitar colisiones con métodos sobrecargados
        doc_map[f"{nombre}:{linea}"] = (linea, tipo, doc)

    tiene_future_annotations = "from __future__ import annotations" in fuente

    # Resolver imports si hay un índice global de contratos disponible
    imports: dict[str, str] = {}
    modulo_actual = path.stem
    if index is not None:
        try:
            resolver = ImportResolver(path, index.project_root)
            resolver.visit(tree)
            imports = resolver.imports
            modulo_actual = resolver.modulo_actual
        except Exception:
            pass

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _procesar_funcion(
                        item, str(path), fuente, config, doc_map, resultado,
                        tiene_future_annotations=tiene_future_annotations,
                        index=index,
                        imports=imports,
                        modulo_actual=modulo_actual,
                        clase_actual=node.name,
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _procesar_funcion(
                node, str(path), fuente, config, doc_map, resultado,
                tiene_future_annotations=tiene_future_annotations,
                index=index,
                imports=imports,
                modulo_actual=modulo_actual,
            )

    return resultado



def _procesar_funcion(
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
        hallazgos.append(
            Hallazgo(
                tipo="warning",
                campo=pe.campo,
                funcion=nombre,
                archivo=archivo,
                linea=pe.linea or node.lineno,
                mensaje=pe.mensaje,
                sugerencia=pe.sugerencia,
            )
        )

    # Side effects
    se_errores = check_side_effects(node, contrato, config, nombre, archivo)
    for se in se_errores:
        hallazgos.append(
            Hallazgo(
                tipo="error" if "pero se detectaron" in se.mensaje else "warning",
                campo=se.campo,
                funcion=nombre,
                archivo=archivo,
                linea=se.linea or node.lineno,
                mensaje=se.mensaje,
                sugerencia=se.sugerencia,
            )
        )

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
            hallazgos.append(
                Hallazgo(
                    tipo="error",  # La falsificación de contratos es un error crítico
                    campo=te.campo,
                    funcion=nombre,
                    archivo=archivo,
                    linea=te.linea or node.lineno,
                    mensaje=te.mensaje,
                    sugerencia=te.sugerencia,
                )
            )

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
        hallazgos.append(
            Hallazgo(
                tipo="error",
                campo=dep.campo,
                funcion=nombre,
                archivo=archivo,
                linea=dep.linea or node.lineno,
                mensaje=dep.mensaje,
                sugerencia=dep.sugerencia,
            )
        )

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
        hallazgos.append(
            Hallazgo(
                tipo="warning",
                campo=imp.campo,
                funcion=nombre,
                archivo=archivo,
                linea=imp.linea or node.lineno,
                mensaje=imp.mensaje,
                sugerencia=imp.sugerencia,
            )
        )

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
        from docpact.checker.semantic_rn import validar_rn
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
                hallazgos.append(
                    Hallazgo(
                        tipo="error",  # T02 Fase A: errores semánticos son errores reales
                        campo="rn_semantica",
                        funcion=nombre,
                        archivo=archivo,
                        linea=es.linea or node.lineno,
                        mensaje=es.mensaje,
                        sugerencia=es.sugerencia,
                    )
                )

    # RN registry check
    from pathlib import Path as _Path
    from typing import Optional as _Optional

    # Verificar firma: input/output del CONTRATO vs firma real de Python
    check_signature(node, contrato, nombre, archivo, hallazgos,
                     tiene_future_annotations=tiene_future_annotations)

    if check_rn_against_registry is not None:
        proyecto_root = find_project_root(archivo)
        if proyecto_root is not None:
            rn_reg_errors, rn_reg_infos = check_rn_against_registry(
                proyecto_root, contrato.rn
            )
            for e in rn_reg_errors:
                hallazgos.append(
                    Hallazgo(
                        tipo="error",
                        campo=e.campo,
                        funcion=nombre,
                        archivo=archivo,
                        linea=e.linea or node.lineno,
                        mensaje=e.mensaje,
                        sugerencia=e.sugerencia,
                    )
                )
            for i in rn_reg_infos:
                hallazgos.append(
                    Hallazgo(
                        tipo="info",
                        campo=i.campo,
                        funcion=nombre,
                        archivo=archivo,
                        linea=i.linea or node.lineno,
                        mensaje=i.mensaje,
                        sugerencia=i.sugerencia,
                    )
                )

    # RN test checker: cada RN-XXX debe tener tests/rn/test_rn_XXX.py
    rn_ids = [r.id for r in contrato.rn]
    if rn_ids:
        proyecto_root = find_project_root(archivo)
        if proyecto_root is not None:
            rn_test_errors = check_rn_tests(rn_ids, proyecto_root, nombre)
            for e in rn_test_errors:
                hallazgos.append(
                    Hallazgo(
                        tipo="error",
                        campo=e.campo,
                        funcion=nombre,
                        archivo=archivo,
                        linea=node.lineno,
                        mensaje=e.mensaje,
                        sugerencia=e.sugerencia,
                    )
                )
            # Verificar que los tests existentes PASEN
            if config.run_tests:
                rn_test_fallos = check_rn_tests_pasan(rn_ids, proyecto_root, nombre)
                for e in rn_test_fallos:
                    hallazgos.append(
                        Hallazgo(
                            tipo="error",
                            campo=e.campo,
                            funcion=nombre,
                            archivo=archivo,
                            linea=node.lineno,
                            mensaje=e.mensaje,
                            sugerencia=e.sugerencia,
                        )
                    )

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


def _get_changed_files(ruta_base: Path) -> list[Path]:
    """Obtiene archivos modificados via git diff.

    Orden: staged first (pre-commit), luego unstaged (local dev).
    Retorna vacía si no hay cambios o no es repo git.

    Returns:
        Lista de Paths absolutos de archivos modificados.
    """
    import subprocess

    try:
        # Staged changes (pre-commit hook context)
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=ruta_base,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [ruta_base / p for p in result.stdout.strip().splitlines()]
        # Unstaged changes (local dev context)
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=ruta_base,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [ruta_base / p for p in result.stdout.strip().splitlines()]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return []


def _escanear_eficiente(ruta: Path, config: DocpactConfig, extensiones: tuple[str, ...]) -> list[Path]:
    import os
    archivos = []
    
    ruta_res = ruta.resolve()
    # Comprobar la carpeta raíz de forma relativa
    if config.debe_excluir(Path(ruta_res.name)):
        return archivos

    ruta_str = str(ruta_res)
    for root, dirs, files in os.walk(ruta_str):
        root_path = Path(root).resolve()
        try:
            rel_root = root_path.relative_to(ruta_res)
        except ValueError:
            rel_root = Path("")

        # Modificar dirs in-place usando rutas relativas
        dirs_to_keep = []
        for d in dirs:
            rel_dir_path = rel_root / d
            if not config.debe_excluir(rel_dir_path):
                dirs_to_keep.append(d)
        dirs[:] = dirs_to_keep

        for f in files:
            file_path = root_path / f
            rel_file_path = rel_root / f
            if file_path.suffix in extensiones:
                if not config.debe_excluir(rel_file_path):
                    archivos.append(file_path)
    return archivos


def check_proyecto(
    path: str | Path,
    config: Optional[DocpactConfig] = None,
    diff_only: bool = False,
) -> ResultadoProyecto:
    """Verifica un proyecto completo (archivo o directorio) en paralelo.

    Args:
        path: Ruta al archivo o directorio.
        config: Configuración. Si es None, usa defaults.
        diff_only: Si True, solo verifica archivos modificados vs HEAD.

    Returns:
        ResultadoProyecto con todos los archivos y hallazgos.
    """
    if config is None:
        config = DocpactConfig()

    ruta = Path(path)
    if ruta.is_file():
        archivos = [ruta]
    elif ruta.is_dir():
        archivos = sorted(_escanear_eficiente(ruta, config, (".py", ".ts", ".tsx", ".jsx")))
    else:
        archivos = []

    if not archivos:
        return ResultadoProyecto(config=config)

    # Filtrar solo archivos modificados si diff_only está activo
    if diff_only:
        changed = _get_changed_files(ruta)
        if not changed:
            return ResultadoProyecto(config=config)
        changed_set = set(p.resolve() for p in changed)
        archivos = [a for a in archivos if a.resolve() in changed_set]

    if not archivos:
        return ResultadoProyecto(config=config)

    # Construir índice global de contratos para el análisis transitivo
    index = ContractIndex()
    proyecto_root = find_project_root(ruta)
    try:
        # Buscamos todos los archivos .py del proyecto para el índice (incluso los no modificados)
        todos_py = archivos
        if diff_only and ruta.is_dir():
            todos_py = sorted(_escanear_eficiente(ruta, config, (".py",)))
        index.build(todos_py, config, project_root=proyecto_root)
    except Exception:
        pass

    import concurrent.futures

    resultados_archivos: list[ResultadoArchivo] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futuros = {pool.submit(check_file, a, config, index): a for a in archivos}
        for futuro in concurrent.futures.as_completed(futuros):
            try:
                ra = futuro.result()
                if ra.funciones:
                    resultados_archivos.append(ra)
            except Exception:
                pass  # Error en un archivo no detiene el proyecto

    resultado = ResultadoProyecto(config=config)
    resultado.archivos = resultados_archivos

    # Cross-reference contra REGISTRO.md: detectar RNs fake y huerfanas.
    # Esto resuelve el problema de agentes que declaran 'rn: [RN-XXX]' sin
    # verificar que la regla exista en la documentacion canonica.
    # Envuelto en try/except: si REGISTRO no existe o hay error, no rompemos.
    try:
        from docpact.checker.rn_registry import crossref_contratos_registro
        from docpact.models.contrato import ContratoExtraido, TipoFuncion

        todos_los_contratos: list = []
        for ra in resultado.archivos:
            for rf in ra.funciones:
                if rf.contrato:
                    todos_los_contratos.append(
                        ContratoExtraido(
                            funcion=rf.nombre,
                            tipo=TipoFuncion(rf.tipo) if hasattr(rf, "tipo") else TipoFuncion.FUNCTION,
                            archivo=ra.archivo,
                            linea=rf.linea if hasattr(rf, "linea") else 0,
                            contrato=rf.contrato,
                            raw_text="",
                            errores=[],
                        )
                    )

        if todos_los_contratos and proyecto_root is not None:
            crossref = crossref_contratos_registro(todos_los_contratos, proyecto_root)
            resultado.rns_fake = crossref.rns_fake
            resultado.rns_huerfanas = crossref.rns_huerfanas
            resultado.rns_placeholders = crossref.rns_placeholders
    except Exception:
        # Cross-ref opcional. Si falla (REGISTRO no existe, import error, etc),
        # los campos quedan vacíos y el resto del check continúa normalmente.
        pass

    # Cross-reference RN: verificar que funciones llamadas tengan las RNs
    if resultados_archivos:
        _errores_xref = _check_cross_reference_proyecto(resultados_archivos, config)
        for ra in resultado.archivos:
            for rf in ra.funciones:
                for ex in _errores_xref:
                    if ex.archivo == ra.archivo:
                        rf.hallazgos.append(
                            Hallazgo(
                                tipo="warning",
                                campo="rn",
                                funcion=rf.nombre,
                                archivo=ex.archivo,
                                linea=ex.linea,
                                mensaje=ex.mensaje,
                                sugerencia=ex.sugerencia,
                            )
                        )
                # Suprimir warnings de cross-reference según docpact.toml
                rf.hallazgos = _suprimir_hallazgos(rf.hallazgos, config)

        # Module boundary check: verificar dependencias entre módulos
        if config.modules:
            from docpact.checker.boundary_checker import check_boundary

            _errores_boundary = check_boundary(resultados_archivos, config.modules)
            for ra in resultado.archivos:
                for rf in ra.funciones:
                    for eb in _errores_boundary:
                        if eb.archivo == ra.archivo and eb.funcion == rf.nombre:
                            rf.hallazgos.append(
                                Hallazgo(
                                    tipo="error",
                                    campo="dependencias",
                                    funcion=rf.nombre,
                                    archivo=eb.archivo,
                                    linea=rf.linea if hasattr(rf, "linea") else 0,
                                    mensaje=eb.mensaje,
                                    sugerencia=eb.sugerencia,
                                )
                            )

    return resultado


def _check_cross_reference_proyecto(
    resultados_archivos: list,
    config: object,
) -> list:
    """Cross-reference RN entre funciones del proyecto."""
    if not getattr(config, "rn_patrones", None):
        return []
    from docpact.checker.rn_crossref import (
        build_funcion_map,
        verificar_cross_reference,
    )

    # Construir mapa de funciones
    fuentes: dict[str, str] = {}
    todas_las_funciones_list = []
    for ra in resultados_archivos:
        archivo = getattr(ra, "archivo", "")
        if archivo:
            try:
                fuentes[archivo] = Path(archivo).read_text(encoding="utf-8")
            except Exception:
                pass
        todas_las_funciones_list.extend(getattr(ra, "funciones", []))

    mapa_funciones = build_funcion_map(todas_las_funciones_list, fuentes)

    errores: list = []
    for ra in resultados_archivos:
        for rf in getattr(ra, "funciones", []):
            contrato = getattr(rf, "contrato", None)
            if not contrato or not getattr(contrato, "rn", None):
                continue
            rn_ids = [r.id for r in contrato.rn if r.id]
            if not rn_ids:
                continue
            codigo = getattr(rf, "codigo_funcion", "") or fuentes.get(getattr(ra, "archivo", ""), "")
            if codigo:
                errs = verificar_cross_reference(
                    getattr(ra, "archivo", ""),
                    codigo,
                    rn_ids,
                    mapa_funciones,
                )
                errores.extend(errs)
    return errores


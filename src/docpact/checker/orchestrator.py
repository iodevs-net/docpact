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

from docpact.checker._file_utils import get_changed_files, escanear_eficiente
from docpact.checker._process_function import procesar_funcion
from docpact.checker.models import (
    Hallazgo,
    ResultadoArchivo,
    ResultadoFuncion,
    ResultadoProyecto,
    _suprimir_hallazgos,
)
from docpact.checker.ts_checker import check_file_ts
from docpact.checker.signature_checker import find_project_root
from docpact.config import DocpactConfig
from docpact.parser.extractor import extraer_docstrings
from docpact.checker.contract_index import ContractIndex, ImportResolver


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
                    procesar_funcion(
                        item, str(path), fuente, config, doc_map, resultado,
                        tiene_future_annotations=tiene_future_annotations,
                        index=index,
                        imports=imports,
                        modulo_actual=modulo_actual,
                        clase_actual=node.name,
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            procesar_funcion(
                node, str(path), fuente, config, doc_map, resultado,
                tiene_future_annotations=tiene_future_annotations,
                index=index,
                imports=imports,
                modulo_actual=modulo_actual,
            )

    return resultado


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
        archivos = sorted(escanear_eficiente(ruta, config, (".py", ".ts", ".tsx", ".jsx")))
    else:
        archivos = []

    if not archivos:
        return ResultadoProyecto(config=config)

    # Filtrar solo archivos modificados si diff_only está activo
    if diff_only:
        changed = get_changed_files(ruta)
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
            todos_py = sorted(escanear_eficiente(ruta, config, (".py",)))
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

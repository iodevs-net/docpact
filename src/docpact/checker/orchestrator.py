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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from docpact.checker.side_effects import check_side_effects
from docpact.checker.rn_checker import check_rn, extraer_comentarios_desde_fuente, _extraer_ids_rn
from docpact.checker.deps_checker import check_deps
from docpact.checker.import_checker import check_inline_imports
try:
    from docpact.checker.rn_registry_checker import check_rn_against_registry  # type: ignore[import-untyped]
except ImportError:
    check_rn_against_registry = None
from docpact.checker.rn_test_checker import check_rn_tests
from docpact.config import DocpactConfig
from docpact.models.contrato import (
    Contrato, ErrorParser, ReglaNegocio, Dependencia, SideEffect,
)
from docpact.parser.extractor import extraer_docstrings
from docpact.parser.lexer import tokenizar
from docpact.parser.parser import parsear
from docpact.parser.ts_parser import extraer_contratos_ts
from docpact.checker.ts_sidefx import check_side_effects_ts

@dataclass
class Hallazgo:
    """Un hallazgo individual de la verificación."""
    tipo: str  # "error" o "warning"
    campo: str
    funcion: str
    archivo: str
    linea: int
    mensaje: str
    sugerencia: str = ""

    def a_error_parser(self) -> ErrorParser:
        return ErrorParser(
            campo=self.campo,
            mensaje=self.mensaje,
            linea=self.linea,
            sugerencia=self.sugerencia,
        )


@dataclass
class ResultadoFuncion:
    """Resultado de la verificación de una función."""
    nombre: str
    archivo: str
    linea: int
    tiene_contrato: bool
    contrato: Optional[Contrato] = None
    hallazgos: list[Hallazgo] = field(default_factory=list)

    @property
    def errores(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.tipo == "error"]

    @property
    def warnings(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.tipo == "warning"]

    @property
    def valido(self) -> bool:
        return len(self.errores) == 0


@dataclass
class ResultadoArchivo:
    """Resultado de la verificación de un archivo completo."""
    archivo: str
    funciones: list[ResultadoFuncion] = field(default_factory=list)

    @property
    def total_funciones(self) -> int:
        return len(self.funciones)

    @property
    def funciones_con_contrato(self) -> int:
        return sum(1 for f in self.funciones if f.tiene_contrato)

    @property
    def total_errores(self) -> int:
        return sum(len(f.errores) for f in self.funciones)

    @property
    def total_warnings(self) -> int:
        return sum(len(f.warnings) for f in self.funciones)


@dataclass
class ResultadoProyecto:
    """Resultado de la verificación de todo el proyecto."""
    archivos: list[ResultadoArchivo] = field(default_factory=list)
    config: DocpactConfig = field(default_factory=DocpactConfig)

    @property
    def total_funciones(self) -> int:
        return sum(a.total_funciones for a in self.archivos)

    @property
    def funciones_con_contrato(self) -> int:
        return sum(a.funciones_con_contrato for a in self.archivos)

    @property
    def total_errores(self) -> int:
        return sum(a.total_errores for a in self.archivos)

    @property
    def total_warnings(self) -> int:
        return sum(a.total_warnings for a in self.archivos)

    @property
    def total_archivos(self) -> int:
        return len(self.archivos)

    def calcular_score(self) -> int:
        """Calcula el score AI-Native (0-100)."""
        if self.total_funciones == 0:
            return 0

        score = 100

        # Penalización por funciones sin CONTRATO
        sin_contrato = self.total_funciones - self.funciones_con_contrato
        if sin_contrato > 0:
            penalty_sin = min(30, int((sin_contrato / self.total_funciones) * 50))
            score -= penalty_sin

        # Penalización por errores de verificación
        if self.total_errores > 0:
            penalty_errores = min(40, self.total_errores * 10)
            score -= penalty_errores

        # Penalización por warnings
        if self.total_warnings > 0:
            penalty_warnings = min(15, self.total_warnings * 3)
            score -= penalty_warnings

        return max(0, score)

    @property
    def nivel(self) -> str:
        score = self.calcular_score()
        if score >= 90:
            return "L4 — AI-Optimized"
        elif score >= 75:
            return "L3 — AI-Native"
        elif score >= 50:
            return "L2 — AI-Friendly"
        elif score >= 25:
            return "L1 — AI-Aware"
        return "L0 — Human-Native"


def check_file(
    archivo: str | Path,
    config: DocpactConfig,
) -> ResultadoArchivo:
    """Verifica un archivo Python, TypeScript o JSX.

    Args:
        archivo: Ruta al archivo.
        config: Configuración de docpact.

    Returns:
        ResultadoArchivo con todas las funciones y sus hallazgos.
    """
    path = Path(archivo)
    if config.debe_excluir(path):
        return ResultadoArchivo(archivo=str(path))

    if path.suffix in (".ts", ".tsx", ".jsx"):
        return _check_file_ts(path, config)

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
        doc_map[nombre] = (linea, tipo, doc)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _procesar_funcion(
                        item, str(path), fuente, config, doc_map, resultado
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _procesar_funcion(
                node, str(path), fuente, config, doc_map, resultado
            )

    return resultado
def _check_file_ts(path: Path, config: DocpactConfig) -> ResultadoArchivo:
    """Verifica un archivo TypeScript/JSX extrayendo CONTRATOS con regex."""
    resultado = ResultadoArchivo(archivo=str(path))

    try:
        contratos = extraer_contratos_ts(str(path))
        fuente = path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return resultado

    lineas_fn = fuente.splitlines()

    for c in contratos:
        nombre = c.get("nombre_funcion", "")
        if not nombre or nombre.startswith("_"):
            continue

        tiene_contrato = bool(
            c.get("input") or c.get("output") or c.get("side_effects")
        )

        if not tiene_contrato and config.strict:
            resultado.funciones.append(ResultadoFuncion(
                nombre=nombre,
                archivo=str(path),
                linea=c.get("linea", 0),
                tiene_contrato=False,
                hallazgos=[
                    Hallazgo(
                        tipo="error",
                        campo="presencia",
                        funcion=nombre,
                        archivo=str(path),
                        linea=c.get("linea", 0),
                        mensaje=f"Función pública '{nombre}' sin CONTRATO",
                        sugerencia="Agrega un bloque CONTRATO al comentario de la función",
                    )
                ],
            ))
        elif tiene_contrato:
            hallazgos_ts: list[Hallazgo] = []
            linea_contrato = c.get("linea", 1)

            # ── 1. Side effects ──
            try:
                inicio = linea_contrato - 1
                codigo_fn = "\n".join(lineas_fn[inicio:])
                se_declarados = c.get("side_effects", [])
                if isinstance(se_declarados, str):
                    se_declarados = [se_declarados]
                err_sidefx = check_side_effects_ts(codigo_fn, se_declarados)
            except Exception:
                err_sidefx = []
            for msg in err_sidefx:
                # Coincidencia de side_effects en TS es heurística:
                # Inertia router, window.open, fetch pueden no detectarse
                # por contexto. Usar warning (no error) para evitar falsos
                # positivos que bloqueen commits.
                hallazgos_ts.append(Hallazgo(
                    tipo="warning",
                    campo="side_effects",
                    funcion=nombre,
                    archivo=str(path),
                    linea=linea_contrato,
                    mensaje=msg,
                ))

            # ── 2. Dependencias ──
            deps = c.get("dependencias", [])
            if isinstance(deps, list):
                for dep in deps:
                    dep = dep.strip()
                    if not dep:
                        continue
                    # Separar modulo y simbolo
                    if "::" in dep:
                        modulo_path, _simbolo = dep.split("::", 1)
                    else:
                        modulo_path = dep

                    # ── npm packages / Vite aliases ──
                    # Paths que empiezan con @org/ son npm packages (node_modules)
                    # ej: @inertiajs/react, @vitejs/plugin
                    if modulo_path.startswith("@") and "/" in modulo_path:
                        continue

                    # Vite alias @/ (mapea a resources/js/ en ioDesk-3)
                    if modulo_path.startswith("@/"):
                        base_dir = path.parent
                        vite_base = base_dir
                        # Subir hasta encontrar resources/js/
                        for p in [base_dir] + list(base_dir.parents):
                            if (p / "resources" / "js").is_dir():
                                vite_base = p / "resources" / "js"
                                break
                        ruta_rel = vite_base / modulo_path[2:]
                        existe = False
                        for ext in (".ts", ".tsx", ".jsx"):
                            if ruta_rel.with_suffix(ext).exists():
                                existe = True
                                break
                        if existe:
                            continue
                        # Si no se resuelve, silenciar (falso positivo de alias)
                        continue

                    # Resolver contra directorio del archivo actual
                    base_dir = path.parent
                    ruta_rel = base_dir / modulo_path
                    existe = False
                    for ext in (".py", ".ts", ".tsx", ".jsx"):
                        if ruta_rel.with_suffix(ext).exists():
                            existe = True
                            break
                    if not ruta_rel.exists() and not existe:
                        hallazgos_ts.append(Hallazgo(
                            tipo="warning",  # Downgraded to warning since it's often an alias
                            campo="dependencias",
                            funcion=nombre,
                            archivo=str(path),
                            linea=linea_contrato,
                            mensaje=f"'{nombre}': dependencia '{dep}' — "
                                    f"archivo '{modulo_path}' no encontrado",
                            sugerencia=f"Verifica la ruta (buscado desde {base_dir})",
                        ))

            # ── 3. RN check ──
            rn_list = c.get("rn", [])
            if isinstance(rn_list, list):
                # Extraer comentarios // RN-XXX del codigo fuente
                comentarios_ts: list[str] = []
                # Buscar desde la linea del CONTRATO hasta fin del archivo
                from_i = max(0, linea_contrato - 1)
                for l in lineas_fn[from_i:]:
                    stripped = l.strip()
                    if "RN-" in stripped or "Gotcha" in stripped:
                        comentarios_ts.append(stripped)
                ids_en_codigo = set()
                import re as _re
                patron = _re.compile(r"RN-[\w-]+|Gotcha #\d+")
                for cmt in comentarios_ts:
                    for match in patron.finditer(cmt):
                        ids_en_codigo.add(match.group())

                for rn_entry in rn_list:
                    rn_id = ""
                    if isinstance(rn_entry, dict):
                        rn_id = rn_entry.get("id", "")
                    elif isinstance(rn_entry, str):
                        rn_id = rn_entry
                    if rn_id and rn_id not in ids_en_codigo:
                        hallazgos_ts.append(Hallazgo(
                            tipo="warning",
                            campo="rn",
                            funcion=nombre,
                            archivo=str(path),
                            linea=linea_contrato,
                            mensaje=f"'{nombre}': RN '{rn_id}' declarada pero no encontrada "
                                    f"como comentario en el código",
                            sugerencia=f"Agrega '// {rn_id}' en el lugar donde se implementa",
                        ))

            # RN test checker para TS: cada RN-XXX debe tener tests/rn/test_rn_XXX.py
            if rn_list:
                ts_rn_ids = []
                for rn_entry in rn_list:
                    if isinstance(rn_entry, dict):
                        rid = rn_entry.get("id", "")
                        if rid:
                            ts_rn_ids.append(rid)
                    elif isinstance(rn_entry, str):
                        ts_rn_ids.append(rn_entry)
                if ts_rn_ids:
                    ts_root = _find_project_root(str(path))
                    if ts_root is not None:
                        rn_test_errors_ts = check_rn_tests(ts_rn_ids, ts_root, nombre)
                        for e in rn_test_errors_ts:
                            hallazgos_ts.append(Hallazgo(tipo="error", campo=e.campo, funcion=nombre, archivo=str(path), linea=linea_contrato, mensaje=e.mensaje, sugerencia=e.sugerencia))
            resultado.funciones.append(ResultadoFuncion(
                nombre=nombre,
                archivo=str(path),
                linea=linea_contrato,
                tiene_contrato=True,
                hallazgos=hallazgos_ts,
            ))
    return resultado


def _procesar_funcion(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    archivo: str,
    fuente: str,
    config: DocpactConfig,
    doc_map: dict[str, tuple[int, str, str]],
    resultado: ResultadoArchivo,
) -> None:
    """Procesa una función: extrae CONTRATO y ejecuta checkers."""
    nombre = node.name

    # Ignorar privadas
    if nombre.startswith("_"):
        return

    # Obtener docstring
    info = doc_map.get(nombre)
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
            res.hallazgos.append(Hallazgo(
                tipo="error",
                campo="presencia",
                funcion=nombre,
                archivo=archivo,
                linea=node.lineno,
                mensaje=f"Función pública '{nombre}' sin CONTRATO",
                sugerencia="Agrega un bloque CONTRATO al docstring",
            ))
        resultado.funciones.append(res)
        return

    if info is None:
        return

    _, _, doc = info

    # Parsear CONTRATO del docstring
    tokens = tokenizar(doc)
    contrato, parse_errors = parsear(tokens)

    hay_contrato = bool(contrato.side_effects or contrato.rn or contrato.input or contrato.output)

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
        resultado.funciones.append(ResultadoFuncion(
            nombre=nombre,
            archivo=archivo,
            linea=node.lineno,
            tiene_contrato=False,
        ))
        return

    # Hay CONTRATO — ejecutar verificadores
    hallazgos: list[Hallazgo] = []

    # Parse errors first
    for pe in parse_errors:
        hallazgos.append(Hallazgo(
            tipo="warning",
            campo=pe.campo,
            funcion=nombre,
            archivo=archivo,
            linea=pe.linea or node.lineno,
            mensaje=pe.mensaje,
            sugerencia=pe.sugerencia,
        ))

    # Side effects
    se_errores = check_side_effects(node, contrato, config, nombre, archivo)
    for se in se_errores:
        hallazgos.append(Hallazgo(
            tipo="error" if "pero se detectaron" in se.mensaje else "warning",
            campo=se.campo,
            funcion=nombre,
            archivo=archivo,
            linea=se.linea or node.lineno,
            mensaje=se.mensaje,
            sugerencia=se.sugerencia,
        ))

    # RN check — usa la fuente original para extraer comentarios
    rn_errores = _check_rn_con_fuente(node, contrato, fuente, config.rn_prefix, nombre)
    for rn in rn_errores:
        hallazgos.append(Hallazgo(
            tipo="warning",
            campo=rn.campo,
            funcion=nombre,
            archivo=archivo,
            linea=rn.linea or node.lineno,
            mensaje=rn.mensaje,
            sugerencia=rn.sugerencia,
        ))

    # Dependencias
    deps_errores = check_deps(contrato, archivo, nombre)
    for dep in deps_errores:
        hallazgos.append(Hallazgo(
            tipo="error",
            campo=dep.campo,
            funcion=nombre,
            archivo=archivo,
            linea=dep.linea or node.lineno,
            mensaje=dep.mensaje,
            sugerencia=dep.sugerencia,
        ))

    # Imports inline que duplican dependencias del CONTRATO
    lineas_f = fuente.splitlines()
    linea_fin_f = getattr(node, 'end_lineno', len(lineas_f))
    codigo_funcion = "\n".join(lineas_f[node.lineno - 1 : linea_fin_f])
    imp_errores = check_inline_imports(codigo_funcion, [d.ref for d in contrato.dependencias], nombre, archivo, node.lineno)
    for imp in imp_errores:
        hallazgos.append(Hallazgo(tipo="warning", campo=imp.campo, funcion=nombre, archivo=archivo, linea=imp.linea or node.lineno, mensaje=imp.mensaje, sugerencia=imp.sugerencia))

    # RN registry check
    from pathlib import Path as _Path
    from typing import Optional as _Optional
    # Verificar firma: input/output del CONTRATO vs firma real de Python
    _check_signature(node, contrato, nombre, archivo, hallazgos)
    
    if check_rn_against_registry is not None:
        proyecto_root = _find_project_root(archivo)
        if proyecto_root is not None:
            rn_reg_errors, rn_reg_infos = check_rn_against_registry(proyecto_root, contrato.rn)
            for e in rn_reg_errors:
                hallazgos.append(Hallazgo(tipo="error", campo=e.campo, funcion=nombre, archivo=archivo, linea=e.linea or node.lineno, mensaje=e.mensaje, sugerencia=e.sugerencia))
            for i in rn_reg_infos:
                hallazgos.append(Hallazgo(tipo="info", campo=i.campo, funcion=nombre, archivo=archivo, linea=i.linea or node.lineno, mensaje=i.mensaje, sugerencia=i.sugerencia))

    # RN test checker: cada RN-XXX debe tener tests/rn/test_rn_XXX.py
    rn_ids = [r.id for r in contrato.rn]
    if rn_ids:
        proyecto_root = _find_project_root(archivo)
        if proyecto_root is not None:
            rn_test_errors = check_rn_tests(rn_ids, proyecto_root, nombre)
            for e in rn_test_errors:
                hallazgos.append(Hallazgo(tipo="error", campo=e.campo, funcion=nombre, archivo=archivo, linea=node.lineno, mensaje=e.mensaje, sugerencia=e.sugerencia))

    resultado.funciones.append(ResultadoFuncion(
        nombre=nombre,
        archivo=archivo,
        linea=node.lineno,
        tiene_contrato=True,
        contrato=contrato,
        hallazgos=hallazgos,
    ))

def _check_rn_con_fuente(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    contrato: Contrato,
    fuente: str,
    prefix: str,
    nombre: str,
) -> list[ErrorParser]:
    """Verifica RNs usando la fuente original para extraer comentarios."""
    if not contrato.rn:
        return []

    # Extraer comentarios de la fuente
    linea_inicio = node.lineno
    linea_fin = getattr(node, 'end_lineno', node.lineno + 50) or (node.lineno + 50)
    comentarios = extraer_comentarios_desde_fuente(fuente, linea_inicio, linea_fin)
    ids_en_codigo = set(_extraer_ids_rn(comentarios, prefix))

    errores: list[ErrorParser] = []
    for rn in contrato.rn:
        if rn.id not in ids_en_codigo:
            errores.append(ErrorParser(
                "rn",
                f"'{nombre}': RN '{rn.id}' declarada pero no encontrada "
                f"como comentario en el código",
                sugerencia=f"Agrega '# {rn.id}' en el lugar donde se implementa",
            ))
    return errores


def _get_changed_files(ruta_base: Path) -> list[Path]:
    """Obtiene archivos modificados via git diff.

    Returns:
        Lista de Paths relativos a ruta_base de archivos modificados.
        Vacía si no es un repo git o si no hay cambios.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=ruta_base,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [ruta_base / p for p in result.stdout.strip().splitlines()]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return []


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
        archivos = sorted(
            list(ruta.rglob("*.py"))
            + list(ruta.rglob("*.ts"))
            + list(ruta.rglob("*.tsx"))
            + list(ruta.rglob("*.jsx"))
        )
    else:
        archivos = []

    archivos = [a for a in archivos if not config.debe_excluir(a)]

    if not archivos:
        return ResultadoProyecto(config=config)

    # Filtrar solo archivos modificados si diff_only está activo
    if diff_only:
        changed = _get_changed_files(ruta)
        if changed:
            changed_set = set(p.resolve() for p in changed)
            archivos = [a for a in archivos if a.resolve() in changed_set]
        # Si no hay cambios o el git diff falla, continuar con archivos filtrados
        # (puede quedar vacío → resultado vacío = OK)

    if not archivos:
        return ResultadoProyecto(config=config)

    import concurrent.futures
    resultados_archivos: list[ResultadoArchivo] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futuros = {pool.submit(check_file, a, config): a for a in archivos}
        for futuro in concurrent.futures.as_completed(futuros):
            try:
                ra = futuro.result()
                if ra.funciones:
                    resultados_archivos.append(ra)
            except Exception:
                pass  # Error en un archivo no detiene el proyecto

    resultado = ResultadoProyecto(config=config)
    resultado.archivos = resultados_archivos
    return resultado

def _check_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    contrato: Contrato,
    nombre: str,
    archivo: str,
    hallazgos: list[Hallazgo],
) -> None:
    """Verifica que input/output del CONTRATO coincidan con la firma real."""
    import inspect
    # Verificar que input del CONTRATO tenga al menos los parametros de la funcion
    params_contrato = {c.nombre for c in contrato.input.values()} if contrato.input else set()
    params_reales = {arg.arg for arg in node.args.args if arg.arg != 'self'}
    
    # Parametros en la firma pero no en el CONTRATO
    if params_reales and contrato.input is not None:
        faltantes = params_reales - params_contrato
        if faltantes:
            for p in sorted(faltantes):
                hallazgos.append(Hallazgo(
                    tipo="warning", campo="input",
                    funcion=nombre, archivo=archivo,
                    linea=node.lineno,
                    mensaje=f"Parametro '{p}' en firma de funcion pero no declarado en input del CONTRATO",
                    sugerencia=f"Agregar '{p}: type — desc' en input del CONTRATO"
                ))
    
    # Verificar output del CONTRATO vs return annotation
    if contrato.output and hasattr(node, 'returns') and node.returns is not None:
        try:
            return_type = ast.unparse(node.returns)
            contrato_out = contrato.output
            if contrato_out and contrato_out.lower() not in return_type.lower() and return_type.lower() not in contrato_out.lower():
                hallazgos.append(Hallazgo(
                    tipo="info", campo="output",
                    funcion=nombre, archivo=archivo,
                    linea=node.lineno,
                    mensaje=f"Output del CONTRATO ('{contrato_out}') difiere del type hint ('{return_type}')",
                    sugerencia="Verificar que coincidan o que la diferencia sea intencional"
                ))
        except Exception:
            pass

def _find_project_root(archivo: str) -> Optional[Path]:
    """Busca la raiz del proyecto ascendiendo desde un archivo."""
    from pathlib import Path as _Path
    path = _Path(archivo).resolve()
    for parent in [path] + list(path.parents):
        reg = parent / "docs" / "reglas-del-negocio" / "REGISTRO.md"
        if reg.exists():
            return parent
        if (parent / "pyproject.toml").exists() or (parent / "docpact.toml").exists():
            return parent
    return None

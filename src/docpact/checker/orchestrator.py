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
from docpact.config import DocpactConfig
from docpact.models.contrato import Contrato, ErrorParser
from docpact.parser.extractor import extraer_docstrings
from docpact.parser.lexer import tokenizar
from docpact.parser.parser import parsear


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
    """Verifica un archivo Python completo.

    Args:
        archivo: Ruta al archivo .py.
        config: Configuración de docpact.

    Returns:
        ResultadoArchivo con todas las funciones y sus hallazgos.
    """
    path = Path(archivo)
    if config.debe_excluir(path):
        return ResultadoArchivo(archivo=str(path))

    try:
        with open(path, "r", encoding="utf-8") as f:
            fuente = f.read()
        tree = ast.parse(fuente, filename=str(path))
    except (SyntaxError, FileNotFoundError) as e:
        # Archivo con error de sintaxis — reportamos pero seguimos
        return ResultadoArchivo(archivo=str(path))

    resultado = ResultadoArchivo(archivo=str(path))

    # Extraer funciones con docstring (usa la lógica de Fase 1)
    doc_funciones = extraer_docstrings(path)

    # Crear un mapa: nombre_función → (linea, tipo, docstring)
    # Nota: si hay funciones con el mismo nombre, solo procesamos la última
    doc_map: dict[str, tuple[int, str, str]] = {}
    for linea, nombre, tipo, doc in doc_funciones:
        doc_map[nombre] = (linea, tipo, doc)

    # Recorrer AST para encontrar nodos de funciones
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


def check_proyecto(
    path: str | Path,
    config: Optional[DocpactConfig] = None,
) -> ResultadoProyecto:
    """Verifica un proyecto completo (archivo o directorio).

    Args:
        path: Ruta al archivo o directorio.
        config: Configuración. Si es None, usa defaults.

    Returns:
        ResultadoProyecto con todos los archivos y hallazgos.
    """
    if config is None:
        config = DocpactConfig()

    ruta = Path(path)
    if ruta.is_file():
        archivos = [ruta]
    elif ruta.is_dir():
        archivos = sorted(ruta.rglob("*.py"))
    else:
        archivos = []

    resultado = ResultadoProyecto(config=config)
    for archivo in archivos:
        if config.debe_excluir(archivo):
            continue
        ra = check_file(archivo, config)
        if ra.funciones:
            resultado.archivos.append(ra)

    return resultado

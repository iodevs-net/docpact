"""docpact API — interfaz pública para agentes.

Uso desde Python:
  >>> from docpact.api import check_file, check_proyecto, extract_contratos
  >>> resultado = check_file("soporte/services/tickets.py")
  >>> resultado.valido
  True
  >>> resultado.score
  70

Uso desde agente (MCP):
  Las mismas funciones están expuestas como herramientas MCP
  en docpact.mcp_server.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from docpact.checker.orchestrator import (
    check_file as _check_file,
    check_proyecto as _check_proyecto,
    ResultadoArchivo,
    ResultadoFuncion,
    ResultadoProyecto,
    Hallazgo,
)
from docpact.config import DocpactConfig
from docpact.parser.extractor import extraer_docstrings
from docpact.parser.lexer import tokenizar
from docpact.parser.parser import parsear


def check_file(
    path: str | Path,
    config: Optional[DocpactConfig] = None,
    strict: bool = False,
) -> ResultadoArchivo:
    """Verifica un archivo Python.

    Args:
        path: Ruta al archivo .py.
        config: Configuración opcional. Si es None, usa defaults.
        strict: Si True, falla si hay funciones públicas sin CONTRATO.

    Returns:
        ResultadoArchivo con todas las funciones y sus hallazgos.
    """
    if config is None:
        config = DocpactConfig()
    if strict:
        config.strict = True
    return _check_file(str(path), config)


def check_proyecto(
    path: str | Path,
    config: Optional[DocpactConfig] = None,
    strict: bool = False,
) -> ResultadoProyecto:
    """Verifica un proyecto completo (archivo o directorio).

    Args:
        path: Ruta al archivo o directorio.
        config: Configuración opcional.
        strict: Si True, falla si hay funciones públicas sin CONTRATO.

    Returns:
        ResultadoProyecto con todos los archivos y hallazgos.
    """
    if config is None:
        config = DocpactConfig()
    if strict:
        config.strict = True
    return _check_proyecto(str(path), config)


def extract_contratos(
    path: str | Path,
    incluir_privadas: bool = False,
) -> list[dict]:
    """Extrae todos los CONTRATOS de un archivo o directorio.

    Args:
        path: Ruta al archivo o directorio.
        incluir_privadas: Si True, incluye funciones privadas.

    Returns:
        Lista de CONTRATOS como dicts serializables.
    """
    ruta = Path(path)
    archivos = list(ruta.rglob("*.py")) if ruta.is_dir() else [ruta]

    resultados = []
    for archivo in archivos:
        if _es_excluido(archivo):
            continue
        try:
            docstrings = extraer_docstrings(archivo, incluir_privadas=incluir_privadas)
        except (SyntaxError, FileNotFoundError):
            continue

        for linea, nombre, tipo, doc in docstrings:
            tokens = tokenizar(doc)
            contrato, errores = parsear(tokens)
            if contrato.side_effects or contrato.rn or contrato.input or contrato.output:
                resultados.append({
                    "archivo": str(archivo),
                    "funcion": nombre,
                    "tipo": tipo,
                    "linea": linea,
                    "contrato": {
                        "input": {k: {"tipo": v.tipo, "descripcion": v.descripcion}
                                  for k, v in contrato.input.items()},
                        "output": contrato.output,
                        "output_descripcion": contrato.output_descripcion,
                        "side_effects": [s.descripcion for s in contrato.side_effects],
                        "rn": [{"id": r.id, "descripcion": r.descripcion} for r in contrato.rn],
                        "borde": [{"condicion": b.condicion, "comportamiento": b.comportamiento}
                                  for b in contrato.borde],
                        "dependencias": [d.ref for d in contrato.dependencias],
                    },
                    "errores": [{"campo": e.campo, "mensaje": e.mensaje, "sugerencia": e.sugerencia}
                                for e in errores],
                })
    return resultados


def _es_excluido(path: Path) -> bool:
    excluidos = {
        "__pycache__", ".venv", "venv", "node_modules",
        ".git", "migrations", ".pytest_cache",
    }
    for parte in path.parts:
        if parte in excluidos:
            return True
    return False


__all__ = [
    "check_file",
    "check_proyecto",
    "extract_contratos",
    "ResultadoArchivo",
    "ResultadoFuncion",
    "ResultadoProyecto",
    "Hallazgo",
    "DocpactConfig",
]

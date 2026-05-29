"""Índice global de contratos del proyecto para la resolución de efectos transitivos.

Permite indexar todos los contratos definidos en el proyecto y mapear llamadas
locales utilizando resolución estática de imports (incluyendo inline imports).
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from docpact.config import DocpactConfig
from docpact.models.contrato import Contrato
from docpact.parser.lexer import tokenizar
from docpact.parser.parser import parsear

logger = logging.getLogger(__name__)


@dataclass
class ContratoIndexado:
    """Representa un contrato registrado en el índice global."""

    modulo: str            # ej: "soporte.services.tickets"
    clase: Optional[str]   # ej: "TicketService" o None
    funcion: str           # ej: "crear_ticket"
    side_effects: list[str]
    archivo: str
    linea: int


class ImportResolver(ast.NodeVisitor):
    """Extrae todos los imports (tanto globales como locales/inline) de un archivo Python."""

    def __init__(self, filepath: Path, project_root: Optional[Path] = None):
        self.filepath = filepath
        self.project_root = project_root
        # Mapa: nombre_local -> modulo_completo_o_simbolo
        # Ej: "TicketService" -> "soporte.services.tickets.TicketService"
        self.imports: dict[str, str] = {}
        # Nombre del módulo actual basado en la ruta relativa
        self.modulo_actual = self._obtener_nombre_modulo()

    def _obtener_nombre_modulo(self) -> str:
        if not self.project_root:
            return self.filepath.stem
        try:
            rel = self.filepath.resolve().relative_to(self.project_root.resolve())
            partes = list(rel.parts)
            if partes[-1] == "__init__.py":
                partes.pop()
            else:
                partes[-1] = rel.stem
            return ".".join(partes)
        except Exception:
            return self.filepath.stem

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            nombre = alias.name
            asname = alias.asname or nombre.split(".")[-1]
            self.imports[asname] = nombre
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        modulo = node.module or ""
        nivel = node.level

        # Manejo de imports relativos (ej: from .models import Ticket)
        if nivel > 0:
            partes_actual = self.modulo_actual.split(".")
            # Retroceder según el nivel (1 = mismo dir, 2 = padre, etc.)
            if len(partes_actual) >= nivel:
                base = ".".join(partes_actual[:-nivel])
                if modulo:
                    modulo = f"{base}.{modulo}" if base else modulo
                else:
                    modulo = base
            else:
                # Fallback seguro
                pass

        for alias in node.names:
            nombre = alias.name
            asname = alias.asname or nombre
            if modulo:
                self.imports[asname] = f"{modulo}.{nombre}"
            else:
                self.imports[asname] = nombre
        self.generic_visit(node)


# Nombres de métodos genéricos de frameworks (Django ORM, HTTP views, Python builtins)
# que son extremadamente comunes y causan colisiones de nombres cortos.
# Estos NUNCA se registran como clave corta standalone.
_NOMBRES_GENERICOS_FRAMEWORK = frozenset({
    # Django ORM / Model
    "save", "delete", "create", "update", "get", "filter", "exclude",
    "get_or_create", "update_or_create", "bulk_create", "bulk_update",
    "clean", "full_clean", "validate",
    # Django views / HTTP verbs
    "get", "post", "put", "patch", "delete", "head", "options",
    "dispatch", "setup",
    # Django management commands
    "handle", "add_arguments",
    # Python builtins / dunder
    "__init__", "__str__", "__repr__", "__call__",
})


class ContractIndex:
    """Índice global de todos los contratos definidos en el proyecto."""

    # Valor centinela para indicar que un nombre corto es ambiguo
    # (existe en múltiples módulos con contratos diferentes)
    _AMBIGUOUS = object()

    def __init__(self):
        # Mapa: "modulo.clase.funcion" o "modulo.funcion" -> ContratoIndexado
        self.indice: dict[str, ContratoIndexado | object] = {}
        self.project_root: Optional[Path] = None

    def build(self, archivos: list[Path], config: DocpactConfig, project_root: Optional[Path] = None) -> None:
        """Parsea y registra los contratos de todos los archivos del proyecto."""
        self.project_root = project_root
        for archivo in archivos:
            if not archivo.suffix == ".py":
                continue
            try:
                self._indexar_archivo(archivo, config)
            except Exception as e:
                logger.warning(f"Error indexando {archivo}: {e}", exc_info=True)

    def _indexar_archivo(self, filepath: Path, config: DocpactConfig) -> None:
        contenido = filepath.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(contenido)
        except SyntaxError:
            return

        # Calcular el nombre del módulo actual
        resolver = ImportResolver(filepath, self.project_root)
        modulo = resolver.modulo_actual

        class ClassAndFuncIndexer(ast.NodeVisitor):
            def __init__(self, index: ContractIndex, file_path: str):
                self.index = index
                self.file_path = file_path
                self.clase_actual: Optional[str] = None

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                old_clase = self.clase_actual
                self.clase_actual = node.name
                self.generic_visit(node)
                self.clase_actual = old_clase

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._procesar_nodo(node)
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._procesar_nodo(node)
                self.generic_visit(node)

            def _procesar_nodo(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                doc = ast.get_docstring(node)
                if not doc or "CONTRATO:" not in doc:
                    return

                tokens = tokenizar(doc)
                contrato, _ = parsear(tokens)
                if not contrato:
                    return

                side_effects = [s.descripcion.lower().strip() for s in contrato.side_effects]

                # Construir clave calificada
                clave = f"{modulo}."
                if self.clase_actual:
                    clave += f"{self.clase_actual}."
                clave += node.name

                contrato_idx = ContratoIndexado(
                    modulo=modulo,
                    clase=self.clase_actual,
                    funcion=node.name,
                    side_effects=side_effects,
                    archivo=self.file_path,
                    linea=node.lineno,
                )

                # Clave calificada completa: siempre se registra (no hay colisión posible)
                self.index.indice[clave] = contrato_idx

                # Alias "Clase.metodo": registrar solo si no hay colisión
                if self.clase_actual:
                    clave_clase = f"{self.clase_actual}.{node.name}"
                    existente = self.index.indice.get(clave_clase)
                    if existente is None:
                        self.index.indice[clave_clase] = contrato_idx
                    elif existente is not ContractIndex._AMBIGUOUS and isinstance(existente, ContratoIndexado) and existente.modulo != modulo:
                        self.index.indice[clave_clase] = ContractIndex._AMBIGUOUS

                # Alias corto "funcion": NO registrar si es nombre genérico del framework
                if node.name not in _NOMBRES_GENERICOS_FRAMEWORK:
                    existente = self.index.indice.get(node.name)
                    if existente is None:
                        self.index.indice[node.name] = contrato_idx
                    elif existente is not ContractIndex._AMBIGUOUS and isinstance(existente, ContratoIndexado) and existente.modulo != modulo:
                        # Colisión: mismo nombre corto, módulos diferentes -> ambiguo
                        self.index.indice[node.name] = ContractIndex._AMBIGUOUS

        indexer = ClassAndFuncIndexer(self, str(filepath))
        indexer.visit(tree)

    def lookup(
        self,
        nombre_llamada: str,
        imports: dict[str, str],
        modulo_actual: str,
        clase_contexto: Optional[str] = None
    ) -> Optional[ContratoIndexado]:
        """Busca un contrato en el índice resolviendo nombres calificados."""
        def _get_valid(key: str) -> Optional[ContratoIndexado]:
            """Obtiene una entrada del índice, retornando None si es ambigua."""
            entry = self.indice.get(key)
            if entry is ContractIndex._AMBIGUOUS or not isinstance(entry, ContratoIndexado):
                return None
            return entry

        # 1. Búsqueda exacta directa (ej: clave calificada completa)
        resultado = _get_valid(nombre_llamada)
        if resultado:
            return resultado

        partes = nombre_llamada.split(".")
        base = partes[0]

        # 2. Intentar resolver usando la tabla de imports locales
        if base in imports:
            modulo_resuelto = imports[base]
            # Si el import apunta al símbolo final (ej: from x import func -> "modulo.completo.func")
            if len(partes) == 1:
                resultado = _get_valid(modulo_resuelto)
                if resultado:
                    return resultado
            else:
                # Si el import apunta a la clase/modulo (ej: from x import TicketService -> "modulo.completo.TicketService")
                resto = ".".join(partes[1:])
                clave = f"{modulo_resuelto}.{resto}"
                resultado = _get_valid(clave)
                if resultado:
                    return resultado

        # 3. Intentar resolver en el mismo módulo actual (llamadas locales)
        if clase_contexto and len(partes) == 1:
            clave_local = f"{modulo_actual}.{clase_contexto}.{nombre_llamada}"
            resultado = _get_valid(clave_local)
            if resultado:
                return resultado
        elif len(partes) == 1:
            clave_local = f"{modulo_actual}.{nombre_llamada}"
            resultado = _get_valid(clave_local)
            if resultado:
                return resultado

        # 4. Fallback: búsqueda por nombre corto (solo si no es ambiguo)
        resultado = _get_valid(nombre_llamada)
        if resultado:
            return resultado

        return None

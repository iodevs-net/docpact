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


class ContractIndex:
    """Índice global de todos los contratos definidos en el proyecto."""

    def __init__(self):
        # Mapa: "modulo.clase.funcion" o "modulo.funcion" -> ContratoIndexado
        self.indice: dict[str, ContratoIndexado] = {}
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

                self.index.indice[clave] = contrato_idx

                # También registrar por alias locales/cortos para mayor resiliencia
                if self.clase_actual:
                    self.index.indice[f"{self.clase_actual}.{node.name}"] = contrato_idx
                self.index.indice[node.name] = contrato_idx

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
        # 1. Búsqueda exacta directa (ej: si ya viene calificado por casualidad o es global)
        if nombre_llamada in self.indice:
            return self.indice[nombre_llamada]

        partes = nombre_llamada.split(".")
        base = partes[0]

        # 2. Intentar resolver usando la tabla de imports locales
        if base in imports:
            modulo_resuelto = imports[base]
            # Si el import apunta al símbolo final (ej: from x import func -> "modulo.completo.func")
            if len(partes) == 1:
                if modulo_resuelto in self.indice:
                    return self.indice[modulo_resuelto]
            else:
                # Si el import apunta a la clase/modulo (ej: from x import TicketService -> "modulo.completo.TicketService")
                resto = ".".join(partes[1:])
                clave = f"{modulo_resuelto}.{resto}"
                if clave in self.indice:
                    return self.indice[clave]

        # 3. Intentar resolver en el mismo módulo actual (llamadas locales)
        if clase_contexto and len(partes) == 1:
            clave_local = f"{modulo_actual}.{clase_contexto}.{nombre_llamada}"
            if clave_local in self.indice:
                return self.indice[clave_local]
        elif len(partes) == 1:
            clave_local = f"{modulo_actual}.{nombre_llamada}"
            if clave_local in self.indice:
                return self.indice[clave_local]

        # 4. Fallback: búsqueda por coincidencia de sufijo ("Clase.metodo" o "metodo")
        if nombre_llamada in self.indice:
            return self.indice[nombre_llamada]

        return None

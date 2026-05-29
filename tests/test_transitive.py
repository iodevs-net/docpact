"""Tests unitarios para la detección de efectos transitivos e indexador de contratos.
"""

from __future__ import annotations

import ast
from pathlib import Path
import pytest

from docpact.config import DocpactConfig
from docpact.checker.contract_index import ContractIndex, ImportResolver
from docpact.checker.transitive_effects import check_transitive_effects
from docpact.parser.lexer import tokenizar
from docpact.parser.parser import parsear


def test_import_resolver(tmp_path):
    dir_soporte = tmp_path / "soporte"
    dir_soporte.mkdir()
    archivo_py = dir_soporte / "views.py"
    fuente = """
import os
from soporte.services.tickets import TicketService as TS
from .models import Ticket

def post():
    from soporte.services import registrar_evento_bitacora
    pass
"""
    archivo_py.write_text(fuente, encoding="utf-8")
    tree = ast.parse(fuente)

    resolver = ImportResolver(archivo_py, tmp_path)
    resolver.visit(tree)

    assert resolver.imports["os"] == "os"
    assert resolver.imports["TS"] == "soporte.services.tickets.TicketService"
    assert resolver.imports["Ticket"] == "soporte.models.Ticket"
    assert resolver.imports["registrar_evento_bitacora"] == "soporte.services.registrar_evento_bitacora"


def test_contract_index_build_and_lookup(tmp_path):
    # Creamos un archivo simulado con contratos
    dir_soporte = tmp_path / "soporte"
    dir_soporte.mkdir()
    archivo_services = dir_soporte / "services.py"

    fuente_services = """
def crear_ticket(nombre: str) -> None:
    \"\"\"Crea un ticket.
    CONTRATO:
    side_effects: db_write
    \"\"\"
    pass

class TicketService:
    def actualizar_ticket(self) -> None:
        \"\"\"Actualiza.
        CONTRATO:
        side_effects: db_write
        \"\"\"
        pass
"""
    archivo_services.write_text(fuente_services, encoding="utf-8")

    config = DocpactConfig()
    index = ContractIndex()
    index.build([archivo_services], config, project_root=tmp_path)

    # El módulo de services.py debe ser "soporte.services"
    # Verificar que el lookup resuelva adecuadamente
    imports = {
        "TS": "soporte.services.TicketService",
        "crear_ticket": "soporte.services.crear_ticket",
    }

    # Caso 1: llamada local directa resuelta por imports
    res_directo = index.lookup("crear_ticket", imports, "soporte.views")
    assert res_directo is not None
    assert res_directo.funcion == "crear_ticket"
    assert "db_write" in res_directo.side_effects

    # Caso 2: llamada calificada Clase.metodo resuelta por imports
    res_metodo = index.lookup("TS.actualizar_ticket", imports, "soporte.views")
    assert res_metodo is not None
    assert res_metodo.clase == "TicketService"
    assert res_metodo.funcion == "actualizar_ticket"
    assert "db_write" in res_metodo.side_effects


def test_transitive_effects_detection():
    # Simulamos el contrato de origen de 'post' que declara 'ninguno'
    doc_origen = """
    CONTRATO:
    side_effects: ninguno
    """
    tokens = tokenizar(doc_origen)
    contrato_origen, _ = parsear(tokens)

    # Creamos una función que llama a otra con efectos
    fuente_origen = """
def post():
    crear_ticket()
"""
    tree = ast.parse(fuente_origen)
    func_node = tree.body[0]

    # Simulamos un índice que tiene 'crear_ticket' con side_effects
    from dataclasses import dataclass
    @dataclass
    class MockContratoIdx:
        modulo: str
        clase: str | None
        funcion: str
        side_effects: list[str]
        archivo: str
        linea: int

    class MockIndex:
        def lookup(self, name, imports, modulo_actual, clase_contexto=None):
            if name == "crear_ticket":
                return MockContratoIdx(
                    modulo="soporte.services",
                    clase=None,
                    funcion="crear_ticket",
                    side_effects=["db_write"],
                    archivo="services.py",
                    linea=10,
                )
            return None

    index = MockIndex()
    imports = {"crear_ticket": "soporte.services.crear_ticket"}

    errores = check_transitive_effects(
        func_node,
        contrato_origen,
        imports,
        index,
        "post",
        "views.py",
        "soporte.views",
    )

    assert len(errores) == 1
    assert "declara side_effects: ninguno" in errores[0].mensaje
    assert "crear_ticket" in errores[0].mensaje

"""Tests de regresión para _validar_tenant_safe.

Bug conocido (jun-2026): el docstring dice que el default de `forbid` incluye
`.objects.all()` y `.objects.filter()`, pero el codigo solo default es
`["unfiltered_objects"]`. Resultado: codigo inseguro como `Ticket.objects.all()`
NO se detecta con el spec minimo.

Estos tests son RED: demuestran el gap. El fix esperado es agregar
`.objects.all()` y `.objects.filter()` al default `forbid` en
`src/docpact/checker/semantic_rn.py:462`.
"""
from __future__ import annotations

from docpact.checker.semantic_rn import validar_rn


def test_tenant_safe_detecta_objects_all_sin_filtro():
    """tenant_safe DEBE detectar Ticket.objects.all() (unfiltered query)."""
    codigo = """
def listar_todos(user):
    return Ticket.objects.all()
"""
    spec = {"type": "tenant_safe"}
    errores = validar_rn(codigo, "RN-TEST-1", spec, {})
    assert len(errores) > 0, (
        "BUG: tenant_safe no detecta .objects.all() sin filtro. "
        "Docstring dice default forbid incluye '.objects.all()' pero el codigo no."
    )


def test_tenant_safe_detecta_objects_filter_sin_para_usuario():
    """tenant_safe DEBE detectar .objects.filter() sin .para_usuario(user)."""
    codigo = """
def buscar_sin_filtro(user, estado):
    return Ticket.objects.filter(estado=estado)
"""
    spec = {"type": "tenant_safe"}
    errores = validar_rn(codigo, "RN-TEST-2", spec, {})
    assert len(errores) > 0, (
        "BUG: tenant_safe no detecta .objects.filter() sin .para_usuario()."
    )


def test_tenant_safe_pasa_con_para_usuario():
    """tenant_safe debe NO detectar codigo que SI usa .para_usuario(user)."""
    codigo = """
def listar_seguros(user):
    return Ticket.objects.para_usuario(user).all()
"""
    spec = {"type": "tenant_safe"}
    errores = validar_rn(codigo, "RN-TEST-3", spec, {})
    assert len(errores) == 0, (
        f"False positive: tenant_safe reporta {len(errores)} error(es) en codigo "
        f"que SI usa .para_usuario(user). Esperado 0."
    )


def test_tenant_safe_default_forbid_incluye_objects_all():
    """El default forbid deberia incluir .objects.all() (segun docstring)."""
    # Si el fix no se aplico, este test falla porque el default no incluye
    # el pattern. Probamos con codigo que claramente deberia ser detectado.
    codigo_minimo = "x = Ticket.objects.all()"
    spec = {"type": "tenant_safe"}  # sin forbid custom — usa default
    errores = validar_rn(codigo_minimo, "RN-TEST-4", spec, {})
    assert len(errores) > 0, (
        "BUG: con spec minimo (sin forbid custom), tenant_safe no detecta "
        "Ticket.objects.all(). El default deberia incluir este pattern."
    )

"""Priorización ponderada de reglas de negocio descubiertas.

Score = 0.35×riesgo + 0.25×cobertura + 0.25×criticidad + 0.15×recencia.
Zero deps beyond stdlib.
"""

from __future__ import annotations

import ast
import os
import time
from pathlib import Path

_RIESGO: dict[str, float] = {
    "security": 1.0, "negocio": 0.8, "permiso": 0.6,
    "auditoria": 0.4, "validacion": 0.3,
}

_VENTANA = 90 * 86_400  # 90 days in seconds


def _contar_funciones(p: Path) -> int:
    try:
        tree = ast.parse(p.read_text("utf-8", errors="replace"))
        return sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree))
    except (SyntaxError, OSError):
        return 1


def _tiene_tests(archivo: str, raiz: Path) -> bool:
    return (raiz / "tests" / f"test_{Path(archivo).stem}.py").exists()


def _score_recencia(p: Path) -> float:
    try:
        return max(0.0, 1.0 - (time.time() - os.path.getmtime(p)) / _VENTANA)
    except OSError:
        return 0.5


def priorizar_reglas(reglas: list[dict], raiz: Path | None = None) -> list[dict]:
    """Score and sort rules by weighted priority (descending).

    Returns each rule dict augmented with ``prioridad``, ``score_riesgo``,
    ``score_cobertura``, ``score_criticidad``, ``score_recencia``.
    """
    if not reglas:
        return []
    raiz = raiz or Path(".")
    funcs: dict[str, int] = {}
    for r in reglas:
        a = r.get("archivo", "")
        if a not in funcs:
            p = raiz / a if not Path(a).is_absolute() else Path(a)
            funcs[a] = _contar_funciones(p)
    mx = max(funcs.values()) if funcs else 1

    resultado = []
    for r in reglas:
        a = r.get("archivo", "")
        p = Path(a) if Path(a).is_absolute() else raiz / a
        sr = _RIESGO.get(r.get("tipo", ""), 0.3)
        sc = funcs.get(a, 1) / mx
        st = 0.7 if not _tiene_tests(a, raiz) else 0.3
        sm = _score_recencia(p)
        pr = 0.35 * sr + 0.25 * sc + 0.25 * st + 0.15 * sm
        resultado.append({
            **r,
            "prioridad": round(pr, 4),
            "score_riesgo": round(sr, 2),
            "score_cobertura": round(sc, 2),
            "score_criticidad": round(st, 2),
            "score_recencia": round(sm, 2),
        })
    resultado.sort(key=lambda x: x["prioridad"], reverse=True)
    return resultado

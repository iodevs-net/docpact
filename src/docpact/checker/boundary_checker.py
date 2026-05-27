"""Verificador de límites entre módulos.

Lee modules.toml y verifica que las dependencias declaradas en CONTRATOS
respeten las reglas de módulo (allowed/forbidden).
"""

from __future__ import annotations

from typing import NamedTuple


class BoundaryError(NamedTuple):
    """Error de límite entre módulos."""

    archivo: str
    funcion: str
    mensaje: str
    sugerencia: str = ""


def _detectar_modulo(archivo: str, modules_cfg: dict) -> str | None:
    """Detecta a qué módulo pertenece un archivo basado en su path."""
    path = archivo.replace("\\", "/")
    for module_name in modules_cfg:
        if f"/{module_name}/" in path:
            return module_name
    for module_name in modules_cfg:
        if path.startswith(module_name) or path.endswith(f"/{module_name}"):
            return module_name
    return None


def _normalizar(items: list[str]) -> list[str]:
    """Quita trailing slash de items para comparación."""
    return [i.rstrip("/") for i in items]


def check_boundary(
    resultados_archivos: list,
    modules_cfg: dict[str, dict],
) -> list[BoundaryError]:
    """Verifica que dependencias respeten módulos.

    Para cada función con dependencias, detecta su módulo y verifica
    que cada dependencia no esté en forbidden y esté en allowed.
    """
    errores: list[BoundaryError] = []

    for ra in resultados_archivos:
        archivo = getattr(ra, "archivo", "")
        if not archivo:
            continue
        modulo = _detectar_modulo(archivo, modules_cfg)
        if not modulo or modulo not in modules_cfg:
            continue
        reglas = modules_cfg[modulo]
        allowed = _normalizar(reglas.get("allowed", ["*"]))
        forbidden = _normalizar(reglas.get("forbidden", []))

        for rf in getattr(ra, "funciones", []):
            contrato = getattr(rf, "contrato", None)
            if not contrato or not getattr(contrato, "dependencias", None):
                continue
            for dep in contrato.dependencias:
                dep_ref = getattr(dep, "ref", None) if not isinstance(dep, str) else dep
                if not dep_ref:
                    continue
                dep_mod = _detectar_modulo(dep_ref, modules_cfg)
                if not dep_mod or dep_mod == modulo:
                    continue

                if dep_mod in forbidden:
                    errores.append(
                        BoundaryError(
                            archivo=archivo,
                            funcion=rf.nombre if hasattr(rf, "nombre") else "",
                            mensaje=f"'{rf.nombre}' en módulo '{modulo}' depende de '{dep_mod}' ({dep_ref}) — prohibido",
                            sugerencia=f"Mover la función a '{dep_mod}' o eliminar la dependencia",
                        )
                    )
                elif "*" not in allowed and dep_mod not in allowed:
                    errores.append(
                        BoundaryError(
                            archivo=archivo,
                            funcion=rf.nombre if hasattr(rf, "nombre") else "",
                            mensaje=f"'{rf.nombre}' en módulo '{modulo}' depende de '{dep_mod}' ({dep_ref}) — no permitido",
                            sugerencia=f"Agregar '{dep_mod}/' a allowed de '{modulo}' en modules.toml",
                        )
                    )

    return errores

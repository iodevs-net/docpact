"""Verificador de patrones RN — valida logica real en el codigo.

Lee la configuracion rn_patrones de docpact.toml y verifica que
cada RN-XXX tenga el patron esperado en el codigo.
Solo revisa RN-XXX fuera de docstrings (ignora CONTRATOS).

Esto evita falsos positivos en vistas/wrappers que declaran RN
en su CONTRATO pero delegan la implementacion a un service.

Ejemplo de config:
[docpact.rn_patrones]
"RN-008" = { patron = "RESTRINGIDO", archivos = ["clientes/services.py"] }
"RN-012" = { patron = "get_horas_consumidas", archivos = ["clientes/"] }
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple


class RNPatternError(NamedTuple):
    """Error de patron RN no encontrado."""

    funcion: str
    archivo: str
    linea: int
    mensaje: str
    sugerencia: str = ""


def _extraer_rns_codigo(source: str) -> list[tuple[str, int]]:
    """Extrae comentarios # RN-XXX fuera de docstrings solamente."""
    resultados: list[tuple[str, int]] = []
    lines = source.split("\n")
    dentro = False  # True si estamos dentro de un docstring triple

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Detectar apertura/cierre de docstring """ o '''
        for delim in ['"""', "'''"]:
            count = stripped.count(delim)
            if count > 0:
                # Si count es impar: abre o cierra. Si es par: inline o nada.
                if count % 2 == 1:
                    dentro = not dentro
                # Si count >= 2: apertura y cierre en misma línea (inline)
                # no cambia estado
                break
        else:
            # Solo buscar RN si no estamos dentro de docstring
            if not dentro:
                m = re.search(r"#\s*(RN-\w+)", line)
                if m:
                    resultados.append((m.group(1), i))

    return resultados


def _linea_tiene_patron(line: str, patron: str) -> bool:
    """Verifica si una linea contiene el patron (soporta multi-patron con |)."""
    for p in patron.split("|"):
        if p.strip() in line:
            return True
    return False


def verificar_rn_patrones(
    archivo: Path,
    fuente: str,
    rn_patrones_config: dict[str, dict[str, str]],
    line_offset: int = 1,
) -> list[RNPatternError]:
    """Verifica que cada RN tenga su patron esperado en el codigo."""
    errores: list[RNPatternError] = []
    rns_en_codigo = _extraer_rns_codigo(fuente)

    for rn_id, linea_local in rns_en_codigo:
        cfg = rn_patrones_config.get(rn_id)
        if not cfg:
            continue

        patron = cfg.get("patron", "")
        archivos_filtro = cfg.get("archivos", [])

        # Verificar filtro de archivos
        str_archivo = str(archivo)
        if archivos_filtro and not any(f in str_archivo for f in archivos_filtro):
            continue

        # Verificar que la linea marcada tenga el patron
        lineas = fuente.split("\n")
        if linea_local <= len(lineas):
            linea_contenido = lineas[linea_local - 1]
            if not _linea_tiene_patron(linea_contenido, patron):
                linea_abs = line_offset + linea_local - 1
                errores.append(
                    RNPatternError(
                        funcion="",
                        archivo=str(archivo),
                        linea=linea_abs,
                        mensaje=f"{rn_id} marcada pero no se detecto patron '{patron}' en linea {linea_abs}",
                        sugerencia=f"Mover # {rn_id} a una linea que contenga '{patron}'",
                    )
                )

    return errores

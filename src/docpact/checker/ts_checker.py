"""Verificación de archivos TypeScript/JSX.

Extraído de orchestrator.py para separar responsabilidades.
"""

from __future__ import annotations

import re
from pathlib import Path

from docpact.checker.models import (
    Hallazgo,
    ResultadoArchivo,
    ResultadoFuncion,
    _suprimir_hallazgos,
)
from docpact.checker.rn_test_checker import check_rn_tests
from docpact.checker.ts_sidefx import check_side_effects_ts
from docpact.config import DocpactConfig
from docpact.parser.ts_parser import extraer_contratos_ts


def _find_project_root(archivo: str) -> Path | None:
    """Busca la raiz del proyecto ascendiendo desde un archivo."""
    path = Path(archivo).resolve()
    for parent in [path] + list(path.parents):
        reg = parent / "docs" / "reglas-del-negocio" / "REGISTRO.md"
        if reg.exists():
            return parent
        if (parent / "pyproject.toml").exists() or (parent / "docpact.toml").exists():
            return parent
    return None


def check_file_ts(path: Path, config: DocpactConfig) -> ResultadoArchivo:
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
            resultado.funciones.append(
                ResultadoFuncion(
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
                )
            )
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
                hallazgos_ts.append(
                    Hallazgo(
                        tipo="warning",
                        campo="side_effects",
                        funcion=nombre,
                        archivo=str(path),
                        linea=linea_contrato,
                        mensaje=msg,
                    )
                )

            # ── 2. Dependencias ──
            deps = c.get("dependencias", [])
            if isinstance(deps, list):
                for dep in deps:
                    dep = dep.strip()
                    if not dep:
                        continue
                    if "::" in dep:
                        modulo_path, _simbolo = dep.split("::", 1)
                    else:
                        modulo_path = dep

                    # npm packages (@org/ prefix)
                    if modulo_path.startswith("@") and "/" in modulo_path:
                        continue

                    # Vite alias @/ (mapea a resources/js/ en ioDesk-3)
                    if modulo_path.startswith("@/"):
                        base_dir = path.parent
                        vite_base = base_dir
                        for p in [base_dir] + list(base_dir.parents):
                            if (p / "resources" / "js").is_dir():
                                vite_base = p / "resources" / "js"
                                break
                        ruta_rel = vite_base / modulo_path[2:]
                        for ext in (".ts", ".tsx", ".jsx"):
                            if ruta_rel.with_suffix(ext).exists():
                                break
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
                        hallazgos_ts.append(
                            Hallazgo(
                                tipo="warning",
                                campo="dependencias",
                                funcion=nombre,
                                archivo=str(path),
                                linea=linea_contrato,
                                mensaje=f"'{nombre}': dependencia '{dep}' — "
                                f"archivo '{modulo_path}' no encontrado",
                                sugerencia=f"Verifica la ruta (buscado desde {base_dir})",
                            )
                        )

            # ── 3. RN check ──
            rn_list = c.get("rn", [])
            if isinstance(rn_list, list):
                comentarios_ts: list[str] = []
                from_i = max(0, linea_contrato - 1)
                for l in lineas_fn[from_i:]:
                    stripped = l.strip()
                    if "RN-" in stripped or "Gotcha" in stripped:
                        comentarios_ts.append(stripped)
                ids_en_codigo = set()

                patron = re.compile(r"RN-[\w-]+|Gotcha #\d+")
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
                        hallazgos_ts.append(
                            Hallazgo(
                                tipo="warning",
                                campo="rn",
                                funcion=nombre,
                                archivo=str(path),
                                linea=linea_contrato,
                                mensaje=f"'{nombre}': RN '{rn_id}' declarada pero no encontrada "
                                f"como comentario en el código",
                                sugerencia=f"Agrega '// {rn_id}' en el lugar donde se implementa",
                            )
                        )

            # RN test checker para TS
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
                            hallazgos_ts.append(
                                Hallazgo(
                                    tipo="error",
                                    campo=e.campo,
                                    funcion=nombre,
                                    archivo=str(path),
                                    linea=linea_contrato,
                                    mensaje=e.mensaje,
                                    sugerencia=e.sugerencia,
                                )
                            )
            hallazgos_ts = _suprimir_hallazgos(hallazgos_ts, config)
            resultado.funciones.append(
                ResultadoFuncion(
                    nombre=nombre,
                    archivo=str(path),
                    linea=linea_contrato,
                    tiene_contrato=True,
                    hallazgos=hallazgos_ts,
                )
            )
    return resultado

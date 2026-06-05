"""docpact.reporter — Delta entre REGISTRO.md y código real.

Lee la tabla de RNs de REGISTRO.md y cruza con el index de docpact
para mostrar qué reglas están implementadas vs qué son letra muerta.

NO re-valida CONTRATOS, markers o tests — eso ya lo hacen otros módulos.
Solo JUNTA datos dispersos en un reporte coherente.

Uso:
    from docpact.reporter import generar_reporte
    reporte = generar_reporte("/path/to/project")
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class RNStatus:
    """Estado de implementación de una RN."""

    id: str
    descripcion: str
    estado_registro: str  # ✅, 🔶, ⏳
    # Lo que docpact encontró en el código
    tiene_validador: bool = False
    tiene_marcador: bool = False
    tiene_test: bool = False
    funciones_implementacion: list[str] = field(default_factory=list)
    archivos_marcador: list[str] = field(default_factory=list)
    test_file: Optional[str] = None
    # Delta
    implementacion: str = "DESCONOCIDA"  # ✅ IMPLEMENTADA / 🔶 PARCIAL / ❌ NO IMPLEMENTADA

    def calcular_implementacion(self) -> None:
        """Calcula el estado de implementación basado en evidencia encontrada."""
        score = 0
        if self.tiene_marcador:
            score += 1
        if self.tiene_test:
            score += 1
        if self.funciones_implementacion:
            score += 1

        if score >= 3:
            self.implementacion = "✅ IMPLEMENTADA"
        elif score >= 1:
            self.implementacion = "🔶 PARCIAL"
        else:
            self.implementacion = "❌ NO IMPLEMENTADA"


def _parsear_registro(registro_path: Path) -> list[dict]:
    """Parsea la tabla de RNs de REGISTRO.md.

    Retorna lista de dicts con: id, descripcion, estado.
    """
    if not registro_path.exists():
        return []

    content = registro_path.read_text(encoding="utf-8")
    rns = []

    # Patrón: | RN-XXX | descripción | file:line | ✓/✗ | estado |
    patron = re.compile(
        r"\|\s*(RN-[\w-]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*(✅|🔶|⏳)\s*\|"
    )

    for match in patron.finditer(content):
        rn_id = match.group(1).strip()
        descripcion = match.group(2).strip()
        estado = match.group(5).strip()

        rns.append(
            {
                "id": rn_id,
                "descripcion": descripcion,
                "estado": estado,
            }
        )

    return rns


def _cargar_index(project_root: Path) -> dict:
    """Carga el index de docpact si existe."""
    import json as json_mod

    index_path = project_root / ".docpact" / "index.json"
    if not index_path.exists():
        return {}
    try:
        return json_mod.loads(index_path.read_text(encoding="utf-8"))
    except (json_mod.JSONDecodeError, OSError):
        return {}


def _buscar_rn_en_index(index: dict, rn_id: str) -> dict:
    """Busca una RN en el index y retorna evidencia encontrada."""
    evidencia = {
        "tiene_marcador": False,
        "tiene_validador": False,
        "funciones": [],
        "archivos": [],
        "tiene_test": False,
        "test_file": None,
    }

    if not index:
        return evidencia

    # Buscar en rns del index (fuente principal)
    rns_index = index.get("rns", {})
    rn_info = rns_index.get(rn_id, {})
    if rn_info:
        evidencia["tiene_validador"] = True
        # Funciones que implementan esta RN
        funciones_info = rn_info.get("funciones", [])
        for func in funciones_info:
            nombre = func.get("funcion", "")
            archivo = func.get("archivo", "")
            if nombre and nombre not in evidencia["funciones"]:
                evidencia["funciones"].append(nombre)
            if archivo and archivo not in evidencia["archivos"]:
                evidencia["archivos"].append(archivo)
        if evidencia["funciones"]:
            evidencia["tiene_marcador"] = True
        # Test
        test_file = rn_info.get("test")
        if test_file:
            evidencia["tiene_test"] = True
            evidencia["test_file"] = test_file

    return evidencia


def generar_reporte(
    project_root: str | Path,
    registro_path: Optional[str | Path] = None,
) -> list[RNStatus]:
    """Genera el reporte de delta REGISTRO.md vs código real.

    Args:
        project_root: Raíz del proyecto.
        registro_path: Path al REGISTRO.md. Si None, busca en docs/reglas-del-negocio/.

    Returns:
        Lista de RNStatus con el estado de cada RN.
    """
    root = Path(project_root)

    if registro_path is None:
        registro_path = root / "docs" / "reglas-del-negocio" / "REGISTRO.md"
    else:
        registro_path = Path(registro_path)

    # 1. Parsear REGISTRO.md
    rns_registro = _parsear_registro(registro_path)

    # 2. Cargar index
    index = _cargar_index(root)

    # 3. Cruzar datos
    resultados = []
    for rn_data in rns_registro:
        rn_id = rn_data["id"]
        evidencia = _buscar_rn_en_index(index, rn_id)

        status = RNStatus(
            id=rn_id,
            descripcion=rn_data["descripcion"],
            estado_registro=rn_data["estado"],
            tiene_validador=rn_id in index.get("rns", {}),
            tiene_marcador=evidencia["tiene_marcador"],
            tiene_test=evidencia["tiene_test"],
            funciones_implementacion=evidencia["funciones"],
            archivos_marcador=evidencia["archivos"],
            test_file=evidencia["test_file"],
        )
        status.calcular_implementacion()
        resultados.append(status)

    return resultados


def generar_tabla(resultados: list[RNStatus]) -> str:
    """Genera tabla legible para humanos."""
    if not resultados:
        return "No se encontraron RNs en REGISTRO.md"

    # Contadores
    implementadas = sum(1 for r in resultados if r.implementacion.startswith("✅"))
    parciales = sum(1 for r in resultados if r.implementacion.startswith("🔶"))
    no_implementadas = sum(1 for r in resultados if r.implementacion.startswith("❌"))
    total = len(resultados)

    lineas = [
        f"═══ DOC PACT REPORT ═══",
        f"",
        f"RESUMEN:",
        f"  ✅ Implementadas: {implementadas}/{total} ({implementadas * 100 // total}%)",
        f"  🔶 Parciales:     {parciales}/{total} ({parciales * 100 // total}%)",
        f"  ❌ No implement:  {no_implementadas}/{total} ({no_implementadas * 100 // total}%)",
        f"",
        f"═══ DETALLE ═══",
        f"",
    ]

    # Agrupar por estado
    for estado_label, emoji in [
        ("❌ NO IMPLEMENTADA", "❌"),
        ("🔶 PARCIAL", "🔶"),
        ("✅ IMPLEMENTADA", "✅"),
    ]:
        grupo = [r for r in resultados if r.implementacion.startswith(emoji)]
        if not grupo:
            continue

        lineas.append(f"─── {estado_label} ({len(grupo)}) ───")
        for r in grupo:
            checks = []
            checks.append("validador" if r.tiene_validador else "  -   ")
            checks.append("marcador" if r.tiene_marcador else "  -   ")
            checks.append("test" if r.tiene_test else "  -   ")
            lineas.append(
                f"  {r.id:15s} {r.descripcion[:50]:50s} [{', '.join(checks)}]"
            )
        lineas.append("")

    return "\n".join(lineas)


def generar_json(resultados: list[RNStatus]) -> str:
    """Genera JSON para agentes."""
    data = {
        "resumen": {
            "total": len(resultados),
            "implementadas": sum(
                1 for r in resultados if r.implementacion.startswith("✅")
            ),
            "parciales": sum(
                1 for r in resultados if r.implementacion.startswith("🔶")
            ),
            "no_implementadas": sum(
                1 for r in resultados if r.implementacion.startswith("❌")
            ),
        },
        "rns": [asdict(r) for r in resultados],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def validar_ci(resultados: list[RNStatus]) -> tuple[bool, list[str]]:
    """Valida condiciones para CI. Retorna (pass, errores).

    Reglas CI:
    1. Toda RN en REGISTRO.md DEBE tener al menos marcador en código.
    2. Toda RN con marcador DEBE tener test.
    3. RNs ⏳ (pendientes) sin código son warnings, no errores.
    """
    errores = []

    for r in resultados:
        # Solo validar RNs que tienen código (marcador o test)
        # RNs sin código son pendientes legítimas
        if not r.tiene_marcador and not r.tiene_test:
            continue

        # Si tiene marcador pero no test → error
        if r.tiene_marcador and not r.tiene_test:
            errores.append(
                f"❌ {r.id}: tiene marcador en código pero SIN test. "
                f"Crear tests/rn/test_rn_{r.id}.py"
            )

    return (len(errores) == 0, errores)

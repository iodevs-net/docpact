"""Guard — validación de cambios contra CONTRATOs antes de aplicar.

Modo DRY: reutiliza el orchestrator existente.
Modo SOLID: una responsabilidad — validar cambios.
Modo LEAN: mínimo código nuevo, reutiliza infraestructura.
Modo KISS: if/else simple, sin abstracciones innecesarias.
Modo Bus Factor 0: docstrings claros, nombres descriptivos, tests completos.

Flujo:
1. Agente propone modificar un archivo (path + diff)
2. Guard extrae las funciones afectadas
3. Verifica cada función contra su CONTRATO
4. Si hay violación → rechaza con explicación
5. Si es seguro → permite
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ValidationResult:
    """Resultado de la validación de un cambio."""
    allowed: bool
    violations: list[Violation]
    message: str


@dataclass(frozen=True)
class Violation:
    """Una violación detectada en el cambio."""
    funcion: str
    tipo: str  # "side_effect", "rn", "signature"
    mensaje: str
    sugerencia: str


def validar_cambio(
    archivo: str | Path,
    diff: str,
    project_root: str | Path | None = None,
) -> ValidationResult:
    """Valida un diff contra los CONTRATOs del archivo.

    Args:
        archivo: Path del archivo a modificar
        diff: El diff o código nuevo
        project_root: Raíz del proyecto (default: directorio del archivo)

    Returns:
        ValidationResult con allowed=True/False y violaciones detectadas
    """
    archivo = Path(archivo)
    if project_root is None:
        project_root = archivo.parent

    # 1. Extraer funciones afectadas del diff
    funciones_afectadas = _extraer_funciones_del_diff(diff)

    if not funciones_afectadas:
        return ValidationResult(
            allowed=True,
            violations=[],
            message="No se detectaron funciones afectadas"
        )

    # 2. Parsear el archivo actual para obtener CONTRATOs
    try:
        contenido = archivo.read_text(encoding="utf-8")
        contratos = _extraer_contratos(contenido)
    except (FileNotFoundError, SyntaxError, UnicodeDecodeError):
        return ValidationResult(
            allowed=True,
            violations=[],
            message="No se pudo parsear el archivo — permitiendo cambio"
        )

    # 3. Verificar cada función afectada
    violations: list[Violation] = []
    for funcion in funciones_afectadas:
        contrato = contratos.get(funcion)
        if contrato is None:
            continue  # Sin contrato = sin restricciones

        # Verificar side effects
        se_violations = _verificar_side_effects(funcion, diff, contrato)
        violations.extend(se_violations)

        # Verificar RNs
        rn_violations = _verificar_rns(funcion, diff, contrato)
        violations.extend(rn_violations)

    if violations:
        mensaje = _generar_mensaje_rechazo(violations)
        return ValidationResult(
            allowed=False,
            violations=violations,
            message=mensaje,
        )

    return ValidationResult(
        allowed=True,
        violations=[],
        message=f"Cambio seguro en {len(funciones_afectadas)} función(es)"
    )


def _extraer_funciones_del_diff(diff: str) -> list[str]:
    """Extrae nombres de funciones del diff o código nuevo."""
    funciones: list[str] = []

    # Buscar def/async def en el diff
    patron = re.compile(r"(?:async\s+)?def\s+(\w+)\s*\(")
    for match in patron.finditer(diff):
        funciones.append(match.group(1))

    return list(set(funciones))


def _extraer_contratos(contenido: str) -> dict[str, dict]:
    """Extrae CONTRATOs del código fuente."""
    contratos: dict[str, dict] = {}

    try:
        tree = ast.parse(contenido)
    except SyntaxError:
        return contratos

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        docstring = ast.get_docstring(node, clean=False) or ""
        if "CONTRATO" not in docstring.upper():
            continue

        contrato = _parsear_contrato_basico(docstring)
        if contrato:
            contratos[node.name] = contrato

    return contratos


def _parsear_contrato_basico(docstring: str) -> Optional[dict]:
    """Parsea un CONTRATO de forma básica desde el docstring."""
    resultado: dict = {}

    # Buscar side_effects
    se_match = re.search(r"side_effects[:\s]*(.+?)(?:\n\s*\n|\n\s*(?:rn|input|output|borde|dependencias):|\Z)", docstring, re.DOTALL | re.IGNORECASE)
    if se_match:
        se_text = se_match.group(1)
        efectos = re.findall(r"-\s*(.+?)(?:\n|$)", se_text)
        resultado["side_effects"] = [e.strip() for e in efectos if e.strip()]

    # Buscar RNs
    rn_matches = re.findall(r"RN-[\w-]+", docstring)
    if rn_matches:
        resultado["rns"] = rn_matches

    return resultado if resultado else None


def _verificar_side_effects(
    funcion: str,
    diff: str,
    contrato: dict,
) -> list[Violation]:
    """Verifica que el diff no viole side effects declarados."""
    violations: list[Violation] = []
    efectos_declarados = contrato.get("side_effects", [])

    if not efectos_declarados:
        return violations

    # Patrones de side effects prohibidos
    patrones_prohibidos = {
        "db_write": [r"\.save\(\)", r"\.create\(", r"\.update\(", r"\.delete\(", r"\.bulk_create\("],
        "email": [r"send_mail", r"EmailMessage", r"smtplib"],
        "disk_write": [r"open\(.+[\"']w", r"\.write\(", r"os\.remove"],
    }

    for efecto in efectos_declarados:
        efecto_lower = efecto.lower()
        for categoria, patrones in patrones_prohibidos.items():
            if any(p in efecto_lower for p in ["db", "database", "save", "create", "update", "delete"]):
                if categoria == "db_write":
                    for patron in patrones:
                        if re.search(patron, diff):
                            violations.append(Violation(
                                funcion=funcion,
                                tipo="side_effect",
                                mensaje=f"El cambio usa {patron} pero el CONTRATO declara '{efecto}'",
                                sugerencia=f"Si necesitas escribir a DB, actualiza el side_effects del CONTRATO",
                            ))

    return violations


def _verificar_rns(
    funcion: str,
    diff: str,
    contrato: dict,
) -> list[Violation]:
    """Verifica que el diff no viole RNs declaradas."""
    violations: list[Violation] = []
    rns = contrato.get("rns", [])

    if not rns:
        return violations

    # Verificar que las RNs sigan presentes en el diff
    for rn in rns:
        if rn not in diff and rn not in str(contrato):
            violations.append(Violation(
                funcion=funcion,
                tipo="rn",
                mensaje=f"El cambio elimina o modifica código relacionado con {rn}",
                sugerencia=f"Asegúrate de que {rn} siga implementada correctamente",
            ))

    return violations


def _generar_mensaje_rechazo(violations: list[Violation]) -> str:
    """Genera un mensaje claro de por qué el cambio fue rechazado."""
    lineas = [
        "CAMBIO RECHAZADO por violación de CONTRATO:",
        "",
    ]

    for v in violations:
        icono = {"side_effect": "⚡", "rn": "📋", "signature": "📝"}.get(v.tipo, "❌")
        lineas.append(f"  {icono} {v.funcion}: {v.mensaje}")
        if v.sugerencia:
            lineas.append(f"     💡 {v.sugerencia}")

    lineas.append("")
    lineas.append("Corrige las violaciones antes de aplicar el cambio.")

    return "\n".join(lineas)

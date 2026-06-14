"""Suggest new rules from violation/code patterns; score health; flag deprecations.
Zero dependencies beyond stdlib.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

_VIOLATION_THRESHOLD = 3
_CODE_THRESHOLD = 5


@dataclass(frozen=True)
class RuleSuggestion:
    tipo: str
    titulo: str
    razon: str
    confianza: str   # "alta" | "media" | "baja"
    funciones: list[str] = field(default_factory=list)
    ocurrencias: int = 0


@dataclass
class RuleHealth:
    rule_id: str
    score: float          # 0.0-1.0
    violation_rate: float
    test_coverage: float
    age_days: float


def suggest_from_violations(violations: list) -> list[RuleSuggestion]:
    """Suggest a rule when the same (tipo, mensaje stem) appears >=3 times."""
    if not violations:
        return []
    buckets: dict[tuple[str, str], list] = {}
    for v in violations:
        tipo = getattr(v, "tipo", "")
        stem = getattr(v, "mensaje", "").split(":")[0].strip()
        buckets.setdefault((tipo, stem), []).append(v)
    out = []
    for (tipo, stem), group in buckets.items():
        if len(group) < _VIOLATION_THRESHOLD:
            continue
        funcs = sorted({getattr(v, "funcion", "?") for v in group})
        out.append(RuleSuggestion(
            tipo=tipo, titulo=f"Patron frecuente: {stem}",
            razon=f"{len(group)} violaciones del mismo tipo detectadas",
            confianza="alta" if len(group) >= _VIOLATION_THRESHOLD * 2 else "media",
            funciones=funcs, ocurrencias=len(group),
        ))
    out.sort(key=lambda s: s.ocurrencias, reverse=True)
    return out


def suggest_from_code(patterns: dict[str, list[str]]) -> list[RuleSuggestion]:
    """Suggest a rule when >=5 functions share the same pattern."""
    out = []
    for label, funcs in patterns.items():
        if len(funcs) < _CODE_THRESHOLD:
            continue
        out.append(RuleSuggestion(
            tipo="negocio", titulo=f"Regla implicita: {label}",
            razon=f"{len(funcs)} funciones implementan el mismo comportamiento",
            confianza="alta" if len(funcs) >= _CODE_THRESHOLD * 2 else "media",
            funciones=sorted(funcs), ocurrencias=len(funcs),
        ))
    out.sort(key=lambda s: s.ocurrencias, reverse=True)
    return out


def calculate_rule_health(
    rule_id: str, *, violation_count: int = 0, total_checks: int = 0,
    has_test: bool = False, created_ts: float | None = None,
) -> RuleHealth:
    """Score = 0.40*violation_rate + 0.35*test_coverage + 0.25*age."""
    vr = max(0.0, 1.0 - violation_count / total_checks * 5) if total_checks else 1.0
    tc = 1.0 if has_test else 0.0
    if created_ts is not None:
        age = max(0.0, (time.time() - created_ts) / 86_400)
        age_s = max(0.0, 1.0 - age / 90)
    else:
        age, age_s = 0.0, 0.5
    return RuleHealth(
        rule_id=rule_id, score=round(0.40 * vr + 0.35 * tc + 0.25 * age_s, 4),
        violation_rate=round(vr, 4), test_coverage=round(tc, 4),
        age_days=round(age, 1),
    )


def deprecation_candidates(rules: dict[str, float], *, days: int = 90) -> list[str]:
    """Rule IDs with zero violations in *days* (ts=0 = never violated)."""
    cutoff = time.time() - days * 86_400
    return sorted(rid for rid, ts in rules.items() if ts <= cutoff)

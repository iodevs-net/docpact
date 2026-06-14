"""3-phase rule deduplication: exact hash → near-duplicate → semantic clustering.

Phase 1: Hash-based exact dedup on (titulo + evidencia).
Phase 2: FastEmbed cosine similarity > 0.85 (near-duplicate removal).
Phase 3: Semantic clustering at threshold 0.70 — keep the highest-confidence
         rule per cluster, merge evidence from the rest.

Designed to run after rule_discovery.escanear_proyecto().
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from docpact.index import _cosine_similarity
from docpact.checker.rule_discovery import ReglaDescubierta

# Confidence string → numeric for comparison.
_CONFIANZA_SCORE: dict[str, float] = {"alta": 1.0, "media": 0.6, "baja": 0.3}

# Tunables
_NEAR_DUP_THRESHOLD = 0.85
_SEMANTIC_CLUSTER_THRESHOLD = 0.70


@dataclass
class MergeInfo:
    """Records what was merged into a surviving rule."""

    kept: ReglaDescubierta
    merged_from: list[ReglaDescubierta] = field(default_factory=list)


@dataclass
class DedupResult:
    """Output of the 3-phase dedup pipeline."""

    rules: list[ReglaDescubierta]
    merges: list[MergeInfo]
    stats: dict[str, int]


def _hash_rule(r: ReglaDescubierta) -> str:
    """Stable hash of a rule's semantic content."""
    blob = f"{r.titulo}|{r.evidencia}".encode()
    return hashlib.sha256(blob).hexdigest()


def _confidence(r: ReglaDescubierta) -> float:
    return _CONFIANZA_SCORE.get(r.confianza.lower(), 0.3)


def _embed_texts(
    texts: list[str], embedder: Any
) -> list[list[float]]:
    """Batch-embed texts via FastEmbed. Returns list of float vectors."""
    raw = list(embedder.embed(texts))
    return [[float(x) for x in v] for v in raw]


# ── Phases ───────────────────────────────────────────────────────────────


def _phase_exact(rules: list[ReglaDescubierta]) -> tuple[
    list[ReglaDescubierta], list[MergeInfo],
]:
    """Phase 1: drop rules whose (titulo, evidencia) hash is identical."""
    seen: dict[str, ReglaDescubierta] = {}
    merges: list[MergeInfo] = []
    for r in rules:
        h = _hash_rule(r)
        if h in seen:
            # Same exact content — merge into earlier copy.
            merges.append(MergeInfo(kept=seen[h], merged_from=[r]))
        else:
            seen[h] = r
    return list(seen.values()), merges


def _phase_near_dup(
    rules: list[ReglaDescubierta],
    embedder: Any,
) -> tuple[list[ReglaDescubierta], list[MergeInfo]]:
    """Phase 2: drop near-duplicates (cosine > 0.85).

    Greedy: keep the first (highest-confidence) rule in each near-dup pair.
    """
    if len(rules) < 2:
        return rules, []

    vectors = _embed_texts(
        [f"{r.titulo} {r.evidencia}" for r in rules], embedder
    )

    # Greedy forward scan: mark indices to drop.
    drop: set[int] = set()
    merge_map: dict[int, list[ReglaDescubierta]] = {}  # kept_idx → dropped rules

    for i in range(len(rules)):
        if i in drop:
            continue
        for j in range(i + 1, len(rules)):
            if j in drop:
                continue
            sim = _cosine_similarity(vectors[i], vectors[j])
            if sim >= _NEAR_DUP_THRESHOLD:
                # Keep whichever has higher confidence; tie → earlier.
                if _confidence(rules[j]) > _confidence(rules[i]):
                    drop.add(i)
                    merge_map.setdefault(j, []).append(rules[i])
                    break  # i is gone, stop inner loop
                drop.add(j)
                merge_map.setdefault(i, []).append(rules[j])

    kept = [r for idx, r in enumerate(rules) if idx not in drop]
    merges = [
        MergeInfo(kept=rules[ki], merged_from=list(v))
        for ki, v in merge_map.items()
        if ki not in drop
    ]
    return kept, merges


def _phase_semantic(
    rules: list[ReglaDescubierta],
    embedder: Any,
) -> tuple[list[ReglaDescubierta], list[MergeInfo]]:
    """Phase 3: cluster remaining rules by cosine >= 0.70.

    Simple union-find: for every pair above threshold, group together.
    Per cluster, keep the rule with highest confidence; merge the rest.
    """
    n = len(rules)
    if n < 2:
        return rules, []

    vectors = _embed_texts(
        [f"{r.titulo} {r.evidencia}" for r in rules], embedder
    )

    # Union-Find
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if find(i) == find(j):
                continue
            if _cosine_similarity(vectors[i], vectors[j]) >= _SEMANTIC_CLUSTER_THRESHOLD:
                union(i, j)

    # Group by cluster root.
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    kept: list[ReglaDescubierta] = []
    merges: list[MergeInfo] = []

    for members in clusters.values():
        if len(members) == 1:
            kept.append(rules[members[0]])
            continue
        # Pick best by confidence (tie → first occurrence).
        best_idx = max(members, key=lambda idx: _confidence(rules[idx]))
        rest = [rules[idx] for idx in members if idx != best_idx]
        kept.append(rules[best_idx])
        merges.append(MergeInfo(kept=rules[best_idx], merged_from=rest))

    return kept, merges


# ── Public API ───────────────────────────────────────────────────────────


def deduplicate_rules(
    rules: list[ReglaDescubierta],
    embedder: Any | None = None,
) -> DedupResult:
    """Run the 3-phase dedup pipeline on discovered rules.

    Args:
        rules: Output of rule_discovery.escanear_proyecto().
        embedder: FastEmbed TextEmbedding instance (from mcp_server._embedder).
                  If None, only Phase 1 (exact hash) runs.

    Returns:
        DedupResult with deduplicated rules, merge info, and stats.
    """
    if not rules:
        return DedupResult(rules=[], merges=[], stats={"input": 0, "phase1": 0, "phase2": 0, "phase3": 0, "output": 0})

    # Phase 1 — always runs.
    after_p1, merges_p1 = _phase_exact(rules)

    # Phases 2 & 3 — need embedder.
    after_p2, after_p3 = after_p1, after_p1
    merges_p2: list[MergeInfo] = []
    merges_p3: list[MergeInfo] = []

    if embedder is not None:
        after_p2, merges_p2 = _phase_near_dup(after_p1, embedder)
        after_p3, merges_p3 = _phase_semantic(after_p2, embedder)
    else:
        after_p3 = after_p2

    all_merges = merges_p1 + merges_p2 + merges_p3
    return DedupResult(
        rules=after_p3,
        merges=all_merges,
        stats={
            "input": len(rules),
            "phase1_exact": len(rules) - len(after_p1),
            "phase2_near_dup": len(after_p1) - len(after_p2),
            "phase3_semantic": len(after_p2) - len(after_p3),
            "output": len(after_p3),
        },
    )

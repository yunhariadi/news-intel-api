"""source.py — Source activity / influence trend (Layer A).

The cross-source *diversity* dimension of `trending.py` doesn't apply when the
target itself is a source (its distinct-origin count is always 1), so source
trending gets a dedicated scorer — but built from the **same primitives**
(`recency_decay`, `burst_z`, `scale_score`, the shared constants) so behavior is
consistent and bounded.

A source trends when it surges in *original* reporting:
- recency-weighted article volume, log-compressed so a single dump can't
  dominate;
- multiplied by an **originality** factor (fraction of its articles that are the
  resolved origin, not carried wire copy) — a pure carrier that only reposts
  ANTARA scores at half weight. This is the anti-syndication ethos applied to
  sources: original journalism ranks above rebroadcasting (SPEC §4.7).
- plus a clamped Poisson burst on its article count vs its own baseline.

Pure: ages and baseline are computed by the worker against a fixed `now`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from packages.ranking.trending import (
    BURST_COEF,
    MIN_MENTIONS,
    REFERENCE_SCALE,
    burst_z,
    half_life_for_window,
    recency_decay,
    scale_score,
)

# How much a pure carrier (originality 0) is damped vs a fully original source.
_ORIGINALITY_FLOOR: float = 0.5


@dataclass(frozen=True)
class SourceWindow:
    source_id: str
    source_name: str
    article_ages_hours: Sequence[float]  # ages of this source's articles in window
    original_count: int                   # of those, how many resolved to THIS origin
    baseline_mean: float = 0.0            # mean article count over comparable windows


@dataclass(frozen=True)
class SourceScore:
    source_id: str
    source_name: str
    raw_score: float
    normalized_score: float
    weighted_volume: float
    article_count: int
    originality: float
    burst_z: float
    eligible: bool
    components: Mapping[str, float] = field(default_factory=dict)


def originality(original_count: int, article_count: int) -> float:
    """Fraction of a source's window articles that are its own origin, in [0, 1]."""
    if article_count <= 0:
        return 0.0
    return max(0.0, min(original_count / article_count, 1.0))


def score_source(
    sw: SourceWindow, window: str, reference_scale: float = REFERENCE_SCALE
) -> SourceScore:
    """Score one source's activity. Pure: same inputs -> same output."""
    half_life = half_life_for_window(window)
    article_count = len(sw.article_ages_hours)
    decayed = sum(recency_decay(age, half_life) for age in sw.article_ages_hours)
    volume = math.log1p(decayed)

    orig = originality(sw.original_count, article_count)
    originality_factor = _ORIGINALITY_FLOOR + (1.0 - _ORIGINALITY_FLOOR) * orig
    burst = burst_z(article_count, sw.baseline_mean)

    base = volume * originality_factor
    raw = base + BURST_COEF * burst

    return SourceScore(
        source_id=sw.source_id,
        source_name=sw.source_name,
        raw_score=raw,
        normalized_score=scale_score(raw, reference_scale),
        weighted_volume=volume,
        article_count=article_count,
        originality=round(orig, 4),
        burst_z=burst,
        eligible=article_count >= MIN_MENTIONS,
        components={
            "base": base,
            "volume": volume,
            "originality_factor": originality_factor,
            "burst_z": burst,
        },
    )


def rank_sources(
    sources: Sequence[SourceWindow],
    window: str,
    limit: int = 20,
    reference_scale: float = REFERENCE_SCALE,
    include_ineligible: bool = False,
) -> list[SourceScore]:
    """Score, filter ineligible, sort by raw_score desc (tie-break source_id)."""
    if limit < 0:
        raise ValueError("limit must be >= 0")
    scored = [score_source(s, window, reference_scale) for s in sources]
    if not include_ineligible:
        scored = [s for s in scored if s.eligible]
    scored.sort(key=lambda s: (-s.raw_score, s.source_id))
    return scored[:limit]

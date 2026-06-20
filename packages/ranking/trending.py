"""
trending.py — Reference trending engine for news-intel-api (Layer A).

This module is a deterministic, dependency-free, pure-function reference
implementation of the trending score. It is meant to live at
`packages/ranking/trending.py` and to be pinned by `test_trending.py` as a CI
gate, exactly the way v8_pricing.py gates the maker bot.

WHY THIS EXISTS
---------------
The spec's master formula (§12) is:

    trend_score = mention_count
                  * source_diversity
                  * recency_decay
                  * growth_rate
                  * entity_importance
                  * event_cluster_strength

That formula has four defects this module fixes:

1.  COLD-START EXPLOSION. growth_rate = current / max(prev, 1) sends brand-new
    or rare items to the top of the board on a near-zero denominator. Here,
    "burst" is a SMOOTHED, CLAMPED, ADDITIVE bonus (Poisson-style standardized
    residual), never an unbounded multiplier. A cold-start item can only trend
    if its *base evidence* (diversity-weighted volume) is also strong.

2.  TIME DOUBLE-COUNTED. The spec multiplies a window mention_count by an
    aggregate recency_decay — counting time twice. Here, recency is applied
    PER ARTICLE and summed; there is no second time term.

3.  TYPE CONFUSION. entity_importance has no meaning for a *topic* trend, yet
    §12 puts it in the universal product (and contradicts §15). Here there is
    one typed function; per-target `importance` carries entity_importance for
    actors, incident_weight for regions, and 1.0 for topics. Per-mention
    role/quote weighting rides on `Mention.weight_multiplier`.

4.  SYNDICATION-BLIND DIVERSITY. The spec counts URLs/sources naively, so one
    ANTARA wire story republished across 30 carriers reads as "30 sources" and
    dominates. Here, diversity, volume AND burst are all computed over *distinct
    original sources*: volume is log-compressed PER original source and burst is
    a residual on the distinct-origin count, so 30 copies of one wire contribute
    far less than 8 genuinely independent reports and can never fake a spike.

OUTPUT IS BOUNDED AND STABLE. raw_score is mapped to a 0..100 normalized_score
against a fixed REFERENCE_SCALE (meant to be overridden by a rolling P95 of raw
scores), so webhook thresholds like `min_score: 50` (§18) are stable over time
instead of drifting as corpus volume grows.

All functions here are pure: no I/O, no clocks, no globals mutated. `age_hours`
is computed by the caller against a single fixed "now"; pass it in.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Calibration constants. These are the knobs. Change them deliberately; every
# change should be justified by the test suite and (later) the trending
# regression set. They are NOT magic numbers buried in functions.
# ---------------------------------------------------------------------------

# Recency half-life (hours) per requested window. A mention's weight halves
# every half_life hours. Short windows decay fast; long windows decay slowly.
HALF_LIVES: Mapping[str, float] = {
    "1h": 1.0,
    "3h": 2.0,
    "6h": 3.0,
    "12h": 5.0,
    "24h": 8.0,
    "7d": 48.0,
    "30d": 120.0,
}

# Diversity saturates at this many distinct original sources. Beyond it, more
# sources stop adding score — "covered by everyone" is already maxed out.
SOURCE_CAP: int = 20

# How much the diversity bonus can lift the base. base *= (1 + DIVERSITY_COEF*d)
DIVERSITY_COEF: float = 1.0

# Burst is an additive bonus on top of base evidence, never a multiplier.
BURST_COEF: float = 0.8       # raw += BURST_COEF * burst_z
BURST_CAP: float = 5.0        # burst_z is clamped to [0, BURST_CAP]
SIGMA_SMOOTH: float = 1.0     # Laplace term under the sqrt; kills /0 on cold start

# Eligibility floor. To "trend" is to have spread, so a single-original-source
# story (pure syndication or a lone outlet) is NOT trending by definition.
MIN_MENTIONS: int = 3
MIN_DISTINCT_SOURCES: int = 2

# raw_score that maps to normalized 100. Override per-call with a rolling P95 of
# observed raw scores to keep absolute thresholds stable as volume grows.
REFERENCE_SCALE: float = 12.0


class TrendType(str, Enum):
    TOPIC = "topic"
    ACTOR = "actor"
    REGION = "region"


@dataclass(frozen=True)
class Mention:
    """One mention of a target in one article, already syndication-resolved.

    original_source is the *origin* of the content, not the carrier URL. If an
    ANTARA wire story is republished by Tribun, Kompas and detik, all three
    mentions carry original_source="antara". Collapsing carriers -> origin
    happens upstream in the content_cluster step; by the time we score, the
    syndication question is already answered.
    """

    original_source: str
    age_hours: float
    # role_weight * quote_weight for actors; 1.0 for topics/regions. Kept on the
    # mention so the core scorer stays a single typed function.
    weight_multiplier: float = 1.0


@dataclass(frozen=True)
class TargetWindow:
    """All mentions of one target within the scoring window, plus its baseline."""

    target_id: str
    target_type: TrendType
    target_name: str
    mentions: Sequence[Mention]
    # Mean DISTINCT-ORIGIN count over comparable prior windows (the burst
    # baseline). Distinct origins, never carrier copies — so syndication can't
    # manufacture a burst. The worker must compute this on the same basis that
    # score_target measures `observed` (see burst section in score_target).
    baseline_mean: float = 0.0
    # entity_importance (actor, 1.0..2.0) / incident_weight (region) / 1.0 (topic)
    importance: float = 1.0


@dataclass(frozen=True)
class TrendScore:
    target_id: str
    target_type: TrendType
    target_name: str
    raw_score: float
    normalized_score: float  # 0..100, stable against REFERENCE_SCALE
    weighted_mentions: float
    distinct_sources: int
    burst_z: float
    eligible: bool
    components: Mapping[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Primitives (each individually testable)
# ---------------------------------------------------------------------------

def half_life_for_window(window: str) -> float:
    try:
        return HALF_LIVES[window]
    except KeyError:
        raise ValueError(
            f"unsupported window {window!r}; expected one of {sorted(HALF_LIVES)}"
        ) from None


def recency_decay(age_hours: float, half_life: float) -> float:
    """Exponential decay in (0, 1]. decay(0) == 1; older -> smaller."""
    if age_hours < 0:
        raise ValueError(f"age_hours must be >= 0, got {age_hours}")
    if half_life <= 0:
        raise ValueError(f"half_life must be > 0, got {half_life}")
    return math.exp(-math.log(2.0) * age_hours / half_life)


def compressed_volume(
    mentions: Sequence[Mention], half_life: float
) -> tuple[float, dict[str, float]]:
    """Recency-weighted volume with per-original-source diminishing returns.

    For each original source we sum its decayed, weighted mentions, then take
    log1p of that per-source sum, then sum across sources. The per-source log
    is what stops 30 copies of one wire from out-weighing 8 independent
    reports: log1p(30) ~= 3.43 while 8 * log1p(1) ~= 5.55.
    """
    per_source: dict[str, float] = defaultdict(float)
    for m in mentions:
        per_source[m.original_source] += (
            recency_decay(m.age_hours, half_life) * m.weight_multiplier
        )
    volume = sum(math.log1p(w) for w in per_source.values())
    return volume, dict(per_source)


def diversity_bonus(distinct_sources: int) -> float:
    """0 at one source, rising and saturating at SOURCE_CAP. Bounded to [0, 1]."""
    if distinct_sources <= 0:
        return 0.0
    return min(math.log1p(distinct_sources) / math.log1p(SOURCE_CAP), 1.0)


def burst_z(observed_count: int, baseline_mean: float) -> float:
    """Poisson-style standardized residual, clamped to [0, BURST_CAP].

    For a Poisson process variance ~= mean, so the natural scale is
    sqrt(expected). The SIGMA_SMOOTH term removes the divide-by-zero on a
    zero baseline; the clamp removes the cold-start explosion entirely.

    `observed_count` is a syndication-resolved count (distinct origins), not raw
    carrier copies — the caller (score_target) is responsible for passing the
    origin-based count so reposts cannot fake a spike.
    """
    expected = max(baseline_mean, 0.0)
    denom = math.sqrt(expected + SIGMA_SMOOTH)
    z = (observed_count - expected) / denom
    return max(0.0, min(z, BURST_CAP))


def is_eligible(distinct_sources: int, mention_count: int) -> bool:
    """A target trends only if it has both volume and cross-source spread."""
    return (
        mention_count >= MIN_MENTIONS
        and distinct_sources >= MIN_DISTINCT_SOURCES
    )


def scale_score(raw_score: float, reference_scale: float = REFERENCE_SCALE) -> float:
    """Map raw_score to a stable 0..100. Pass a rolling P95 as reference_scale
    in production so thresholds don't drift with corpus volume."""
    if reference_scale <= 0:
        raise ValueError("reference_scale must be > 0")
    return max(0.0, min(100.0, raw_score / reference_scale * 100.0))


# ---------------------------------------------------------------------------
# Composite scorer + ranking
# ---------------------------------------------------------------------------

def score_target(
    tw: TargetWindow, window: str, reference_scale: float = REFERENCE_SCALE
) -> TrendScore:
    """Score one target. Pure: same inputs -> same output."""
    half_life = half_life_for_window(window)
    volume, per_source = compressed_volume(tw.mentions, half_life)
    distinct = len(per_source)
    mention_count = len(tw.mentions)

    div = diversity_bonus(distinct)
    # Burst is measured over DISTINCT ORIGINS, never raw carrier copies: 30
    # reposts of one wire story are 1 origin and cannot manufacture a spike.
    # This keeps burst consistent with compressed_volume's per-origin dampening
    # and with Prime Directive #1 (diversity counts origins, never carriers).
    # Genuine per-origin depth is already rewarded in `volume`, not here.
    burst = burst_z(distinct, tw.baseline_mean)

    base = volume * (1.0 + DIVERSITY_COEF * div) * tw.importance
    raw = base + BURST_COEF * burst

    return TrendScore(
        target_id=tw.target_id,
        target_type=tw.target_type,
        target_name=tw.target_name,
        raw_score=raw,
        normalized_score=scale_score(raw, reference_scale),
        weighted_mentions=volume,
        distinct_sources=distinct,
        burst_z=burst,
        eligible=is_eligible(distinct, mention_count),
        components={
            "base": base,
            "volume": volume,
            "diversity_bonus": div,
            "importance": tw.importance,
            "burst_z": burst,
        },
    )


def rank_trends(
    targets: Sequence[TargetWindow],
    window: str,
    limit: int = 20,
    reference_scale: float = REFERENCE_SCALE,
    include_ineligible: bool = False,
) -> list[TrendScore]:
    """Score, filter ineligible, sort by raw_score desc, return top `limit`.

    Tie-break is by target_id so output ordering is fully deterministic.
    """
    if limit < 0:
        raise ValueError("limit must be >= 0")
    scored = [score_target(t, window, reference_scale) for t in targets]
    if not include_ineligible:
        scored = [s for s in scored if s.eligible]
    scored.sort(key=lambda s: (-s.raw_score, s.target_id))
    return scored[:limit]

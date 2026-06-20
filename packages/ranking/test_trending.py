"""
test_trending.py — CI gate for the trending engine.

These tests pin the behavioural invariants that the spec's §12 formula got
wrong. If a scoring change makes the engine rank a syndicated wire dump above
genuine independent coverage, or lets a cold-start item top the board on a
near-zero baseline, a test here must go red.

Run: pytest -q test_trending.py
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise

import pytest

from packages.ranking.trending import (
    BURST_CAP,
    MIN_DISTINCT_SOURCES,
    REFERENCE_SCALE,
    Mention,
    TargetWindow,
    TrendType,
    burst_z,
    compressed_volume,
    diversity_bonus,
    half_life_for_window,
    is_eligible,
    rank_trends,
    recency_decay,
    scale_score,
    score_target,
)

W = "24h"


def _mentions(
    sources: Sequence[str],
    per_source: int = 1,
    age_hours: float = 0.0,
    weight: float = 1.0,
) -> list[Mention]:
    """Build `per_source` mentions for each source in `sources`."""
    out = []
    for s in sources:
        for _ in range(per_source):
            out.append(Mention(original_source=s, age_hours=age_hours, weight_multiplier=weight))
    return out


def _topic(
    tid: str,
    mentions: Sequence[Mention],
    baseline: float = 0.0,
    importance: float = 1.0,
) -> TargetWindow:
    return TargetWindow(
        target_id=tid,
        target_type=TrendType.TOPIC,
        target_name=tid,
        mentions=mentions,
        baseline_mean=baseline,
        importance=importance,
    )


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------

def test_recency_decay_bounds_and_monotonic() -> None:
    hl = 8.0
    assert recency_decay(0.0, hl) == pytest.approx(1.0)
    assert recency_decay(hl, hl) == pytest.approx(0.5)  # one half-life -> half
    seq = [recency_decay(a, hl) for a in (0, 1, 4, 8, 24)]
    assert all(earlier > later for earlier, later in pairwise(seq))
    assert all(0.0 < v <= 1.0 for v in seq)


def test_recency_decay_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        recency_decay(-1.0, 8.0)
    with pytest.raises(ValueError):
        recency_decay(1.0, 0.0)


def test_half_life_lookup() -> None:
    assert half_life_for_window("1h") == 1.0
    assert half_life_for_window("30d") == 120.0
    with pytest.raises(ValueError):
        half_life_for_window("90d")


def test_compressed_volume_dampens_syndication() -> None:
    # 30 copies from ONE origin vs 8 reports from EIGHT origins.
    hl = half_life_for_window(W)
    wire_vol, wire_src = compressed_volume(_mentions(["antara"], per_source=30), hl)
    indep_vol, indep_src = compressed_volume(_mentions([f"s{i}" for i in range(8)]), hl)
    assert len(wire_src) == 1
    assert len(indep_src) == 8
    # 8 independent reports out-weigh 30 syndicated copies on volume alone.
    assert indep_vol > wire_vol


def test_diversity_bonus_bounded_and_monotonic() -> None:
    assert diversity_bonus(0) == 0.0
    assert diversity_bonus(1) < diversity_bonus(4) < diversity_bonus(12)
    assert 0.0 <= diversity_bonus(8) <= 1.0
    # saturates: far beyond the cap it is clamped to 1.0
    assert diversity_bonus(1000) == 1.0


def test_burst_zero_baseline_does_not_explode() -> None:
    # This is the cold-start bug. A huge observation against a zero baseline
    # must stay finite and clamped, NOT divide by ~0.
    z = burst_z(observed_count=500, baseline_mean=0.0)
    assert z == pytest.approx(BURST_CAP)
    assert math.isfinite(z)


def test_burst_steady_is_small() -> None:
    z = burst_z(observed_count=60, baseline_mean=58.0)
    assert 0.0 <= z < 1.0


def test_burst_acceleration_is_clamped() -> None:
    z = burst_z(observed_count=60, baseline_mean=20.0)
    assert z == pytest.approx(BURST_CAP)  # big jump, capped


def test_scale_score_stable_and_bounded() -> None:
    assert scale_score(0.0) == 0.0
    assert scale_score(REFERENCE_SCALE) == pytest.approx(100.0)
    assert scale_score(2 * REFERENCE_SCALE) == 100.0  # clamped
    assert scale_score(REFERENCE_SCALE / 2) == pytest.approx(50.0)


# --------------------------------------------------------------------------
# Eligibility
# --------------------------------------------------------------------------

def test_single_source_is_ineligible() -> None:
    # A lone-origin story (pure syndication or one outlet) is not "trending".
    assert is_eligible(distinct_sources=1, mention_count=30) is False


def test_thin_volume_is_ineligible() -> None:
    assert is_eligible(distinct_sources=5, mention_count=2) is False


def test_spread_and_volume_is_eligible() -> None:
    assert is_eligible(distinct_sources=MIN_DISTINCT_SOURCES, mention_count=3) is True


# --------------------------------------------------------------------------
# The headline invariants
# --------------------------------------------------------------------------

def test_independent_coverage_outranks_wire_dump() -> None:
    """INVARIANT: 8 independent sources beat 30 copies of one wire story."""
    wire = _topic("wire", _mentions(["antara"], per_source=30), baseline=5.0)
    indep = _topic("indep", _mentions([f"s{i}" for i in range(8)]), baseline=5.0)

    s_wire = score_target(wire, W)
    s_indep = score_target(indep, W)

    # The wire dump is a single origin -> filtered out of trending entirely.
    assert s_wire.eligible is False
    assert s_indep.eligible is True
    # And even ignoring eligibility, independent coverage scores higher.
    assert s_indep.raw_score > s_wire.raw_score

    ranked = rank_trends([wire, indep], W)
    assert [s.target_id for s in ranked] == ["indep"]


def test_burst_ignores_carrier_inflation() -> None:
    """INVARIANT: syndication cannot manufacture a burst. Carrier copies from
    the same origins are irrelevant to burst — only distinct-origin spread is."""
    # Same 2 origins and same baseline; one window has 2 carrier copies, the
    # other 40. Burst must be identical (and zero, since 2 origins == baseline).
    few = _topic("few", _mentions(["a", "b"], per_source=1), baseline=2.0)
    flood = _topic("flood", _mentions(["a", "b"], per_source=20), baseline=2.0)
    s_few = score_target(few, W)
    s_flood = score_target(flood, W)
    assert s_few.burst_z == s_flood.burst_z  # carrier count does not move burst
    assert s_flood.burst_z == 0.0            # 2 origins vs baseline 2 -> no spike
    # Per-origin depth is still rewarded, but in volume — never in burst.
    assert s_flood.weighted_mentions > s_few.weighted_mentions


def test_burst_fires_on_distinct_origin_acceleration() -> None:
    """A genuine spike — more *distinct origins* than baseline — does burst."""
    surge = _topic("surge", _mentions([f"s{i}" for i in range(8)]), baseline=2.0)
    s = score_target(surge, W)
    assert s.burst_z > 0.0


def test_diversity_beats_raw_volume_among_eligible() -> None:
    """8 sources x 1 mention beats 2 sources x 15 mentions, despite 8 < 30."""
    many_few = _topic("two_loud", _mentions(["a", "b"], per_source=15), baseline=30.0)
    few_many = _topic("eight_indep", _mentions([f"s{i}" for i in range(8)]), baseline=8.0)

    s_many_few = score_target(many_few, W)
    s_few_many = score_target(few_many, W)
    assert s_many_few.eligible and s_few_many.eligible
    assert s_few_many.raw_score > s_many_few.raw_score


def test_cold_start_thin_topic_is_not_number_one() -> None:
    """A brand-new thin topic must not outrank established strong coverage,
    even with an infinite growth ratio."""
    cold = _topic("cold", _mentions(["a", "b"], per_source=2), baseline=0.0)      # 4 mentions
    established = _topic(
        "established", _mentions([f"s{i}" for i in range(8)], per_source=3), baseline=20.0
    )  # 24 mentions, 8 sources
    ranked = rank_trends([cold, established], W)
    assert ranked[0].target_id == "established"


def test_acceleration_beats_steady_at_equal_volume() -> None:
    """Same volume and diversity; the one accelerating off a low baseline wins."""
    base_mentions = _mentions([f"s{i}" for i in range(8)])  # 8 sources, 8 mentions
    accel = _topic("accel", base_mentions, baseline=2.0)
    steady = _topic("steady", base_mentions, baseline=8.0)
    s_accel = score_target(accel, W)
    s_steady = score_target(steady, W)
    assert s_accel.weighted_mentions == pytest.approx(s_steady.weighted_mentions)
    assert s_accel.raw_score > s_steady.raw_score


def test_recent_mentions_outweigh_old_ones() -> None:
    fresh = _topic("fresh", _mentions([f"s{i}" for i in range(4)], age_hours=0.0), baseline=4.0)
    stale = _topic("stale", _mentions([f"s{i}" for i in range(4)], age_hours=48.0), baseline=4.0)
    assert score_target(fresh, W).raw_score > score_target(stale, W).raw_score


def test_actor_role_and_quote_weighting_lifts_score() -> None:
    # weight_multiplier carries role_weight * quote_weight for actors.
    loud = TargetWindow(
        "spoke", TrendType.ACTOR, "spoke",
        _mentions(["a", "b"], per_source=2, weight=1.5 * 1.2),  # speaker + direct quote
        baseline_mean=4.0,
    )
    quiet = TargetWindow(
        "named", TrendType.ACTOR, "named",
        _mentions(["a", "b"], per_source=2, weight=1.0),        # merely mentioned
        baseline_mean=4.0,
    )
    assert score_target(loud, W).raw_score > score_target(quiet, W).raw_score


def test_entity_importance_scales_actor_score() -> None:
    minister = TargetWindow(
        "minister", TrendType.ACTOR, "minister",
        _mentions(["a", "b", "c"]), baseline_mean=3.0, importance=2.0,
    )
    backbencher = TargetWindow(
        "backbencher", TrendType.ACTOR, "backbencher",
        _mentions(["a", "b", "c"]), baseline_mean=3.0, importance=1.0,
    )
    assert score_target(minister, W).raw_score > score_target(backbencher, W).raw_score


# --------------------------------------------------------------------------
# Determinism + ranking mechanics
# --------------------------------------------------------------------------

def test_determinism_same_input_same_output() -> None:
    t = _topic("t", _mentions([f"s{i}" for i in range(5)]), baseline=3.0)
    a = score_target(t, W)
    b = score_target(t, W)
    assert a == b


def test_rank_filters_ineligible_and_respects_limit() -> None:
    targets = [
        _topic("wire", _mentions(["antara"], per_source=40), baseline=5.0),  # ineligible
        _topic("a", _mentions([f"s{i}" for i in range(6)]), baseline=4.0),
        _topic("b", _mentions([f"s{i}" for i in range(4)]), baseline=2.0),
        _topic("c", _mentions([f"s{i}" for i in range(3)]), baseline=2.0),
    ]
    ranked = rank_trends(targets, W, limit=2)
    ids = [s.target_id for s in ranked]
    assert "wire" not in ids
    assert len(ranked) == 2
    # sorted by raw_score descending
    assert ranked[0].raw_score >= ranked[1].raw_score


def test_rank_tie_break_is_stable_by_id() -> None:
    # Two identical-shape targets -> identical raw_score -> stable id order.
    m = _mentions([f"s{i}" for i in range(4)])
    t1 = _topic("zzz", m, baseline=4.0)
    t2 = _topic("aaa", m, baseline=4.0)
    ranked = rank_trends([t1, t2], W)
    assert [s.target_id for s in ranked] == ["aaa", "zzz"]


def test_normalized_score_is_in_range() -> None:
    t = _topic("t", _mentions([f"s{i}" for i in range(10)], per_source=3), baseline=10.0)
    s = score_target(t, W)
    assert 0.0 <= s.normalized_score <= 100.0

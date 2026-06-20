"""Gate for source.py — originality-weighted, bounded, syndication-aware."""

from __future__ import annotations

from packages.ranking.source import (
    SourceWindow,
    originality,
    rank_sources,
    score_source,
)


def _sw(sid: str, n_articles: int, n_original: int, baseline: float = 0.0) -> SourceWindow:
    return SourceWindow(
        source_id=sid,
        source_name=sid.upper(),
        article_ages_hours=tuple(1.0 for _ in range(n_articles)),
        original_count=n_original,
        baseline_mean=baseline,
    )


def test_originality_fraction() -> None:
    assert originality(0, 0) == 0.0
    assert originality(3, 6) == 0.5
    assert originality(10, 5) == 1.0  # clamped


def test_original_source_beats_pure_carrier() -> None:
    original = score_source(_sw("orig", 6, 6), "24h")
    carrier = score_source(_sw("carr", 6, 0), "24h")
    assert original.raw_score > carrier.raw_score  # anti-syndication
    assert original.originality == 1.0
    assert carrier.originality == 0.0


def test_normalized_bounded_0_100() -> None:
    s = score_source(_sw("x", 50, 50), "24h")
    assert 0.0 <= s.normalized_score <= 100.0


def test_eligibility_floor() -> None:
    assert score_source(_sw("x", 2, 2), "24h").eligible is False  # < MIN_MENTIONS
    assert score_source(_sw("x", 3, 3), "24h").eligible is True


def test_burst_lifts_surging_source() -> None:
    calm = score_source(_sw("x", 6, 6, baseline=6.0), "24h")
    surge = score_source(_sw("x", 6, 6, baseline=0.0), "24h")
    assert surge.raw_score > calm.raw_score


def test_rank_sources_sorted_and_filtered() -> None:
    sources = [_sw("a", 6, 6), _sw("b", 3, 0), _sw("c", 1, 1)]
    ranked = rank_sources(sources, "24h")
    assert [s.source_id for s in ranked] == ["a", "b"]  # c ineligible (1 < 3)
    assert ranked[0].raw_score >= ranked[1].raw_score


def test_deterministic() -> None:
    a = rank_sources([_sw("a", 5, 3), _sw("b", 5, 5)], "24h")
    b = rank_sources([_sw("a", 5, 3), _sw("b", 5, 5)], "24h")
    assert a == b

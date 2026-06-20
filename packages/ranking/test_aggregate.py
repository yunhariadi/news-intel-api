"""Gate for aggregate.py — window building, origin counting, P95 reference scale."""

from __future__ import annotations

from packages.ranking.aggregate import (
    ActorRef,
    ArticleForTrending,
    RegionRef,
    TopicRef,
    build_actor_windows,
    build_region_windows,
    build_source_windows,
    build_topic_windows,
    reference_scale_p95,
)
from packages.ranking.trending import TrendType, rank_trends


def _article(
    aid: str,
    origin: str,
    *,
    source_id: str = "",
    is_origin: bool = True,
    age: float = 1.0,
    topics: tuple[str, ...] = (),
    actors: tuple[ActorRef, ...] = (),
    regions: tuple[RegionRef, ...] = (),
) -> ArticleForTrending:
    return ArticleForTrending(
        article_id=aid,
        original_source=origin,
        source_id=source_id or origin,
        source_name=(source_id or origin).upper(),
        is_origin=is_origin,
        age_hours=age,
        topics=tuple(TopicRef(t) for t in topics),
        actors=actors,
        regions=regions,
    )


def test_topic_windows_group_by_topic() -> None:
    arts = [
        _article("1", "antara", topics=("moneter",)),
        _article("2", "kompas", topics=("moneter", "fiskal")),
    ]
    wins = {w.target_id: w for w in build_topic_windows(arts)}
    assert set(wins) == {"moneter", "fiskal"}
    assert wins["moneter"].target_type is TrendType.TOPIC
    assert len(wins["moneter"].mentions) == 2
    assert wins["moneter"].importance == 1.0


def test_topic_mentions_carry_origin_not_carrier() -> None:
    # Same wire story carried by 3 outlets -> 3 mentions, but all origin=antara.
    arts = [
        _article("1", "antara", source_id="antara", topics=("korupsi",)),
        _article("2", "antara", source_id="tribun", is_origin=False, topics=("korupsi",)),
        _article("3", "antara", source_id="kompas", is_origin=False, topics=("korupsi",)),
    ]
    (win,) = build_topic_windows(arts)
    assert {m.original_source for m in win.mentions} == {"antara"}  # one origin
    # Scored: distinct_sources collapses to 1 -> ineligible (Prime Directive #1).
    scored = rank_trends([win], "24h", include_ineligible=True)
    assert scored[0].distinct_sources == 1
    assert scored[0].eligible is False


def test_actor_windows_importance_and_weight() -> None:
    arts = [
        _article("1", "antara",
                 actors=(ActorRef("org_bi", "Bank Indonesia", "REGULATOR", is_quoted=True),)),
        _article("2", "kompas",
                 actors=(ActorRef("org_bi", "Bank Indonesia", "REGULATOR"),)),
    ]
    (win,) = build_actor_windows(arts)
    assert win.target_type is TrendType.ACTOR
    assert win.importance == 1.5  # regulator
    # Quoted mention weighs more than the plain one.
    weights = sorted(m.weight_multiplier for m in win.mentions)
    assert weights[0] == 1.0 and weights[1] > 1.0


def test_region_windows_importance_from_type() -> None:
    arts = [
        _article("1", "antara", regions=(RegionRef("reg_surabaya", "Surabaya", "city", 0.8),)),
        _article("2", "kompas", regions=(RegionRef("reg_surabaya", "Surabaya", "city", 0.6),)),
    ]
    (win,) = build_region_windows(arts)
    assert win.importance > 1.0  # city > country
    assert all(m.weight_multiplier > 0 for m in win.mentions)


def test_source_windows_count_origin() -> None:
    arts = [
        _article("1", "antara", source_id="antara", is_origin=True),
        _article("2", "antara", source_id="tribun", is_origin=False),
        _article("3", "tribun", source_id="tribun", is_origin=True),
    ]
    wins = {w.source_id: w for w in build_source_windows(arts)}
    assert wins["tribun"].original_count == 1  # 1 of its 2 articles is its own origin
    assert len(wins["tribun"].article_ages_hours) == 2
    assert wins["antara"].original_count == 1


def test_reference_scale_p95_fallback_until_history() -> None:
    assert reference_scale_p95([], fallback=12.0) == 12.0
    assert reference_scale_p95([5.0], fallback=12.0) == 12.0  # need >= 2


def test_reference_scale_p95_uses_high_percentile() -> None:
    scores = [float(i) for i in range(1, 101)]  # 1..100
    p95 = reference_scale_p95(scores, fallback=1.0)
    assert 94.0 <= p95 <= 96.0

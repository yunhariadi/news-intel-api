"""Gate for event_clusterer.py — incremental assignment, stable IDs, views."""

from __future__ import annotations

from packages.clustering.event_clusterer import (
    ArticleForEvent,
    EventClusterer,
    event_sources,
    event_timeline,
)


def _a(
    aid: str,
    hours: float,
    *,
    origin: str = "antara",
    actors: tuple[str, ...] = (),
    regions: tuple[str, ...] = (),
    topics: tuple[str, ...] = (),
    title: str = "",
) -> ArticleForEvent:
    return ArticleForEvent(
        article_id=aid,
        first_seen_hours=hours,
        original_source=origin,
        actor_keys=frozenset(actors),
        region_ids=frozenset(regions),
        topics=frozenset(topics),
        title=title or aid,
    )


def test_shared_actor_within_window_joins_one_event() -> None:
    c = EventClusterer()
    e1 = c.assign(_a("a1", 0.0, actors=("kpk",), topics=("korupsi",)))
    e2 = c.assign(_a("a2", 6.0, actors=("kpk",), topics=("korupsi",)))
    assert e1 == e2
    assert len(c.events[e1].members) == 2


def test_distinct_actors_open_distinct_events() -> None:
    c = EventClusterer()
    e1 = c.assign(_a("a1", 0.0, actors=("kpk",), topics=("korupsi",)))
    e2 = c.assign(_a("a2", 1.0, actors=("bi",), topics=("moneter",)))
    assert e1 != e2


def test_same_actor_outside_window_opens_new_event() -> None:
    c = EventClusterer()
    e1 = c.assign(_a("a1", 0.0, actors=("kpk",), topics=("korupsi",)))
    e2 = c.assign(_a("a2", 100.0, actors=("kpk",), topics=("korupsi",)))  # > 48h
    assert e1 != e2


def test_region_plus_topic_joins_without_shared_actor() -> None:
    c = EventClusterer()
    e1 = c.assign(_a("a1", 0.0, regions=("reg_medan",), topics=("bencana",)))
    e2 = c.assign(_a("a2", 5.0, regions=("reg_medan",), topics=("bencana",)))
    assert e1 == e2


def test_shared_region_but_different_topic_does_not_join() -> None:
    c = EventClusterer()
    e1 = c.assign(_a("a1", 0.0, regions=("reg_dki",), topics=("banjir_x",)))
    e2 = c.assign(_a("a2", 1.0, regions=("reg_dki",), topics=("politik",)))
    assert e1 != e2  # same place, unrelated stories


def test_event_id_derived_from_seed_article() -> None:
    c = EventClusterer()
    eid = c.assign(_a("seed1", 0.0, actors=("x",)))
    assert eid == "evt_seed1"


# --- the stability gate ----------------------------------------------------

def test_ids_stable_across_reruns() -> None:
    arts = [
        _a("a1", 0.0, actors=("kpk",), topics=("korupsi",)),
        _a("a2", 2.0, actors=("kpk",), topics=("korupsi",)),
        _a("a3", 4.0, actors=("bi",), topics=("moneter",)),
    ]
    first = EventClusterer().assign_all(arts)
    second = EventClusterer().assign_all(arts)
    assert first == second  # deterministic, reproducible IDs


def test_reassigning_existing_article_is_noop() -> None:
    c = EventClusterer()
    art = _a("a1", 0.0, actors=("kpk",))
    first = c.assign(art)
    snapshot = len(c.events[first].members)
    again = c.assign(art)
    assert again == first
    assert len(c.events[first].members) == snapshot  # not double-counted


def test_existing_assignments_unchanged_by_new_article() -> None:
    c = EventClusterer()
    e1 = c.assign(_a("a1", 0.0, actors=("kpk",), topics=("korupsi",)))
    e2 = c.assign(_a("a2", 2.0, actors=("kpk",), topics=("korupsi",)))
    # A later unrelated article must not move a1/a2.
    c.assign(_a("a3", 3.0, actors=("bi",), topics=("moneter",)))
    assert c.event_of("a1") == e1 == e2


# --- merge / split ---------------------------------------------------------

def test_merge_is_logged_and_survivor_is_stable() -> None:
    c = EventClusterer()
    e1 = c.assign(_a("a1", 0.0, actors=("kpk",)))
    e2 = c.assign(_a("b1", 1.0, actors=("polri",)))
    op = c.merge(e1, e2)
    survivor = min(e1, e2)
    assert op.kind == "merge"
    assert op.surviving_event_id == survivor
    assert c.event_of("a1") == survivor and c.event_of("b1") == survivor
    assert c.log[-1].surviving_event_id == survivor


def test_split_creates_new_stable_event() -> None:
    c = EventClusterer()
    e = c.assign(_a("a1", 0.0, actors=("kpk",), topics=("korupsi",)))
    c.assign(_a("a2", 2.0, actors=("kpk",), topics=("korupsi",)))
    op = c.split(e, ["a2"])
    assert op.kind == "split"
    assert c.event_of("a2") == "evt_a2"
    assert c.event_of("a1") == e
    assert c.event_of("a2") != e


# --- views -----------------------------------------------------------------

def test_timeline_is_chronological_by_first_seen() -> None:
    c = EventClusterer()
    e = c.assign(_a("a2", 5.0, actors=("kpk",), title="later"))
    c.assign(_a("a1", 1.0, actors=("kpk",), title="earlier"))
    tl = event_timeline(c.events[e])
    assert [t.article_id for t in tl] == ["a1", "a2"]  # sorted by first_seen


def test_source_comparison_counts_origins_not_carriers() -> None:
    c = EventClusterer()
    # Same wire origin carried 3x + one independent origin.
    e = c.assign(_a("w1", 0.0, origin="antara", actors=("kpk",)))
    c.assign(_a("w2", 1.0, origin="antara", actors=("kpk",)))
    c.assign(_a("w3", 2.0, origin="antara", actors=("kpk",)))
    c.assign(_a("k1", 3.0, origin="kompas", actors=("kpk",)))
    comp = event_sources(c.events[e])
    assert comp.distinct_origins == 2          # antara + kompas, not 4
    assert comp.first_source == "antara"
    assert comp.most_active_source == "antara"  # 3 articles

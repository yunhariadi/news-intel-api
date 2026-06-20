"""events.py — App-level event service (join stores → clusterer → serialize).

Projects enriched articles into `ArticleForEvent`, assigns the ones not yet
clustered (incremental — existing events keep their stable IDs), and serializes
events/timelines/source-comparisons for the API. Event time is rendered from
`first_seen_by_us` (trusted), never the feed's claimed `published_at`
(DESIGN.md §7); source comparison counts distinct ORIGINS (Prime Directive #1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from packages.clustering.event_clusterer import (
    ArticleForEvent,
    Event,
    EventClusterer,
    event_sources,
    event_timeline,
)
from packages.db.enrichment import EnrichmentStore
from packages.db.store import Store

from apps.sources import SOURCE_REGISTRY

_SOURCE_NAMES: dict[str, str] = {rs.config.source_id: rs.config.name for rs in SOURCE_REGISTRY}


def _source_name(source_id: str) -> str:
    return _SOURCE_NAMES.get(source_id, source_id)


def _iso(first_seen_hours: float) -> str:
    return datetime.fromtimestamp(first_seen_hours * 3600.0, tz=UTC).isoformat()


def project_articles_for_event(
    store: Store, enrichment_store: EnrichmentStore
) -> list[ArticleForEvent]:
    """Project every enriched, origin-resolved article into the event shape."""
    by_id = {a.article_id: a for a in store.all_articles()}
    out: list[ArticleForEvent] = []
    for enr in enrichment_store.all_enrichments():
        art = by_id.get(enr.article_id)
        if art is None:
            continue
        out.append(
            ArticleForEvent(
                article_id=art.article_id,
                first_seen_hours=art.first_seen_hours,
                original_source=art.original_source_id or art.source_id,
                actor_keys=frozenset(
                    a.entity_id or f"key:{a.canonical_key}" for a in enr.actors
                ),
                region_ids=frozenset(r.region_id for r in enr.regions),
                topics=frozenset(t.topic for t in enr.topics),
                title=art.title,
            )
        )
    return out


def assign_events(
    clusterer: EventClusterer, store: Store, enrichment_store: EnrichmentStore
) -> None:
    """Assign any not-yet-clustered articles (incremental, stable IDs)."""
    pending = [
        a
        for a in project_articles_for_event(store, enrichment_store)
        if clusterer.event_of(a.article_id) is None
    ]
    clusterer.assign_all(pending)


# --- serializers -----------------------------------------------------------


def event_summary(ev: Event) -> dict[str, Any]:
    comp = event_sources(ev)
    # Main topic = most frequent topic across members (deterministic tie-break).
    topic_counts: dict[str, int] = {}
    for m in ev.members:
        for t in m.topics:
            topic_counts[t] = topic_counts.get(t, 0) + 1
    main_topic = (
        max(topic_counts.items(), key=lambda kv: (kv[1], kv[0]))[0] if topic_counts else None
    )
    return {
        "id": ev.event_id,
        "title": ev.representative_title,
        "status": ev.status,
        "article_count": len(ev.members),
        "source_count": comp.distinct_origins,   # origins, not carriers
        "main_topic": main_topic,
        "first_seen": _iso(ev.first_seen_hours),
        "last_seen": _iso(ev.last_seen_hours),
    }


def event_timeline_view(ev: Event) -> list[dict[str, Any]]:
    return [
        {
            "article_id": e.article_id,
            "time": _iso(e.first_seen_hours),    # first_seen_by_us (trusted)
            "title": e.title,
            "source": _source_name(e.origin_source),
        }
        for e in event_timeline(ev)
    ]


def event_sources_view(ev: Event) -> dict[str, Any]:
    comp = event_sources(ev)
    return {
        "distinct_origins": comp.distinct_origins,   # diversity over origins
        "first_source": _source_name(comp.first_source) if comp.first_source else None,
        "most_active_source": (
            _source_name(comp.most_active_source) if comp.most_active_source else None
        ),
        "origin_breakdown": [
            {"source": _source_name(sid), "article_count": n}
            for sid, n in sorted(comp.origin_article_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


def list_events(clusterer: EventClusterer, limit: int = 20) -> list[dict[str, Any]]:
    """Active events, most-recently-active first."""
    events = [ev for ev in clusterer.events.values() if ev.status != "merged"]
    events.sort(key=lambda ev: (-ev.last_seen_hours, ev.event_id))
    return [event_summary(ev) for ev in events[:limit]]

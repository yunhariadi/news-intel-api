"""trending.py — App-level trending service (joins stores → pure scorers).

The thin, impure shell around the Layer A ranking core: it joins each enriched
article with its stored article metadata (origin, first-seen time, carrier),
projects them into `ArticleForTrending`, filters to the requested window, and
hands them to the pure window-builders + scorers. The worker/API supply the
fixed `now`; everything downstream is deterministic.

Two correctness choices live here:
- **origin vs carrier** — `original_source` is the syndication-resolved origin id
  and `is_origin` is whether this carrier *is* that origin, so diversity/volume/
  burst count origins (Prime Directive #1);
- **reference_scale** — computed as a rolling P95 of the batch's raw scores (raw
  is independent of the scale), so normalized 0–100 output is stable.
"""

from __future__ import annotations

from collections.abc import Callable

from packages.db.enrichment import EnrichmentStore
from packages.db.store import Store, wall_clock_hours
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
from packages.ranking.source import rank_sources, score_source
from packages.ranking.trending import TargetWindow, rank_trends, score_target

from apps.sources import SOURCE_REGISTRY

# Window span in hours (distinct from the recency half-life, which trending.py
# owns per window). An article is in-window if its age <= the span.
WINDOW_HOURS: dict[str, float] = {
    "1h": 1.0, "3h": 3.0, "6h": 6.0, "12h": 12.0,
    "24h": 24.0, "7d": 168.0, "30d": 720.0,
}

_SOURCE_NAMES: dict[str, str] = {rs.config.source_id: rs.config.name for rs in SOURCE_REGISTRY}

TREND_TYPES = ("topic", "actor", "region", "source")


def _source_name(source_id: str) -> str:
    return _SOURCE_NAMES.get(source_id, source_id)


def project_articles(
    store: Store,
    enrichment_store: EnrichmentStore,
    *,
    window: str,
    now_hours: float,
) -> list[ArticleForTrending]:
    """Join articles with their enrichment and keep those inside the window."""
    span = WINDOW_HOURS[window]
    articles_by_id = {a.article_id: a for a in store.all_articles()}
    out: list[ArticleForTrending] = []
    for enr in enrichment_store.all_enrichments():
        art = articles_by_id.get(enr.article_id)
        if art is None:
            continue
        age = now_hours - art.first_seen_hours
        if age < 0 or age > span:
            continue
        origin = art.original_source_id or art.source_id
        is_origin = art.original_source_id is None or art.source_id == art.original_source_id
        quoted_ids = {q.speaker_entity_id for q in enr.quotes if q.speaker_entity_id}
        actors = tuple(
            ActorRef(
                key=a.entity_id or f"key:{a.canonical_key}",
                name=a.display,
                kind=a.kind,
                is_quoted=a.entity_id in quoted_ids,
            )
            for a in enr.actors
        )
        regions = tuple(
            RegionRef(r.region_id, r.name, r.region_type, r.confidence) for r in enr.regions
        )
        out.append(
            ArticleForTrending(
                article_id=art.article_id,
                original_source=origin,
                source_id=art.source_id,
                source_name=_source_name(art.source_id),
                is_origin=is_origin,
                age_hours=age,
                topics=tuple(TopicRef(t.topic) for t in enr.topics),
                actors=actors,
                regions=regions,
            )
        )
    return out


def _build_windows(trend_type: str, articles: list[ArticleForTrending]) -> list[TargetWindow]:
    if trend_type == "topic":
        return build_topic_windows(articles)
    if trend_type == "actor":
        return build_actor_windows(articles)
    if trend_type == "region":
        return build_region_windows(articles)
    raise ValueError(f"unknown trend type {trend_type!r}")


def compute_trending(
    store: Store,
    enrichment_store: EnrichmentStore,
    *,
    trend_type: str = "topic",
    window: str = "24h",
    limit: int = 20,
    now_hours: Callable[[], float] = wall_clock_hours,
    fallback_scale: float = 12.0,
) -> list[dict[str, object]]:
    """Rank trends of `trend_type` over `window`. Returns serializable rows."""
    if trend_type not in TREND_TYPES:
        raise ValueError(f"unsupported type {trend_type!r}; expected one of {TREND_TYPES}")
    if window not in WINDOW_HOURS:
        raise ValueError(f"unsupported window {window!r}; expected one of {sorted(WINDOW_HOURS)}")

    articles = project_articles(store, enrichment_store, window=window, now_hours=now_hours())

    if trend_type == "source":
        windows = build_source_windows(articles)
        raws = [score_source(w, window).raw_score for w in windows]
        scale = reference_scale_p95(raws, fallback_scale)
        ranked = rank_sources(windows, window, limit, scale)
        return [
            {
                "id": s.source_id,
                "name": s.source_name,
                "type": "source",
                "score": round(s.normalized_score, 2),
                "raw_score": round(s.raw_score, 4),
                "article_count": s.article_count,
                "originality": s.originality,
                "burst": round(s.burst_z, 4),
            }
            for s in ranked
        ]

    target_windows = _build_windows(trend_type, articles)
    raws = [score_target(w, window).raw_score for w in target_windows]
    scale = reference_scale_p95(raws, fallback_scale)
    ranked_targets = rank_trends(target_windows, window, limit, scale)
    return [
        {
            "id": t.target_id,
            "name": t.target_name,
            "type": t.target_type.value,
            "score": round(t.normalized_score, 2),
            "raw_score": round(t.raw_score, 4),
            "distinct_sources": t.distinct_sources,
            "weighted_mentions": round(t.weighted_mentions, 4),
            "burst": round(t.burst_z, 4),
        }
        for t in ranked_targets
    ]

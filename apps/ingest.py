"""ingest.py — The ingestion pipeline (fetch → normalize → dedup → cluster).

Glue over the tested Layer A cores: `parse_rss` (normalize), `dedup_key` +
`content_fingerprint` (the two hashes), `cluster_content` (carrier→origin). The
network `Fetcher` is injected, so the whole pipeline is exercisable with feed
snapshots and no sockets.

Re-running over the same feeds is idempotent (dedup_key), so the worker can poll
on a schedule without duplicating rows.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from packages.clustering.content_cluster import ArticleForClustering, cluster_content
from packages.clustering.event_clusterer import EventClusterer
from packages.db.enrichment import EnrichmentStore
from packages.nlp.enrich import Enricher, enrich_article
from packages.schemas.article import SourceConfig
from packages.source_adapters.rss import parse_rss
from packages.utils.hashing import content_fingerprint, dedup_key

from apps.repository import Store, StoredArticle, wall_clock_hours
from apps.sources import RegisteredSource


class Fetcher(Protocol):
    """Returns raw feed bytes for a URL, or None on failure."""

    def __call__(self, url: str) -> bytes | None: ...


@dataclass
class IngestReport:
    fetched: int = 0
    new: int = 0
    duplicates: int = 0
    source_errors: int = 0
    clusters: int = 0


def ingest_articles(
    store: Store,
    source: SourceConfig,
    raw_xml: bytes,
    now_hours: Callable[[], float] = wall_clock_hours,
    *,
    enrichment_store: EnrichmentStore | None = None,
    enricher: Enricher | None = None,
) -> tuple[int, int]:
    """Normalize + dedup one feed's articles into the store. Returns (new, dups).

    When an enrichment store + enricher are supplied, each newly stored article
    is enriched (topics/actors/regions/quotes) in the same pass — Layer A only;
    LLM narration is not in this hot path.
    """
    new = dups = 0
    for art in parse_rss(raw_xml, source):
        key = dedup_key(art.canonical_url)
        if store.has_dedup_key(key):
            dups += 1
            continue
        stored = StoredArticle(
            article_id=key,
            source_id=art.source_id,
            is_wire=source.is_wire,
            url=art.url,
            canonical_url=art.canonical_url,
            title=art.title,
            excerpt=art.excerpt,
            published_at=art.published_at,
            published_tz=art.published_tz,
            language=art.language,
            raw_category=art.raw_category,
            dedup_key=key,
            content_fingerprint=content_fingerprint(art.title, art.excerpt or ""),
            first_seen_hours=now_hours(),
        )
        if store.add_article(stored):
            new += 1
            if enrichment_store is not None and enricher is not None:
                enrichment_store.save(
                    enrich_article(
                        article_id=key,
                        title=art.title,
                        excerpt=art.excerpt,
                        raw_category=art.raw_category,
                        source_url=art.canonical_url,
                        enricher=enricher,
                    )
                )
    return new, dups


def recluster(store: Store) -> int:
    """Recompute content clusters over all articles and write origins back."""
    candidates = [
        ArticleForClustering(
            article_id=a.article_id,
            source_id=a.source_id,
            is_wire=a.is_wire,
            content_fingerprint=a.content_fingerprint,
            first_seen_hours=a.first_seen_hours,
        )
        for a in store.all_articles()
    ]
    clusters = cluster_content(candidates)
    store.apply_clusters(clusters)
    return len(clusters)


def run_ingestion(
    registry: list[RegisteredSource],
    fetcher: Fetcher,
    store: Store,
    now_hours: Callable[[], float] = wall_clock_hours,
    *,
    enrichment_store: EnrichmentStore | None = None,
    enricher: Enricher | None = None,
    event_clusterer: EventClusterer | None = None,
) -> IngestReport:
    """Fetch + ingest every registered source, then recluster once.

    Enrichment (if wired) runs per new article during ingestion; content
    clustering is recomputed once at the end (carrier→origin resolution is
    corpus-wide); event assignment runs last, after origins are known, and is
    incremental — already-clustered articles keep their stable event IDs.
    """
    report = IngestReport()
    for rs in registry:
        try:
            raw = fetcher(rs.feed_url)
        except Exception:
            raw = None
        if raw is None:
            store.mark_source_error(rs.config.source_id)
            report.source_errors += 1
            continue
        new, dups = ingest_articles(
            store, rs.config, raw, now_hours,
            enrichment_store=enrichment_store, enricher=enricher,
        )
        report.fetched += new + dups
        report.new += new
        report.duplicates += dups
        store.mark_source_ok(rs.config.source_id, new)
    report.clusters = recluster(store)
    if event_clusterer is not None and enrichment_store is not None:
        # Import here to avoid a cycle (apps.events imports app-level helpers).
        from apps.events import assign_events

        assign_events(event_clusterer, store, enrichment_store)
    return report

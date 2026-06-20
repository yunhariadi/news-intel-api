"""memory.py — In-memory `Store` (dev/test backend).

A pure data-structure implementation of the `Store` Protocol. It's the reference
behavior the SQL store is checked against (see `test_sql_store.py`). Per-process:
under `make up` the api and worker won't share it — that's expected for a dev
scaffold, replaced by shared Postgres.
"""

from __future__ import annotations

from packages.clustering.content_cluster import ContentCluster
from packages.db.store import (
    NewsPage,
    SourceStatus,
    StoredArticle,
    decode_cursor,
    encode_cursor,
)


class InMemoryStore:
    def __init__(self) -> None:
        self._by_id: dict[str, StoredArticle] = {}
        self._dedup: set[str] = set()
        self._sources: dict[str, SourceStatus] = {}

    # --- ingestion side -----------------------------------------------------

    def has_dedup_key(self, dedup_key: str) -> bool:
        return dedup_key in self._dedup

    def add_article(self, article: StoredArticle) -> bool:
        """Idempotent on dedup_key. Returns True if newly stored, False if dup."""
        if article.dedup_key in self._dedup:
            return False
        self._dedup.add(article.dedup_key)
        self._by_id[article.article_id] = article
        return True

    def all_articles(self) -> list[StoredArticle]:
        return list(self._by_id.values())

    def apply_clusters(self, clusters: list[ContentCluster]) -> None:
        """Write content_cluster_id + resolved origin back onto member articles."""
        for cluster in clusters:
            for article_id in cluster.article_ids:
                article = self._by_id.get(article_id)
                if article is not None:
                    article.content_cluster_id = cluster.cluster_id
                    article.original_source_id = cluster.origin_source_id

    # --- source health ------------------------------------------------------

    def mark_source_ok(self, source_id: str, new_articles: int) -> None:
        s = self._sources.setdefault(source_id, SourceStatus(source_id))
        s.status = "ok"
        s.article_count += new_articles

    def mark_source_error(self, source_id: str) -> None:
        s = self._sources.setdefault(source_id, SourceStatus(source_id))
        s.status = "error"
        s.error_count += 1

    def sources_status(self) -> list[SourceStatus]:
        return [self._sources[k] for k in sorted(self._sources)]

    # --- serve side (cursor pagination, newest first) -----------------------

    def list_news(self, limit: int, cursor: str | None = None) -> NewsPage:
        ordered = sorted(
            self._by_id.values(),
            key=lambda a: (a.first_seen_hours, a.article_id),
            reverse=True,
        )
        if cursor is not None:
            mark = decode_cursor(cursor)
            ordered = [a for a in ordered if (a.first_seen_hours, a.article_id) < mark]
        page = ordered[:limit]
        next_cursor = encode_cursor(page[-1]) if len(ordered) > limit else None
        return NewsPage(items=page, next_cursor=next_cursor)

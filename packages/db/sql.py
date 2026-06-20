"""sql.py — SQLAlchemy-backed `Store` (the production storage backend).

Implements the same `Store` Protocol as `InMemoryStore`, so the worker and API
are unchanged when this replaces it. Verified against SQLite in tests; runs on
Postgres in production. The fingerprint is converted unsigned↔signed at the SQL
boundary (BIGINT is signed); keyset pagination is written portably (no row-value
comparison) so it behaves identically on SQLite and Postgres.
"""

from __future__ import annotations

from sqlalchemy import Engine, and_, create_engine, delete, or_, select
from sqlalchemy.orm import Session, sessionmaker

from packages.clustering.content_cluster import ContentCluster
from packages.db.models import Article, Base, ContentClusterRow, Source
from packages.db.store import (
    NewsPage,
    SourceStatus,
    StoredArticle,
    decode_cursor,
    encode_cursor,
    to_signed64,
    to_unsigned64,
)


def _to_record(row: Article) -> StoredArticle:
    return StoredArticle(
        article_id=row.article_id,
        source_id=row.source_id,
        is_wire=row.is_wire,
        url=row.url,
        canonical_url=row.canonical_url,
        title=row.title,
        excerpt=row.excerpt,
        published_at=row.published_at,
        published_tz=row.published_tz,
        language=row.language,
        raw_category=row.raw_category,
        dedup_key=row.dedup_key,
        content_fingerprint=to_unsigned64(row.content_fingerprint),
        first_seen_hours=row.first_seen_hours,
        content_cluster_id=row.content_cluster_id,
        original_source_id=row.original_source_id,
    )


class SqlStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session = session_factory

    # --- ingestion side -----------------------------------------------------

    def has_dedup_key(self, dedup_key: str) -> bool:
        with self._session() as s:
            stmt = select(Article.article_id).where(Article.dedup_key == dedup_key)
            return s.scalar(stmt) is not None

    def add_article(self, article: StoredArticle) -> bool:
        with self._session() as s:
            if s.get(Article, article.article_id) is not None:
                return False
            s.add(
                Article(
                    article_id=article.article_id,
                    source_id=article.source_id,
                    is_wire=article.is_wire,
                    url=article.url,
                    canonical_url=article.canonical_url,
                    title=article.title,
                    excerpt=article.excerpt,
                    published_at=article.published_at,
                    published_tz=article.published_tz,
                    language=article.language,
                    raw_category=article.raw_category,
                    dedup_key=article.dedup_key,
                    content_fingerprint=to_signed64(article.content_fingerprint),
                    first_seen_hours=article.first_seen_hours,
                    content_cluster_id=article.content_cluster_id,
                    original_source_id=article.original_source_id,
                )
            )
            s.commit()
            return True

    def all_articles(self) -> list[StoredArticle]:
        with self._session() as s:
            return [_to_record(r) for r in s.scalars(select(Article))]

    def apply_clusters(self, clusters: list[ContentCluster]) -> None:
        with self._session() as s:
            s.execute(delete(ContentClusterRow))  # recluster recomputes from scratch
            for cluster in clusters:
                s.add(
                    ContentClusterRow(
                        cluster_id=cluster.cluster_id,
                        origin_source_id=cluster.origin_source_id,
                        origin_article_id=cluster.origin_article_id,
                        carrier_count=cluster.carrier_count,
                        first_seen_hours=cluster.first_seen_hours,
                    )
                )
                for article_id in cluster.article_ids:
                    row = s.get(Article, article_id)
                    if row is not None:
                        row.content_cluster_id = cluster.cluster_id
                        row.original_source_id = cluster.origin_source_id
            s.commit()

    # --- source health ------------------------------------------------------

    def _upsert_source(self, s: Session, source_id: str) -> Source:
        row = s.get(Source, source_id)
        if row is None:
            # Set counters explicitly: column `default=` is an INSERT default,
            # not a Python attribute default, so they'd be None before flush.
            row = Source(source_id=source_id, status="unknown", article_count=0, error_count=0)
            s.add(row)
        return row

    def mark_source_ok(self, source_id: str, new_articles: int) -> None:
        with self._session() as s:
            row = self._upsert_source(s, source_id)
            row.status = "ok"
            row.article_count += new_articles
            s.commit()

    def mark_source_error(self, source_id: str) -> None:
        with self._session() as s:
            row = self._upsert_source(s, source_id)
            row.status = "error"
            row.error_count += 1
            s.commit()

    def sources_status(self) -> list[SourceStatus]:
        with self._session() as s:
            rows = s.scalars(select(Source).order_by(Source.source_id))
            return [
                SourceStatus(
                    source_id=r.source_id,
                    status=r.status,
                    article_count=r.article_count,
                    error_count=r.error_count,
                )
                for r in rows
            ]

    # --- serve side (keyset pagination, newest first) -----------------------

    def list_news(self, limit: int, cursor: str | None = None) -> NewsPage:
        with self._session() as s:
            stmt = select(Article).order_by(
                Article.first_seen_hours.desc(), Article.article_id.desc()
            )
            if cursor is not None:
                hours, article_id = decode_cursor(cursor)
                stmt = stmt.where(
                    or_(
                        Article.first_seen_hours < hours,
                        and_(
                            Article.first_seen_hours == hours,
                            Article.article_id < article_id,
                        ),
                    )
                )
            rows = list(s.scalars(stmt.limit(limit + 1)))
            has_more = len(rows) > limit
            page = [_to_record(r) for r in rows[:limit]]
            next_cursor = encode_cursor(page[-1]) if has_more and page else None
            return NewsPage(items=page, next_cursor=next_cursor)


def make_sql_store(database_url: str, *, echo: bool = False) -> SqlStore:
    """Build a SqlStore + create tables. Use for Postgres in production."""
    engine = create_engine(database_url, echo=echo)
    return _store_for_engine(engine)


def _store_for_engine(engine: Engine) -> SqlStore:
    Base.metadata.create_all(engine)
    return SqlStore(sessionmaker(bind=engine, expire_on_commit=False))

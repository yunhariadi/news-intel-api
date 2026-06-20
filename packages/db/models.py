"""models.py — SQLAlchemy 2.0 models (DESIGN.md §2 subset for Phase 1).

The two hashes (`dedup_key`, `content_fingerprint`) and the two timestamps
(`published_at` claimed, `first_seen_hours` trusted) are first-class columns.
`content_fingerprint` is stored signed (see store.to_signed64) so a top-bit-set
SimHash fits a BIGINT. Types are portable enough to run on SQLite in tests and
Postgres in production; pgvector/JSONB columns arrive in later phases.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, default="")
    is_wire: Mapped[bool] = mapped_column(Boolean, default=False)
    default_tz: Mapped[str] = mapped_column(String, default="Asia/Jakarta")
    # Runtime health (DESIGN.md §9 source status).
    status: Mapped[str] = mapped_column(String, default="unknown")
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)


class Article(Base):
    __tablename__ = "articles"

    article_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    is_wire: Mapped[bool] = mapped_column(Boolean)
    url: Mapped[str] = mapped_column(String)
    canonical_url: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    excerpt: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_tz: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String, default="id")
    raw_category: Mapped[str | None] = mapped_column(String, nullable=True)
    dedup_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    content_fingerprint: Mapped[int] = mapped_column(BigInteger)  # signed-stored SimHash
    first_seen_hours: Mapped[float] = mapped_column(Float, index=True)
    content_cluster_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    original_source_id: Mapped[str | None] = mapped_column(String, nullable=True)


class ContentClusterRow(Base):
    __tablename__ = "content_clusters"

    cluster_id: Mapped[str] = mapped_column(String, primary_key=True)
    origin_source_id: Mapped[str] = mapped_column(String)
    origin_article_id: Mapped[str] = mapped_column(String)
    carrier_count: Mapped[int] = mapped_column(Integer)
    first_seen_hours: Mapped[float] = mapped_column(Float)

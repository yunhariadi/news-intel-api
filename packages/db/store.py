"""store.py — Storage contract shared by every store implementation.

Defines the records (`StoredArticle`, `SourceStatus`, `NewsPage`), the cursor
codec, and the `Store` Protocol that both `InMemoryStore` and the SQL store
satisfy. The pipeline and API depend on this Protocol, never on a concrete
backend — so swapping in-memory ↔ Postgres is just a different implementation.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from packages.clustering.content_cluster import ContentCluster

_U64 = 1 << 64
_I63 = 1 << 63


def wall_clock_hours() -> float:
    """Our monotonic-ish ingestion clock as hours from the epoch (first_seen_by_us)."""
    return time.time() / 3600.0


def to_signed64(value: int) -> int:
    """Map an unsigned 64-bit value into the signed range a SQL BIGINT holds.

    A 64-bit SimHash can have its top bit set (>= 2**63), which overflows a
    signed BIGINT. Store the same bit pattern reinterpreted as signed.
    """
    return value - _U64 if value >= _I63 else value


def to_unsigned64(value: int) -> int:
    """Inverse of `to_signed64`: recover the unsigned fingerprint on read."""
    return value + _U64 if value < 0 else value


@dataclass
class StoredArticle:
    """An ingested article row. `first_seen_hours` is our trusted ingestion time
    (DESIGN.md §7); `published_at` is the feed's claimed time (untrusted)."""

    article_id: str          # == dedup_key (stable per canonical URL)
    source_id: str
    is_wire: bool
    url: str
    canonical_url: str
    title: str
    excerpt: str | None
    published_at: datetime | None
    published_tz: str
    language: str
    raw_category: str | None
    dedup_key: str
    content_fingerprint: int  # unsigned 64-bit at this layer
    first_seen_hours: float
    content_cluster_id: str | None = None
    original_source_id: str | None = None


@dataclass
class SourceStatus:
    source_id: str
    status: str = "unknown"   # ok | error | unknown
    article_count: int = 0
    error_count: int = 0


@dataclass
class NewsPage:
    items: list[StoredArticle]
    next_cursor: str | None


def encode_cursor(a: StoredArticle) -> str:
    raw = f"{a.first_seen_hours!r}|{a.article_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[float, str]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    hours, _, article_id = raw.partition("|")
    return float(hours), article_id


class Store(Protocol):
    """The storage interface the ingestion pipeline and API depend on."""

    def has_dedup_key(self, dedup_key: str) -> bool: ...
    def add_article(self, article: StoredArticle) -> bool: ...
    def all_articles(self) -> list[StoredArticle]: ...
    def apply_clusters(self, clusters: list[ContentCluster]) -> None: ...
    def mark_source_ok(self, source_id: str, new_articles: int) -> None: ...
    def mark_source_error(self, source_id: str) -> None: ...
    def sources_status(self) -> list[SourceStatus]: ...
    def list_news(self, limit: int, cursor: str | None = None) -> NewsPage: ...

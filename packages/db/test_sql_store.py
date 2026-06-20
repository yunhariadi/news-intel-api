"""test_sql_store.py — Gate for the SQL store (run against SQLite).

Proves the SqlStore is a behavioral drop-in for InMemoryStore (so the worker/API
don't change), and pins the BIGINT signed-fingerprint round-trip that a 64-bit
SimHash needs.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from packages.clustering.content_cluster import ContentCluster
from packages.db.memory import InMemoryStore
from packages.db.sql import SqlStore, _store_for_engine
from packages.db.store import Store, StoredArticle, to_signed64, to_unsigned64


def _sqlite_store() -> SqlStore:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return _store_for_engine(engine)


def _article(aid: str, fp: int, hours: float, *, is_wire: bool = False) -> StoredArticle:
    return StoredArticle(
        article_id=aid,
        source_id="antara" if is_wire else "kompas",
        is_wire=is_wire,
        url=f"https://x.id/{aid}",
        canonical_url=f"https://x.id/{aid}",
        title=f"title {aid}",
        excerpt="ringkasan",
        published_at=datetime(2026, 6, 16, 1, 30, tzinfo=UTC),
        published_tz="Asia/Jakarta",
        language="id",
        raw_category="Ekonomi",
        dedup_key=aid,
        content_fingerprint=fp,
        first_seen_hours=hours,
    )


# --------------------------------------------------------------------------
# Signed/unsigned conversion (the BIGINT gotcha)
# --------------------------------------------------------------------------

def test_signed_conversion_roundtrips_high_bit_fingerprint() -> None:
    top_bit = (1 << 64) - 1  # all 64 bits set -> overflows signed BIGINT
    assert to_signed64(top_bit) < 0
    assert to_unsigned64(to_signed64(top_bit)) == top_bit
    assert to_unsigned64(to_signed64(0)) == 0


def test_sql_store_preserves_unsigned_fingerprint() -> None:
    store = _sqlite_store()
    fp = (1 << 64) - 7  # high bit set
    store.add_article(_article("a", fp, 1.0))
    (got,) = store.all_articles()
    assert got.content_fingerprint == fp  # survived signed BIGINT storage


# --------------------------------------------------------------------------
# Idempotency, clustering write-back, source health
# --------------------------------------------------------------------------

def test_sql_idempotent_on_dedup_key() -> None:
    store = _sqlite_store()
    assert store.add_article(_article("a", 1, 1.0)) is True
    assert store.add_article(_article("a", 1, 1.0)) is False
    assert store.has_dedup_key("a") is True
    assert len(store.all_articles()) == 1


def test_sql_apply_clusters_writes_origin() -> None:
    store = _sqlite_store()
    store.add_article(_article("a_antara", 1, 0.0, is_wire=True))
    store.add_article(_article("a_kompas", 1, 1.0))
    cluster = ContentCluster(
        cluster_id="a_antara",
        article_ids=("a_antara", "a_kompas"),
        origin_source_id="antara",
        origin_article_id="a_antara",
        carrier_count=2,
        first_seen_hours=0.0,
    )
    store.apply_clusters([cluster])
    origins = {a.article_id: a.original_source_id for a in store.all_articles()}
    assert origins == {"a_antara": "antara", "a_kompas": "antara"}


def test_sql_source_status() -> None:
    store = _sqlite_store()
    store.mark_source_ok("antara", 2)
    store.mark_source_ok("antara", 1)
    store.mark_source_error("broken")
    status = {s.source_id: s for s in store.sources_status()}
    assert status["antara"].article_count == 3
    assert status["antara"].status == "ok"
    assert status["broken"].status == "error"
    assert status["broken"].error_count == 1


# --------------------------------------------------------------------------
# Parity with the in-memory reference
# --------------------------------------------------------------------------

@pytest.mark.parametrize("factory", [InMemoryStore, _sqlite_store])
def test_pagination_parity(factory: object) -> None:
    store: Store = factory()  # type: ignore[operator]
    for i in range(5):
        store.add_article(_article(f"a{i}", i + 1, float(i)))

    # Walk single-item pages; collect ids and assert completeness + no overlap.
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        page = store.list_news(limit=2, cursor=cursor)
        seen.extend(a.article_id for a in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert sorted(seen) == [f"a{i}" for i in range(5)]
    assert len(seen) == len(set(seen))
    # Newest-first ordering (higher first_seen_hours first).
    full = store.list_news(limit=10).items
    assert [a.article_id for a in full] == ["a4", "a3", "a2", "a1", "a0"]

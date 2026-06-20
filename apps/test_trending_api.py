"""End-to-end gate for GET /v1/trending."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from packages.db.enrichment import InMemoryEnrichmentStore
from packages.db.store import StoredArticle, wall_clock_hours
from packages.nlp.enrich import ArticleEnrichment
from packages.nlp.topic import TopicScore

from apps.api.main import app, get_enrichment_store, get_store
from apps.repository import InMemoryStore

_NOW = wall_clock_hours()


def _stored(aid: str, source: str, origin: str, fs: float) -> StoredArticle:
    return StoredArticle(
        article_id=aid, source_id=source, is_wire=False, url=f"https://x/{aid}",
        canonical_url=f"https://x/{aid}", title=aid, excerpt=None,
        published_at=datetime(2026, 6, 15, tzinfo=UTC), published_tz="Asia/Jakarta",
        language="id", raw_category=None, dedup_key=aid, content_fingerprint=0,
        first_seen_hours=fs, original_source_id=origin,
    )


def _wire() -> tuple[InMemoryStore, InMemoryEnrichmentStore]:
    store = InMemoryStore()
    enr = InMemoryEnrichmentStore()
    # Three independent origins on "korupsi", first-seen ~1h ago (in-window).
    for aid, src in [("a", "antara"), ("b", "kompas"), ("c", "cnbc")]:
        store.add_article(_stored(aid, src, src, fs=_NOW - 1.0))
        enr.save(ArticleEnrichment(article_id=aid, language="id",
                                   topics=(TopicScore("korupsi", 0.9),),
                                   actors=(), regions=(), quotes=()))
    return store, enr


def _client(store: InMemoryStore, enr: InMemoryEnrichmentStore) -> TestClient:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_enrichment_store] = lambda: enr
    return TestClient(app)


def test_trending_default_topic() -> None:
    store, enr = _wire()
    try:
        body = _client(store, enr).get("/v1/trending").json()
        assert body["meta"]["type"] == "topic"
        assert body["meta"]["window"] == "24h"
        # korupsi has 3 distinct origins -> eligible.
        assert any(r["id"] == "korupsi" for r in body["data"])
    finally:
        app.dependency_overrides.clear()


def test_trending_rejects_bad_type() -> None:
    store, enr = _wire()
    try:
        resp = _client(store, enr).get("/v1/trending", params={"type": "banana"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "bad_request"
    finally:
        app.dependency_overrides.clear()


def test_trending_rejects_bad_window() -> None:
    store, enr = _wire()
    try:
        resp = _client(store, enr).get("/v1/trending", params={"window": "99y"})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_trending_source_type() -> None:
    store, enr = _wire()
    try:
        body = _client(store, enr).get(
            "/v1/trending", params={"type": "source"}
        ).json()
        assert body["meta"]["type"] == "source"
        for r in body["data"]:
            assert "originality" in r and 0.0 <= r["score"] <= 100.0
    finally:
        app.dependency_overrides.clear()

"""test_ingest.py — End-to-end gate for fetch → cluster → serve (in-memory).

Proves the whole Phase 1 path without sockets or Postgres:
- idempotent ingestion (re-run adds nothing),
- carrier→origin collapse (a wire story republished by a carrier resolves to the
  wire origin),
- a failing source is recorded, not fatal,
- the API serves metadata-only, attributed, cursor-paginated results from what
  was ingested.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from packages.schemas.article import SourceConfig

from apps.api.main import app, get_store
from apps.ingest import run_ingestion
from apps.repository import InMemoryStore
from apps.sources import RegisteredSource

_FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "feeds"
_ANTARA = (_FIXTURES / "antara_sample.xml").read_bytes()
_TRIBUN = (_FIXTURES / "tribun_sample.xml").read_bytes()

_REGISTRY = [
    RegisteredSource(SourceConfig(source_id="antara", name="ANTARA", is_wire=True), "antara_feed"),
    RegisteredSource(SourceConfig(source_id="tribun", name="Tribun"), "tribun_feed"),
    RegisteredSource(SourceConfig(source_id="broken", name="Broken"), "broken_feed"),
]

_FEEDS = {"antara_feed": _ANTARA, "tribun_feed": _TRIBUN}


def _fetcher(url: str) -> bytes | None:
    return _FEEDS.get(url)


def _fresh_store() -> InMemoryStore:
    store = InMemoryStore()
    # Fixed clock so all articles land in one near-dup time window.
    run_ingestion(_REGISTRY, _fetcher, store, now_hours=lambda: 1000.0)
    return store


def test_ingestion_counts_and_idempotency() -> None:
    store = InMemoryStore()
    first = run_ingestion(_REGISTRY, _fetcher, store, now_hours=lambda: 1000.0)
    # antara: 2 unique, tribun: 1 (different URL -> separate carrier row), broken: error
    assert first.new == 3
    assert first.duplicates == 0
    assert first.source_errors == 1
    assert first.clusters == 2  # {subsidi (2 carriers), suku-bunga (1)}

    # Re-running the same feeds adds nothing (dedup_key idempotency).
    second = run_ingestion(_REGISTRY, _fetcher, store, now_hours=lambda: 1000.0)
    assert second.new == 0
    assert second.duplicates == 3
    assert len(store.all_articles()) == 3


def test_syndication_resolves_to_wire_origin() -> None:
    store = _fresh_store()
    subsidi = [a for a in store.all_articles() if "subsidi" in a.canonical_url]
    assert len(subsidi) == 2  # ANTARA + Tribun carriers
    # Both collapse into one content cluster with the WIRE as origin.
    assert {a.content_cluster_id for a in subsidi} == {subsidi[0].content_cluster_id}
    assert all(a.original_source_id == "antara" for a in subsidi)


def test_failing_source_is_recorded_not_fatal() -> None:
    store = _fresh_store()
    statuses = {s.source_id: s for s in store.sources_status()}
    assert statuses["broken"].status == "error"
    assert statuses["antara"].status == "ok"
    assert statuses["antara"].article_count == 2


def test_api_serves_ingested_metadata() -> None:
    store = _fresh_store()
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        body = client.get("/v1/news").json()
        assert len(body["data"]) == 3
        item = body["data"][0]
        # Metadata only + attribution (PR2); no body field is ever present.
        assert set(item) == {
            "id", "source_id", "title", "excerpt", "url",
            "published_at", "content_cluster_id", "original_source_id",
        }
        assert item["url"].startswith("https://")
        assert "body" not in item

        status = client.get("/v1/sources/status").json()["data"]
        assert {s["source_id"] for s in status} == {"antara", "tribun", "broken"}
    finally:
        app.dependency_overrides.clear()


def test_api_cursor_pagination_is_complete_and_non_overlapping() -> None:
    store = _fresh_store()
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        seen: list[str] = []
        cursor = None
        for _ in range(5):  # safety bound
            params = {"limit": 1}
            if cursor:
                params["cursor"] = cursor
            body = client.get("/v1/news", params=params).json()
            seen.extend(i["id"] for i in body["data"])
            cursor = body["meta"]["cursor"]
            if cursor is None:
                break
        assert len(seen) == 3
        assert len(set(seen)) == 3  # no duplicates across pages
    finally:
        app.dependency_overrides.clear()

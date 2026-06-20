"""End-to-end gate for the event endpoints (/v1/events[...]).

Ingests fixtures through the full pipeline with event clustering wired in, then
drives the API: events list, detail, timeline (from first_seen_by_us), and
source comparison (origins, not carriers).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from packages.clustering.event_clusterer import EventClusterer
from packages.db.enrichment import InMemoryEnrichmentStore
from packages.nlp.enrich import build_enricher
from packages.schemas.article import SourceConfig

from apps.api.main import app, get_event_clusterer
from apps.ingest import run_ingestion
from apps.repository import InMemoryStore
from apps.sources import RegisteredSource

_REGISTRY = [
    RegisteredSource(SourceConfig(source_id="antara", name="ANTARA", is_wire=True), "antara_feed"),
    RegisteredSource(SourceConfig(source_id="kompas", name="Kompas"), "kompas_feed"),
]


def _feed(items: list[tuple[str, str, str]]) -> bytes:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link><description>{d}</description></item>"
        for t, d, u in items
    )
    return f"<rss><channel>{body}</channel></rss>".encode()


def _feeds() -> dict[str, bytes]:
    return {
        # Both outlets cover the same KPK corruption story -> one event, 2 origins.
        "antara_feed": _feed([
            ("KPK Periksa Pejabat soal Korupsi",
             '"Kami dalami kasus ini," kata Erick Thohir di Jakarta.',
             "https://antara.id/k1"),
        ]),
        "kompas_feed": _feed([
            ("Erick Thohir Diperiksa KPK soal Korupsi",
             "Penyidik KPK memeriksa Erick Thohir terkait dugaan korupsi di Jakarta.",
             "https://kompas.id/k2"),
        ]),
    }


def _wire() -> tuple[InMemoryStore, EventClusterer]:
    store = InMemoryStore()
    enr = InMemoryEnrichmentStore()
    clusterer = EventClusterer()
    feeds = _feeds()
    run_ingestion(
        _REGISTRY,
        lambda url: feeds.get(url),
        store,
        now_hours=lambda: 1000.0,
        enrichment_store=enr,
        enricher=build_enricher(),
        event_clusterer=clusterer,
    )
    return store, clusterer


def _client(clusterer: EventClusterer) -> TestClient:
    app.dependency_overrides[get_event_clusterer] = lambda: clusterer
    return TestClient(app)


def test_events_list_and_clustering() -> None:
    _store, clusterer = _wire()
    try:
        body = _client(clusterer).get("/v1/events").json()
        assert body["data"]
        ev = body["data"][0]
        # The two articles share actor Erick Thohir + topic korupsi -> one event.
        assert ev["article_count"] == 2
        assert ev["source_count"] == 2  # antara + kompas origins
    finally:
        app.dependency_overrides.clear()


def test_event_detail_timeline_sources() -> None:
    _store, clusterer = _wire()
    try:
        client = _client(clusterer)
        event_id = client.get("/v1/events").json()["data"][0]["id"]

        detail = client.get(f"/v1/events/{event_id}").json()["data"]
        assert detail["id"] == event_id

        timeline = client.get(f"/v1/events/{event_id}/timeline").json()["data"]
        times = [e["time"] for e in timeline]
        assert times == sorted(times)  # chronological by first_seen_by_us

        sources = client.get(f"/v1/events/{event_id}/sources").json()["data"]
        assert sources["distinct_origins"] == 2
    finally:
        app.dependency_overrides.clear()


def test_unknown_event_404() -> None:
    _store, clusterer = _wire()
    try:
        resp = _client(clusterer).get("/v1/events/evt_does_not_exist")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"
    finally:
        app.dependency_overrides.clear()

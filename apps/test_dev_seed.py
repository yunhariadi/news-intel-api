"""Gate for dev_seed — the demo data flows through the whole pipeline."""

from __future__ import annotations

from fastapi.testclient import TestClient
from packages.clustering.event_clusterer import EventClusterer
from packages.db.enrichment import InMemoryEnrichmentStore

from apps.api.main import app, get_enrichment_store, get_event_clusterer, get_store
from apps.dev_seed import seed_stores
from apps.repository import InMemoryStore


def _seeded() -> tuple[InMemoryStore, InMemoryEnrichmentStore, EventClusterer]:
    store = InMemoryStore()
    enr = InMemoryEnrichmentStore()
    clusterer = EventClusterer()
    # Fixed clock so all demo articles land in one window.
    seed_stores(store, enr, clusterer, now_hours=lambda: 1000.0)
    return store, enr, clusterer


def test_seed_populates_stores() -> None:
    store, enr, clusterer = _seeded()
    assert len(store.all_articles()) >= 6
    assert len(enr.all_enrichments()) >= 6
    assert len(clusterer.events) >= 1


def test_seed_collapses_syndicated_wire_to_one_origin() -> None:
    store, _enr, _c = _seeded()
    bi = [a for a in store.all_articles() if "bi-rate" in a.canonical_url]
    assert len(bi) == 2                                  # ANTARA + Kompas carry
    assert len({a.content_cluster_id for a in bi}) == 1  # one content cluster
    assert all(a.original_source_id == "antara" for a in bi)  # origin = the wire


def test_seed_clusters_the_kpk_event_across_origins() -> None:
    _store, _enr, clusterer = _seeded()
    # Three outlets cover the KPK corruption story -> one event, 3 origins.
    biggest = max(clusterer.events.values(), key=lambda e: len(e.members))
    assert len(biggest.origin_sources) >= 3


def _client(store: InMemoryStore, enr: InMemoryEnrichmentStore, c: EventClusterer) -> TestClient:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_enrichment_store] = lambda: enr
    app.dependency_overrides[get_event_clusterer] = lambda: c
    return TestClient(app)


def test_seeded_endpoints_return_data() -> None:
    # Seed against the real clock so the API's wall-clock trending window
    # includes the demo articles (the API computes trends at request time).
    store = InMemoryStore()
    enr = InMemoryEnrichmentStore()
    clusterer = EventClusterer()
    seed_stores(store, enr, clusterer)
    try:
        client = _client(store, enr, clusterer)
        assert client.get("/v1/news").json()["data"]
        assert client.get("/v1/topics").json()["data"]
        assert client.get("/v1/actors").json()["data"]
        assert client.get("/v1/quotes").json()["data"]
        assert client.get("/v1/events").json()["data"]
        # korupsi is covered by 3 origins -> eligible trend over a wide window.
        trend = client.get("/v1/trending", params={"window": "7d", "type": "topic"}).json()
        assert any(r["id"] == "korupsi" for r in trend["data"])
    finally:
        app.dependency_overrides.clear()

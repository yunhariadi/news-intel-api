"""End-to-end gate for the Phase 2 endpoints (/v1/topics|actors|regions|quotes).

Ingests fixtures through the real pipeline with enrichment wired in, then drives
the API and asserts: enrichment is served, every quote carries a
source-paragraph link, and the compliance gate filters suppressed/exonerated
actors out of responses.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from packages.compliance.invariants import LegalStatus
from packages.db.enrichment import EntityRecord, InMemoryEnrichmentStore
from packages.nlp.enrich import build_enricher
from packages.schemas.article import SourceConfig

from apps.api.main import app, get_enrichment_store, get_store
from apps.ingest import run_ingestion
from apps.repository import InMemoryStore
from apps.sources import RegisteredSource

_REGISTRY = [
    RegisteredSource(SourceConfig(source_id="antara", name="ANTARA", is_wire=True), "antara_feed"),
]


def _feed() -> bytes:
    items = [
        ("Bank Indonesia Tahan Suku Bunga",
         '"Inflasi terkendali," kata Perry Warjiyo di Jakarta.',
         "Ekonomi", "https://antara.id/a/1"),
        ("KPK Periksa Pejabat di Surabaya",
         '"Kami dalami kasus ini," kata Erick Thohir.',
         "Hukum", "https://antara.id/a/2"),
    ]
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link>"
        f"<description>{d}</description><category>{c}</category></item>"
        for t, d, c, u in items
    )
    return f"<rss><channel>{body}</channel></rss>".encode()


def _wire() -> tuple[InMemoryStore, InMemoryEnrichmentStore]:
    store = InMemoryStore()
    enr = InMemoryEnrichmentStore()
    run_ingestion(
        _REGISTRY,
        lambda url: _feed() if url == "antara_feed" else None,
        store,
        now_hours=lambda: 1000.0,
        enrichment_store=enr,
        enricher=build_enricher(),
    )
    return store, enr


def _client(store: InMemoryStore, enr: InMemoryEnrichmentStore) -> TestClient:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_enrichment_store] = lambda: enr
    return TestClient(app)


def test_topics_endpoint() -> None:
    store, enr = _wire()
    try:
        body = _client(store, enr).get("/v1/topics").json()
        topics = {t["topic"] for t in body["data"]}
        assert "moneter" in topics or "ekonomi" in topics
    finally:
        app.dependency_overrides.clear()


def test_actors_endpoint_resolves_entities() -> None:
    store, enr = _wire()
    try:
        body = _client(store, enr).get("/v1/actors").json()
        ids = {a["id"] for a in body["data"]}
        assert "org_bi" in ids
        assert "per_perry" in ids
    finally:
        app.dependency_overrides.clear()


def test_regions_endpoint() -> None:
    store, enr = _wire()
    try:
        body = _client(store, enr).get("/v1/regions").json()
        names = {r["name"] for r in body["data"]}
        assert "DKI Jakarta" in names or "Surabaya" in names
    finally:
        app.dependency_overrides.clear()


def test_quotes_endpoint_has_source_paragraph_url() -> None:
    store, enr = _wire()
    try:
        body = _client(store, enr).get("/v1/quotes").json()
        assert body["data"]
        for q in body["data"]:
            assert q["source_paragraph_url"].startswith("https://")  # I2
            assert q["speaker"] is not None
    finally:
        app.dependency_overrides.clear()


def test_quotes_filter_by_actor() -> None:
    store, enr = _wire()
    try:
        body = _client(store, enr).get("/v1/quotes", params={"actor": "Perry"}).json()
        assert body["data"]
        assert all("Perry" in (q["speaker"] or "") for q in body["data"])
    finally:
        app.dependency_overrides.clear()


def test_suppressed_actor_filtered_from_api() -> None:
    store, enr = _wire()
    enr.upsert_entity(
        EntityRecord(entity_id="per_perry", display="Perry Warjiyo",
                     kind="PERSON", suppressed=True)
    )
    try:
        client = _client(store, enr)
        actors = client.get("/v1/actors").json()["data"]
        assert all(a["id"] != "per_perry" for a in actors)  # P2
        quotes = client.get("/v1/quotes").json()["data"]
        assert all(q["speaker_id"] != "per_perry" for q in quotes)
    finally:
        app.dependency_overrides.clear()


def test_exonerated_actor_never_carries_accusatory_label() -> None:
    # P1: the store surfaces only the *current* status, so once an actor reaches
    # acquittal (bebas) the API can never serve a stale `tersangka` label —
    # an exonerated person stays queryable, but cleared.
    store, enr = _wire()
    enr.upsert_entity(
        EntityRecord(entity_id="per_erick", display="Erick Thohir", kind="PERSON",
                     legal_status=LegalStatus.BEBAS)
    )
    try:
        actors = _client(store, enr).get("/v1/actors").json()["data"]
        erick = [a for a in actors if a["id"] == "per_erick"]
        assert erick and erick[0]["legal_status"] == "bebas"
        assert erick[0]["legal_status"] not in {"tersangka", "terdakwa"}
    finally:
        app.dependency_overrides.clear()

"""Phase 5 gates — auth, rate limiting, tier gating, DSR workflow.

Uses an *enforcing* access store (the default scaffold store is open) seeded with
known keys, injected via dependency_overrides.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from packages.access.tiers import Tier
from packages.db.enrichment import InMemoryEnrichmentStore
from packages.nlp.enrich import build_enricher, enrich_article

from apps.access_store import InMemoryAccessStore
from apps.api.main import app, get_access_store, get_enrichment_store

_FREE = "nik_free_aaaaaaaaaaaaaaaa"
_BIZ = "nik_biz_bbbbbbbbbbbbbbbbb"
_ADMIN = "nik_admin_ccccccccccccccc"


def _store(*, free_quota: int = 1000) -> InMemoryAccessStore:
    s = InMemoryAccessStore(enforce=True)
    s.register_plaintext(_FREE, "free", Tier.FREE, quota_override=free_quota)
    s.register_plaintext(_BIZ, "biz", Tier.BUSINESS)
    s.register_plaintext(_ADMIN, "admin", Tier.ENTERPRISE, is_admin=True)
    return s


def _client(access: InMemoryAccessStore, enr: InMemoryEnrichmentStore | None = None) -> TestClient:
    app.dependency_overrides[get_access_store] = lambda: access
    if enr is not None:
        app.dependency_overrides[get_enrichment_store] = lambda: enr
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- authentication ---------------------------------------------------------

def test_health_is_exempt_from_auth() -> None:
    try:
        assert _client(_store()).get("/v1/health").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_missing_key_is_401() -> None:
    try:
        resp = _client(_store()).get("/v1/sources")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthorized"
    finally:
        app.dependency_overrides.clear()


def test_invalid_key_is_401() -> None:
    try:
        resp = _client(_store()).get("/v1/sources", headers=_auth("nik_bogus_xxxxxxxx"))
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_valid_key_passes_with_ratelimit_headers() -> None:
    try:
        resp = _client(_store()).get("/v1/sources", headers=_auth(_FREE))
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "1000"
        assert int(resp.headers["X-RateLimit-Remaining"]) < 1000
        assert "X-RateLimit-Reset" in resp.headers
    finally:
        app.dependency_overrides.clear()


# --- rate limiting ----------------------------------------------------------

def test_quota_exhaustion_returns_429() -> None:
    try:
        client = _client(_store(free_quota=2))
        assert client.get("/v1/sources", headers=_auth(_FREE)).status_code == 200
        assert client.get("/v1/sources", headers=_auth(_FREE)).status_code == 200
        third = client.get("/v1/sources", headers=_auth(_FREE))
        assert third.status_code == 429
        assert third.json()["error"]["code"] == "rate_limit_exceeded"
        assert "Retry-After" in third.headers
        assert third.headers["X-RateLimit-Remaining"] == "0"
    finally:
        app.dependency_overrides.clear()


def test_usage_endpoint_reports_consumption() -> None:
    try:
        client = _client(_store())
        client.get("/v1/sources", headers=_auth(_BIZ))
        body = client.get("/v1/usage", headers=_auth(_BIZ)).json()["data"]
        assert body["tier"] == "business"
        assert body["used"] >= 1
        assert body["remaining"] == body["quota"] - body["used"]
    finally:
        app.dependency_overrides.clear()


# --- tier gating ------------------------------------------------------------

def test_free_tier_cannot_create_webhook() -> None:
    try:
        resp = _client(_store()).post(
            "/v1/webhooks", headers=_auth(_FREE),
            json={"name": "x", "target_url": "https://c/cb",
                  "rules": {"topics": ["moneter"], "window": "24h", "min_score": 50}},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "forbidden"
    finally:
        app.dependency_overrides.clear()


def test_business_tier_can_create_and_list_webhooks() -> None:
    try:
        client = _client(_store())
        created = client.post(
            "/v1/webhooks", headers=_auth(_BIZ),
            json={"name": "BI Monitor", "target_url": "https://c/cb",
                  "rules": {"actors": ["Bank Indonesia"], "window": "1h", "min_score": 50}},
        )
        assert created.status_code == 200
        listed = client.get("/v1/webhooks", headers=_auth(_BIZ)).json()["data"]
        assert any(w["name"] == "BI Monitor" for w in listed)
    finally:
        app.dependency_overrides.clear()


def test_saved_queries_require_business() -> None:
    try:
        client = _client(_store())
        assert client.post("/v1/saved-queries", headers=_auth(_FREE),
                           json={"name": "q", "query": {}}).status_code == 403
        assert client.post("/v1/saved-queries", headers=_auth(_BIZ),
                           json={"name": "q", "query": {"topic": "moneter"}}).status_code == 200
    finally:
        app.dependency_overrides.clear()


# --- DSR workflow (erase -> entity absent everywhere) -----------------------

def _enr_with_smi() -> InMemoryEnrichmentStore:
    enr = InMemoryEnrichmentStore()
    enr.save(enrich_article(
        article_id="a1", title="Sri Mulyani Bicara Anggaran",
        excerpt='"Anggaran efisien," kata Sri Mulyani Indrawati.',
        raw_category=None, source_url="https://x/a1", enricher=build_enricher(),
    ))
    return enr


def test_dsr_requires_admin() -> None:
    try:
        resp = _client(_store(), _enr_with_smi()).post(
            "/v1/admin/dsr", headers=_auth(_BIZ),
            json={"entity_id": "per_smi", "action": "erase"},
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_dsr_erase_removes_entity_from_all_responses() -> None:
    enr = _enr_with_smi()
    try:
        client = _client(_store(), enr)
        # Present before erasure.
        before = client.get("/v1/actors", headers=_auth(_ADMIN)).json()["data"]
        assert any(a["id"] == "per_smi" for a in before)
        # Erase via the admin DSR console (P2).
        applied = client.post("/v1/admin/dsr", headers=_auth(_ADMIN),
                              json={"entity_id": "per_smi", "action": "erase"})
        assert applied.status_code == 200
        # Absent from actors AND quotes afterward.
        actors = client.get("/v1/actors", headers=_auth(_ADMIN)).json()["data"]
        quotes = client.get("/v1/quotes", headers=_auth(_ADMIN)).json()["data"]
        assert all(a["id"] != "per_smi" for a in actors)
        assert all(q["speaker_id"] != "per_smi" for q in quotes)
    finally:
        app.dependency_overrides.clear()


# --- public pages -----------------------------------------------------------

def test_bot_info_and_takedown_public() -> None:
    try:
        client = _client(_store())
        assert client.get("/bot-info").status_code == 200
        assert client.get("/takedown").json()["contact"]
    finally:
        app.dependency_overrides.clear()

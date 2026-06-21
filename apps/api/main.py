"""FastAPI application entry point.

Phase 0 skeleton: a runnable app with the response/error envelopes and
server-side `request_id` from `DESIGN.md §8` baked in, plus `GET /v1/health`.
Domain routes (`/v1/news`, `/v1/trending`, …) arrive in later phases and should
reuse `success()` / the error envelope so the contract stays uniform.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from packages.access.quota import check_quota
from packages.access.tiers import allows_saved_queries, allows_webhooks
from packages.access.webhooks import WebhookRule
from packages.compliance.invariants import (
    LegalStatus,
    NewsItemView,
    has_required_attribution,
)
from packages.db.enrichment import EntityRecord
from pydantic import BaseModel

from apps.access_store import ApiKeyRecord, InMemoryAccessStore, current_period
from apps.api.config import get_settings
from apps.events import (
    event_sources_view,
    event_summary,
    event_timeline_view,
    list_events,
)
from apps.repository import (
    EnrichmentStore,
    EventClusterer,
    Store,
    StoredArticle,
    get_default_access_store,
    get_default_enrichment_store,
    get_default_event_clusterer,
    get_default_store,
)
from apps.sources import SOURCE_REGISTRY
from apps.trending import TREND_TYPES, WINDOW_HOURS, compute_trending

settings = get_settings()


class ApiError(Exception):
    """A controlled API error rendered into the spec's error envelope."""

    def __init__(
        self, status_code: int, code: str, message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


# Paths that never require authentication (liveness + public policy pages).
_EXEMPT_PATHS = frozenset(
    {"/v1/health", "/bot-info", "/takedown", "/docs", "/redoc", "/openapi.json"}
)


def get_store() -> Store:
    """Store dependency. Overridable in tests via app.dependency_overrides."""
    return get_default_store()


def get_enrichment_store() -> EnrichmentStore:
    """Enrichment-store dependency. Overridable in tests."""
    return get_default_enrichment_store()


def get_event_clusterer() -> EventClusterer:
    """Event-clusterer dependency. Overridable in tests."""
    return get_default_event_clusterer()


def get_access_store() -> InMemoryAccessStore:
    """Access-store dependency. Overridable in tests."""
    return get_default_access_store()


def _period_reset_epoch(now: datetime | None = None) -> int:
    """Unix epoch of the start of next month (the quota reset, X-RateLimit-Reset)."""
    dt = now or datetime.now(UTC)
    year, month = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    nxt = datetime(year, month, 1, tzinfo=UTC)
    return int(nxt.timestamp())


def authenticate(
    request: Request,
    response: Response,
    store: Annotated[InMemoryAccessStore, Depends(get_access_store)],
) -> None:
    """Global gate: validate the bearer key, meter usage, enforce the monthly
    quota, and set `X-RateLimit-*` headers. No-op when enforcement is off or the
    path is exempt (so the open scaffold and pre-Phase-5 tests are unaffected)."""
    path = request.url.path
    if not store.enforce or path in _EXEMPT_PATHS or not path.startswith("/v1/"):
        return

    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header[:7].lower() == "bearer " else ""
    record = store.lookup(token)
    if record is None:
        raise ApiError(401, "unauthorized", "Missing or invalid API key.")

    period = current_period()
    state = check_quota(store.usage(record.key_hash, period), record.quota())
    reset = _period_reset_epoch()
    rate_headers = {
        "X-RateLimit-Limit": str(state.limit),
        "X-RateLimit-Remaining": str(state.remaining),
        "X-RateLimit-Reset": str(reset),
    }
    for k, v in rate_headers.items():
        response.headers[k] = v
    if not state.allowed:
        retry_after = max(0, reset - int(datetime.now(UTC).timestamp()))
        raise ApiError(
            429, "rate_limit_exceeded", "Monthly quota exceeded.",
            headers={**rate_headers, "Retry-After": str(retry_after)},
        )
    store.record_usage(record.key_hash, period)
    request.state.api_key = record


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hooks.

    - DEV_SEED=true        → seed synthetic demo data through the full pipeline;
    - ENABLE_SCHEDULER=true → run real-feed ingestion in-process on a schedule
      (the all-in-one deployment that serves real news).
    """
    cfg = get_settings()
    if cfg.enable_scheduler:
        # Surface the scheduler's per-run "ingest: new=… clusters=…" heartbeat.
        # It's logged at INFO; without a handler at that level uvicorn filters
        # it out, so `docker compose logs -f api` looks silent even though the
        # 5-minute fetch loop is running. Attach a handler so the heartbeat (and
        # "fetch failed" warnings) are visible.
        import logging

        sched_log = logging.getLogger("scheduler")
        if not sched_log.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
            sched_log.addHandler(handler)
        sched_log.setLevel(logging.INFO)
        sched_log.propagate = False
    if cfg.seed_api_key:

        # Register a durable, restart-stable key in THIS (serving) process's
        # access store. A key minted via `docker compose exec` lives in a
        # separate process and the server never sees it — see config.py.
        from packages.access.tiers import Tier

        get_default_access_store().register_plaintext(
            cfg.seed_api_key, "seed", Tier.BUSINESS, is_admin=True
        )
    if cfg.dev_seed:
        from apps.dev_seed import seed_default_stores

        seed_default_stores()

    scheduler = None
    if cfg.enable_scheduler:
        from apps.scheduler import start_scheduler

        scheduler = start_scheduler()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    dependencies=[Depends(authenticate)],
    lifespan=lifespan,
)


def _current_key(request: Request) -> ApiKeyRecord | None:
    return getattr(request.state, "api_key", None)


def _require_feature(request: Request, allowed: bool, feature: str) -> None:
    rec = _current_key(request)
    if rec is not None and not allowed:
        raise ApiError(403, "forbidden", f"{feature} requires the Business tier or higher.")


def _require_admin(request: Request) -> None:
    rec = _current_key(request)
    if rec is not None and not rec.is_admin:
        raise ApiError(403, "forbidden", "Admin privilege required.")


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


def _news_item(a: StoredArticle) -> dict[str, Any]:
    return {
        "id": a.article_id,
        "source_id": a.source_id,
        "title": a.title,
        "excerpt": a.excerpt,           # hard-capped metadata, never a full body
        "url": a.canonical_url,         # origin link-back (PR2)
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "content_cluster_id": a.content_cluster_id,
        "original_source_id": a.original_source_id,
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _bad_request(request: Request, message: str) -> JSONResponse:
    """Spec error envelope with a 400 status (invalid query parameters)."""
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "bad_request",
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


def _not_found(request: Request, message: str) -> JSONResponse:
    """Spec error envelope with a 404 status."""
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "not_found",
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


def success(request: Request, data: Any, **meta: Any) -> dict[str, Any]:
    """Wrap a payload in the standard success envelope: {meta, data}."""
    return {
        "meta": {
            "request_id": getattr(request.state, "request_id", None),
            "generated_at": _now_iso(),
            **meta,
        },
        "data": data,
    }


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Any) -> Any:
    """Generate a server-side request_id (honoring an inbound one for tracing)
    and echo it on the response, per CLAUDE.md §5."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Spec error envelope: {"error": {code, message, request_id}}."""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "request_id": request_id,
            }
        },
    )


@app.get("/v1/health")
def health(request: Request) -> dict[str, Any]:
    return success(
        request,
        {"status": "ok", "app": settings.app_name, "env": settings.app_env},
    )


@app.get("/v1/news")
def list_news(
    request: Request,
    store: Annotated[Store, Depends(get_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    page = store.list_news(limit=limit, cursor=cursor)
    data = []
    for a in page.items:
        # PR2: every served item must carry source + origin url, or it is dropped.
        view = NewsItemView(source_name=a.source_id, origin_url=a.canonical_url)
        if has_required_attribution(view):
            data.append(_news_item(a))
    return success(request, data, limit=limit, cursor=page.next_cursor)


@app.get("/v1/topics")
def list_topics(
    request: Request,
    enr: Annotated[EnrichmentStore, Depends(get_enrichment_store)],
) -> dict[str, Any]:
    data = [
        {"topic": t.topic, "article_count": t.article_count, "avg_confidence": t.avg_confidence}
        for t in enr.topics()
    ]
    return success(request, data)


@app.get("/v1/actors")
def list_actors(
    request: Request,
    enr: Annotated[EnrichmentStore, Depends(get_enrichment_store)],
) -> dict[str, Any]:
    # Rows are already compliance-filtered (P1/P2/P4) inside the store.
    data = [
        {
            "id": a.entity_id,
            "name": a.display,
            "kind": a.kind,
            "mention_count": a.mention_count,
            "legal_status": a.legal_status,
        }
        for a in enr.actors()
    ]
    return success(request, data)


@app.get("/v1/regions")
def list_regions(
    request: Request,
    enr: Annotated[EnrichmentStore, Depends(get_enrichment_store)],
) -> dict[str, Any]:
    data = [
        {
            "id": r.region_id,
            "name": r.name,
            "region_type": r.region_type,
            "article_count": r.article_count,
            "avg_confidence": r.avg_confidence,
        }
        for r in enr.regions()
    ]
    return success(request, data)


@app.get("/v1/quotes")
def list_quotes(
    request: Request,
    enr: Annotated[EnrichmentStore, Depends(get_enrichment_store)],
    actor: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    # Each row passed the compliance gate (I1/I2/I3 + speaker exposability).
    data = [
        {
            "quote": q.quote_text,
            "speaker": q.speaker_display,
            "speaker_id": q.speaker_entity_id,
            "source_paragraph_url": q.source_paragraph_url,  # I2: always present
            "confidence": q.confidence,
            "method": q.method,
        }
        for q in enr.quotes(actor=actor)
    ]
    return success(request, data)


@app.get("/v1/trending")
def trending(
    request: Request,
    store: Annotated[Store, Depends(get_store)],
    enr: Annotated[EnrichmentStore, Depends(get_enrichment_store)],
    type: Annotated[str, Query()] = "topic",
    window: Annotated[str, Query()] = "24h",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Any:
    if type not in TREND_TYPES:
        return _bad_request(request, f"type must be one of {list(TREND_TYPES)}")
    if window not in WINDOW_HOURS:
        return _bad_request(request, f"window must be one of {sorted(WINDOW_HOURS)}")
    data = compute_trending(
        store, enr, trend_type=type, window=window, limit=limit,
        fallback_scale=settings.trend_reference_scale_fallback,
    )
    return success(request, data, window=window, type=type, limit=limit)


@app.get("/v1/events")
def get_events(
    request: Request,
    clusterer: Annotated[EventClusterer, Depends(get_event_clusterer)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    return success(request, list_events(clusterer, limit=limit), limit=limit)


@app.get("/v1/events/{event_id}")
def get_event(
    request: Request,
    event_id: str,
    clusterer: Annotated[EventClusterer, Depends(get_event_clusterer)],
) -> Any:
    ev = clusterer.events.get(event_id)
    if ev is None or ev.status == "merged":
        return _not_found(request, f"event {event_id} not found")
    return success(request, event_summary(ev))


@app.get("/v1/events/{event_id}/timeline")
def get_event_timeline(
    request: Request,
    event_id: str,
    clusterer: Annotated[EventClusterer, Depends(get_event_clusterer)],
) -> Any:
    ev = clusterer.events.get(event_id)
    if ev is None or ev.status == "merged":
        return _not_found(request, f"event {event_id} not found")
    return success(request, event_timeline_view(ev), event_id=event_id)


@app.get("/v1/events/{event_id}/sources")
def get_event_sources(
    request: Request,
    event_id: str,
    clusterer: Annotated[EventClusterer, Depends(get_event_clusterer)],
) -> Any:
    ev = clusterer.events.get(event_id)
    if ev is None or ev.status == "merged":
        return _not_found(request, f"event {event_id} not found")
    return success(request, event_sources_view(ev), event_id=event_id)


class WebhookRules(BaseModel):
    topics: list[str] = []
    actors: list[str] = []
    regions: list[str] = []
    window: str = "24h"
    min_score: float = 50.0


class WebhookCreate(BaseModel):
    name: str
    target_url: str
    rules: WebhookRules = WebhookRules()


class SavedQueryCreate(BaseModel):
    name: str
    query: dict[str, Any] = {}


class DSRRequest(BaseModel):
    entity_id: str
    action: str                      # "erase" | "rectify"
    display: str | None = None
    legal_status: str | None = None


@app.post("/v1/webhooks")
def create_webhook(
    request: Request,
    body: WebhookCreate,
    store: Annotated[InMemoryAccessStore, Depends(get_access_store)],
) -> Any:
    rec = _current_key(request)
    _require_feature(request, rec is None or allows_webhooks(rec.tier), "Webhooks")
    if body.rules.window not in WINDOW_HOURS:
        return _bad_request(request, f"window must be one of {sorted(WINDOW_HOURS)}")
    rule = WebhookRule(
        topics=frozenset(body.rules.topics),
        actors=frozenset(body.rules.actors),
        regions=frozenset(body.rules.regions),
        window=body.rules.window,
        min_score=body.rules.min_score,
    )
    owner = rec.key_hash if rec else "anon"
    wh = store.create_webhook(owner, body.name, body.target_url, rule)
    return success(
        request, {"id": wh.webhook_id, "name": wh.spec.name, "target_url": wh.spec.target_url}
    )


@app.get("/v1/webhooks")
def list_webhooks(
    request: Request,
    store: Annotated[InMemoryAccessStore, Depends(get_access_store)],
) -> dict[str, Any]:
    rec = _current_key(request)
    owner = rec.key_hash if rec else "anon"
    data = [
        {"id": w.webhook_id, "name": w.spec.name, "target_url": w.spec.target_url,
         "window": w.spec.rule.window, "min_score": w.spec.rule.min_score}
        for w in store.list_webhooks(owner)
    ]
    return success(request, data)


@app.post("/v1/saved-queries")
def create_saved_query(
    request: Request,
    body: SavedQueryCreate,
    store: Annotated[InMemoryAccessStore, Depends(get_access_store)],
) -> Any:
    rec = _current_key(request)
    _require_feature(request, rec is None or allows_saved_queries(rec.tier), "Saved queries")
    owner = rec.key_hash if rec else "anon"
    q = store.create_saved_query(owner, body.name, body.query)
    return success(request, {"id": q.query_id, "name": q.name})


@app.get("/v1/saved-queries")
def list_saved_queries(
    request: Request,
    store: Annotated[InMemoryAccessStore, Depends(get_access_store)],
) -> dict[str, Any]:
    rec = _current_key(request)
    owner = rec.key_hash if rec else "anon"
    data = [{"id": q.query_id, "name": q.name, "query": q.params}
            for q in store.list_saved_queries(owner)]
    return success(request, data)


@app.get("/v1/usage")
def usage(
    request: Request,
    store: Annotated[InMemoryAccessStore, Depends(get_access_store)],
) -> dict[str, Any]:
    rec = _current_key(request)
    if rec is None:
        return success(request, {"auth": "disabled"})
    period = current_period()
    used = store.usage(rec.key_hash, period)
    return success(request, {
        "tier": rec.tier.value,
        "period": period,
        "quota": rec.quota(),
        "used": used,
        "remaining": max(0, rec.quota() - used),
    })


@app.post("/v1/admin/dsr")
def data_subject_request(
    request: Request,
    body: DSRRequest,
    enr: Annotated[EnrichmentStore, Depends(get_enrichment_store)],
) -> Any:
    """Data-subject request console (COMPLIANCE.md §5): erase (suppress + tombstone)
    or rectify a governed entity. Suppression propagates because every serializer
    re-checks the compliance gate at query time."""
    _require_admin(request)
    if body.action not in {"erase", "rectify"}:
        return _bad_request(request, "action must be 'erase' or 'rectify'")
    existing = enr.get_entity(body.entity_id)
    display = body.display or (existing.display if existing else body.entity_id)
    kind = existing.kind if existing else "PERSON"
    if body.action == "erase":
        enr.upsert_entity(EntityRecord(
            entity_id=body.entity_id, display=display, kind=kind, suppressed=True))
    else:  # rectify
        status = LegalStatus(body.legal_status) if body.legal_status else (
            existing.legal_status if existing else None)
        enr.upsert_entity(EntityRecord(
            entity_id=body.entity_id, display=display, kind=kind,
            legal_status=status,
            suppressed=existing.suppressed if existing else False))
    return success(
        request, {"entity_id": body.entity_id, "action": body.action, "status": "applied"}
    )


@app.get("/bot-info")
def bot_info() -> dict[str, Any]:
    """Public bot-information page (PR3); the crawler User-Agent links here."""
    return {
        "bot": "NewsIntelBot",
        "purpose": "Collects Indonesian news metadata for a structured intelligence "
                   "API. Stores metadata and short excerpts only — never full article "
                   "bodies. Always links back to the origin source.",
        "respects_robots_txt": True,
        "contact": "abuse@example.com",
        "takedown": "/takedown",
    }


@app.get("/takedown")
def takedown() -> dict[str, Any]:
    """Public takedown / correction policy (PR3)."""
    return {
        "policy": "To request correction or removal of metadata about you or your "
                  "publication, email the contact below with the URL(s) concerned. "
                  "We action data-subject erasure/rectification within the documented SLA.",
        "contact": "takedown@example.com",
        "data_subject_rights": ["access", "rectification", "erasure", "consent-withdrawal"],
    }


@app.get("/v1/sources")
def list_sources(request: Request) -> dict[str, Any]:
    data = [
        {
            "source_id": rs.config.source_id,
            "name": rs.config.name,
            "is_wire": rs.config.is_wire,
            "default_tz": rs.config.default_tz,
        }
        for rs in SOURCE_REGISTRY
    ]
    return success(request, data)


@app.get("/v1/sources/status")
def sources_status(
    request: Request, store: Annotated[Store, Depends(get_store)]
) -> dict[str, Any]:
    data = [
        {
            "source_id": s.source_id,
            "status": s.status,
            "article_count": s.article_count,
            "error_count": s.error_count,
        }
        for s in store.sources_status()
    ]
    return success(request, data)

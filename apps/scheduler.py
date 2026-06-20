"""scheduler.py — In-process real-feed ingestion for the all-in-one deployment.

When `ENABLE_SCHEDULER=true`, the API runs ingestion against the real RSS feeds
in `apps.sources` on startup and then on `FETCH_INTERVAL_SECONDS`, writing into
the same process-global stores it serves from. This is the simplest deployment
that serves *real* news from a single process (no separate worker, no
cross-process store sharing required).

Trade-offs (single-VPS scaffold): the scheduler runs in a background thread, so
reads during a write are best-effort consistent; in-memory enrichment/events are
rebuilt from the feed window on restart. For multi-process / horizontal scaling,
the stores need a shared (SQL) backend — deferred work, see DESIGN.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from packages.db.store import wall_clock_hours

from apps.api.config import Settings, get_settings
from apps.ingest import Fetcher, IngestReport, run_ingestion
from apps.repository import (
    get_default_access_store,
    get_default_enricher,
    get_default_enrichment_store,
    get_default_event_clusterer,
    get_default_store,
)
from apps.sources import SOURCE_REGISTRY

if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

log = logging.getLogger("scheduler")


def make_http_fetcher(settings: Settings) -> Fetcher:
    """A polite httpx-backed fetcher; returns None on any HTTP/transport error so
    one bad source can't stop the run (circuit-breaker-lite). The User-Agent
    carries the bot-info URL (PR3)."""
    import httpx

    client = httpx.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.fetch_timeout_seconds,
        follow_redirects=True,
    )

    def fetch(url: str) -> bytes | None:
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as exc:
            log.warning("fetch failed for %s: %s", url, exc)
            return None

    return fetch


def ingest_real_once(
    fetcher: Fetcher | None = None,
    now_hours: Callable[[], float] = wall_clock_hours,
) -> IngestReport:
    """Run one real-feed ingestion into the process-global stores."""
    settings = get_settings()
    fetch = fetcher or make_http_fetcher(settings)
    report = run_ingestion(
        SOURCE_REGISTRY,
        fetch,
        get_default_store(),
        now_hours=now_hours,
        enrichment_store=get_default_enrichment_store(),
        enricher=get_default_enricher(),
        event_clusterer=get_default_event_clusterer(),
    )
    # Seed the configured admin key so an authed deployment is usable on boot.
    _ = get_default_access_store()
    log.info(
        "ingest: new=%d dups=%d errors=%d clusters=%d",
        report.new, report.duplicates, report.source_errors, report.clusters,
    )
    return report


def start_scheduler() -> BackgroundScheduler:
    """Run one ingestion now, then schedule it on FETCH_INTERVAL_SECONDS.

    Returns the started scheduler so the caller can shut it down on app exit.
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    settings = get_settings()
    try:
        ingest_real_once()  # populate immediately so endpoints aren't empty
    except Exception:  # never let a bad first fetch crash startup
        log.exception("initial ingestion failed; scheduler will retry")

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        ingest_real_once,
        "interval",
        seconds=settings.fetch_interval_seconds,
        id="ingest",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("ingestion scheduler started (every %ds)", settings.fetch_interval_seconds)
    return scheduler

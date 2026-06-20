"""Worker entry point (APScheduler for the MVP, per CLAUDE.md).

Phase 0 skeleton: starts the scheduler and runs a heartbeat on
`FETCH_INTERVAL_SECONDS`. Real jobs (fetch → normalize → dedup → cluster →
enrich → trends) are wired in from Phase 1 onward. APScheduler is imported
lazily inside `main()` so this module stays importable for unit tests even
where the scheduler isn't installed.
"""

from __future__ import annotations

import logging

from apps.api.config import Settings, get_settings
from apps.ingest import Fetcher
from apps.scheduler import ingest_real_once, make_http_fetcher

log = logging.getLogger("worker")


def ingest_once(settings: Settings, fetcher: Fetcher) -> None:
    """One ingestion pass into the process-global stores."""
    ingest_real_once(fetcher=fetcher)


def main() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    log.info("starting worker for %s (env=%s)", settings.app_name, settings.app_env)
    log.warning("in-memory store is per-process; api will not see this data until Postgres")

    fetcher = make_http_fetcher(settings)
    ingest_once(settings, fetcher)  # run immediately on boot

    # All scheduling math is done in UTC; source-local zones are stored, not
    # used to drive the clock (CLAUDE.md §5 / DESIGN.md §7).
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        ingest_once,
        "interval",
        seconds=settings.fetch_interval_seconds,
        args=[settings, fetcher],
        id="ingest",
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("worker shutting down")


if __name__ == "__main__":
    main()

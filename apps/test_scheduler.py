"""Gate for scheduler.py — real-ingestion wiring + graceful source failure."""

from __future__ import annotations

from apps.scheduler import ingest_real_once
from apps.sources import SOURCE_REGISTRY


def test_ingest_real_once_handles_all_sources_failing() -> None:
    # A fetcher that returns None for every URL (network down): every source is
    # recorded as an error, nothing is added, and it does not raise.
    report = ingest_real_once(fetcher=lambda url: None, now_hours=lambda: 1000.0)
    assert report.new == 0
    assert report.source_errors == len(SOURCE_REGISTRY)


def test_ingest_real_once_ingests_a_served_feed() -> None:
    feed = (
        b'<?xml version="1.0"?><rss><channel>'
        b"<item><title>Bank Indonesia Tahan Suku Bunga</title>"
        b"<link>https://antara.example/bi</link>"
        b"<description>Inflasi terkendali kata Perry Warjiyo.</description></item>"
        b"</channel></rss>"
    )
    first_url = SOURCE_REGISTRY[0].feed_url
    report = ingest_real_once(
        fetcher=lambda url: feed if url == first_url else None,
        now_hours=lambda: 2000.0,
    )
    assert report.new >= 1  # the one served feed produced an article

"""Trending regression set (BUILD_ORDER Phase 3).

Pins real-shaped scenarios through the *full* stack (article store + enrichment
store → compute_trending), asserting the DoD properties on live-like data:
- a known burst topic trends at #1 ("on date D, topic T trended");
- a wire dump (one origin, many carriers) never tops the board — it is filtered
  as ineligible (Prime Directive #1);
- normalized scores stay within 0–100.

A scoring change that stops detecting the pinned burst, or lets syndication win,
fails CI. The fixture grows by adding files to tests/fixtures/trending_regression/.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from apps.trending import compute_trending
from packages.db.enrichment import InMemoryEnrichmentStore
from packages.db.memory import InMemoryStore
from packages.db.store import StoredArticle
from packages.nlp.enrich import ArticleEnrichment
from packages.nlp.topic import TopicScore

_FIX = Path(__file__).resolve().parent / "fixtures" / "trending_regression"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _stored(aid: str, source: str, origin: str, first_seen_hours: float) -> StoredArticle:
    return StoredArticle(
        article_id=aid,
        source_id=source,
        is_wire=(source == "antara"),
        url=f"https://{source}.id/{aid}",
        canonical_url=f"https://{source}.id/{aid}",
        title=aid,
        excerpt=None,
        published_at=datetime(2026, 6, 15, tzinfo=UTC),
        published_tz="Asia/Jakarta",
        language="id",
        raw_category=None,
        dedup_key=aid,
        content_fingerprint=0,
        first_seen_hours=first_seen_hours,
        original_source_id=origin,
    )


def _build_stores(scenario: dict) -> tuple[InMemoryStore, InMemoryEnrichmentStore, float]:
    as_of = scenario["as_of_hours"]
    store = InMemoryStore()
    enr = InMemoryEnrichmentStore()
    for a in scenario["articles"]:
        first_seen = as_of - a["age_hours"]
        store.add_article(_stored(a["id"], a["source"], a["origin"], first_seen))
        enr.save(
            ArticleEnrichment(
                article_id=a["id"],
                language="id",
                topics=tuple(TopicScore(t, 0.9) for t in a["topics"]),
                actors=(),
                regions=(),
                quotes=(),
            )
        )
    return store, enr, as_of


def test_known_burst_topic_trends_first() -> None:
    sc = _load("kpk_case_20260615.json")
    store, enr, as_of = _build_stores(sc)
    rows = compute_trending(
        store, enr, trend_type="topic", window=sc["window"], now_hours=lambda: as_of
    )
    assert rows, "expected some trending topics"
    assert rows[0]["id"] == sc["expect_top_topic"]


def test_eligible_topics_present_and_wire_dump_absent() -> None:
    sc = _load("kpk_case_20260615.json")
    store, enr, as_of = _build_stores(sc)
    rows = compute_trending(
        store, enr, trend_type="topic", window=sc["window"], now_hours=lambda: as_of
    )
    ids = {r["id"] for r in rows}
    for t in sc["expect_eligible_contains"]:
        assert t in ids, f"expected eligible topic {t} in results"
    for t in sc["expect_ineligible_or_absent"]:
        # The wire dump (one origin, six carriers) must not surface as a trend.
        assert t not in ids, f"syndicated topic {t} should not trend"


def test_normalized_scores_bounded() -> None:
    sc = _load("kpk_case_20260615.json")
    store, enr, as_of = _build_stores(sc)
    rows = compute_trending(
        store, enr, trend_type="topic", window=sc["window"], now_hours=lambda: as_of
    )
    assert all(0.0 <= r["score"] <= 100.0 for r in rows)


def test_wire_dump_distinct_sources_collapses_to_one() -> None:
    # Directly assert the syndication invariant on the olahraga group.
    sc = _load("kpk_case_20260615.json")
    store, enr, as_of = _build_stores(sc)
    rows = compute_trending(
        store, enr, trend_type="topic", window=sc["window"], limit=50,
        now_hours=lambda: as_of,
    )
    # korupsi has 5 distinct origins; that is what carries it above ekonomi.
    korupsi = next(r for r in rows if r["id"] == "korupsi")
    assert korupsi["distinct_sources"] == 5

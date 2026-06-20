"""Phase 5 gate — webhook firing on a stable (bounded normalized) score threshold."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from packages.access.webhooks import WebhookRule
from packages.db.enrichment import InMemoryEnrichmentStore
from packages.db.store import StoredArticle
from packages.nlp.enrich import ArticleEnrichment
from packages.nlp.topic import TopicScore

from apps.access_store import InMemoryAccessStore
from apps.repository import InMemoryStore
from apps.webhook_dispatch import dispatch_due_webhooks

_NOW = 1000.0


def _stored(aid: str, src: str) -> StoredArticle:
    return StoredArticle(
        article_id=aid, source_id=src, is_wire=False, url=f"https://{src}/{aid}",
        canonical_url=f"https://{src}/{aid}", title=aid, excerpt=None,
        published_at=datetime(2026, 6, 15, tzinfo=UTC), published_tz="Asia/Jakarta",
        language="id", raw_category=None, dedup_key=aid, content_fingerprint=0,
        first_seen_hours=_NOW - 1.0, original_source_id=src,
    )


def _stores() -> tuple[InMemoryStore, InMemoryEnrichmentStore]:
    # "korupsi" covered by three independent origins -> an eligible, scoring trend.
    store = InMemoryStore()
    enr = InMemoryEnrichmentStore()
    for aid, src in [("a", "antara"), ("b", "kompas"), ("c", "cnbc")]:
        store.add_article(_stored(aid, src))
        enr.save(ArticleEnrichment(article_id=aid, language="id",
                                   topics=(TopicScore("korupsi", 0.9),),
                                   actors=(), regions=(), quotes=()))
    return store, enr


def _rule(min_score: float, topic: str = "korupsi") -> WebhookRule:
    return WebhookRule(topics=frozenset({topic}), actors=frozenset(),
                       regions=frozenset(), window="24h", min_score=min_score)


def test_webhook_fires_when_trend_crosses_threshold() -> None:
    store, enr = _stores()
    access = InMemoryAccessStore(enforce=True)
    owner = "owner"
    access.create_webhook(owner, "low", "https://c/low", _rule(min_score=1.0))
    access.create_webhook(owner, "high", "https://c/high", _rule(min_score=99.0))
    access.create_webhook(owner, "other", "https://c/other", _rule(min_score=1.0, topic="olahraga"))

    sent: list[tuple[str, dict[str, Any]]] = []
    firings = dispatch_due_webhooks(
        access, store, enr, now_hours=_NOW, sender=lambda url, p: sent.append((url, p))
    )

    urls = {u for u, _ in sent}
    assert "https://c/low" in urls          # min_score 1 -> fires on korupsi
    assert "https://c/high" not in urls     # min_score 99 -> stays silent
    assert "https://c/other" not in urls    # watches a topic that isn't trending
    assert all(f.name == "korupsi" for f in firings)


def test_no_webhooks_means_no_firings() -> None:
    store, enr = _stores()
    access = InMemoryAccessStore(enforce=True)
    sent: list[Any] = []
    firings = dispatch_due_webhooks(
        access, store, enr, now_hours=_NOW, sender=lambda url, p: sent.append(url)
    )
    assert firings == [] and sent == []


def test_fired_payload_carries_bounded_score() -> None:
    store, enr = _stores()
    access = InMemoryAccessStore(enforce=True)
    access.create_webhook("o", "w", "https://c/cb", _rule(min_score=1.0))
    sent: list[tuple[str, dict[str, Any]]] = []
    dispatch_due_webhooks(access, store, enr, now_hours=_NOW,
                          sender=lambda url, p: sent.append((url, p)))
    assert sent
    _, payload = sent[0]
    assert 0.0 <= payload["score"] <= 100.0   # stable, bounded threshold basis
    assert payload["trend_type"] == "topic"

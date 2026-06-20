"""webhooks.py — Webhook rule matching + evaluation (Layer A, pure).

SPEC §18 alerts. A webhook rule watches some topics/actors/regions and fires when
a matching trend's score crosses `min_score`. Critically, the score compared is
the **bounded normalized 0–100** trend score (DESIGN.md §4 / BUILD_ORDER Phase 5:
"use the bounded normalized score so `min_score` is stable") — an absolute
threshold like 50 means the same thing this month and next, instead of drifting
with corpus volume.

Pure: rules + a snapshot of current trends in, firings out. Delivery (the HTTP
POST, retries) is the app's job; this module only decides *whether* to fire.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class WebhookRule:
    topics: frozenset[str]
    actors: frozenset[str]
    regions: frozenset[str]
    window: str
    min_score: float


@dataclass(frozen=True)
class WebhookSpec:
    webhook_id: str
    name: str
    target_url: str
    rule: WebhookRule


@dataclass(frozen=True)
class TrendRow:
    trend_type: str   # topic | actor | region
    target_id: str
    name: str
    score: float      # normalized 0..100


@dataclass(frozen=True)
class Firing:
    webhook_id: str
    target_url: str
    trend_type: str
    target_id: str
    name: str
    score: float


def _norm(s: str) -> str:
    return s.strip().lower()


def _watched_for(rule: WebhookRule, trend_type: str) -> frozenset[str]:
    return {
        "topic": rule.topics,
        "actor": rule.actors,
        "region": rule.regions,
    }.get(trend_type, frozenset())


def webhook_matches(rule: WebhookRule, trend: TrendRow) -> bool:
    """True iff the rule watches this trend's target AND its score >= min_score.

    Comparison is on the bounded normalized score, so `min_score` is stable over
    time. Names and ids are matched case-insensitively; an empty watch list for
    the trend's type means the rule doesn't watch that type.
    """
    if trend.score < rule.min_score:
        return False
    watched = {_norm(x) for x in _watched_for(rule, trend.trend_type)}
    if not watched:
        return False
    return _norm(trend.name) in watched or _norm(trend.target_id) in watched


def evaluate_webhooks(
    webhooks: Sequence[WebhookSpec], trends: Sequence[TrendRow]
) -> list[Firing]:
    """All (webhook, trend) firings for the current trend snapshot, deterministic."""
    firings: list[Firing] = []
    for wh in webhooks:
        for tr in trends:
            if webhook_matches(wh.rule, tr):
                firings.append(
                    Firing(
                        webhook_id=wh.webhook_id,
                        target_url=wh.target_url,
                        trend_type=tr.trend_type,
                        target_id=tr.target_id,
                        name=tr.name,
                        score=tr.score,
                    )
                )
    firings.sort(key=lambda f: (f.webhook_id, f.trend_type, f.target_id))
    return firings

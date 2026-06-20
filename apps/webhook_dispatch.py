"""webhook_dispatch.py — Evaluate registered webhooks against live trends + fire.

Bridges the trending service to the pure webhook evaluator: for each window any
webhook watches, it computes topic/actor/region trends (the **bounded normalized
0–100 score**, so `min_score` is stable), evaluates every webhook's rule, and
delivers a firing via an injected `sender`. The sender is injected so the
firing decision is testable without sockets; the worker passes a real HTTP POST.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from packages.access.webhooks import Firing, TrendRow, evaluate_webhooks

from apps.access_store import InMemoryAccessStore
from apps.repository import EnrichmentStore, Store
from apps.trending import WINDOW_HOURS, compute_trending

# (target_url, payload) -> None. The worker supplies an httpx POST.
Sender = Callable[[str, dict[str, Any]], None]


def _collect_trends(
    store: Store,
    enrichment_store: EnrichmentStore,
    *,
    window: str,
    now_hours: float,
    fallback_scale: float,
) -> list[TrendRow]:
    rows: list[TrendRow] = []
    for trend_type in ("topic", "actor", "region"):
        for r in compute_trending(
            store, enrichment_store,
            trend_type=trend_type, window=window, limit=100,
            now_hours=lambda: now_hours, fallback_scale=fallback_scale,
        ):
            score = r["score"]
            rows.append(
                TrendRow(
                    trend_type=trend_type,
                    target_id=str(r["id"]),
                    name=str(r["name"]),
                    score=float(score) if isinstance(score, int | float) else 0.0,
                )
            )
    return rows


def _payload(f: Firing) -> dict[str, Any]:
    return {
        "webhook_id": f.webhook_id,
        "trend_type": f.trend_type,
        "target_id": f.target_id,
        "name": f.name,
        "score": f.score,
    }


def dispatch_due_webhooks(
    access_store: InMemoryAccessStore,
    store: Store,
    enrichment_store: EnrichmentStore,
    *,
    now_hours: float,
    sender: Sender,
    fallback_scale: float = 12.0,
) -> list[Firing]:
    """Evaluate all webhooks against current trends and deliver each firing.

    Returns the firings (for logging/metering). Trends are computed once per
    distinct window across all webhooks.
    """
    specs = [w for w in access_store.all_webhook_specs() if w.rule.window in WINDOW_HOURS]
    if not specs:
        return []
    windows = {wh.rule.window for wh in specs}
    trends_by_window = {
        w: _collect_trends(
            store, enrichment_store, window=w, now_hours=now_hours, fallback_scale=fallback_scale
        )
        for w in windows
    }
    fired: list[Firing] = []
    for wh in specs:
        for f in evaluate_webhooks([wh], trends_by_window[wh.rule.window]):
            sender(f.target_url, _payload(f))
            fired.append(f)
    return fired

"""Gate for the access core — tiers, key hashing, quota math, webhook matching."""

from __future__ import annotations

from packages.access.keys import generate_key, hash_key, looks_like_key
from packages.access.quota import check_quota
from packages.access.tiers import (
    Tier,
    allows_saved_queries,
    allows_webhooks,
    monthly_quota,
)
from packages.access.webhooks import (
    Firing,
    TrendRow,
    WebhookRule,
    WebhookSpec,
    evaluate_webhooks,
    webhook_matches,
)

# --- tiers ------------------------------------------------------------------

def test_quota_ordering() -> None:
    assert (
        monthly_quota(Tier.FREE)
        < monthly_quota(Tier.DEVELOPER)
        < monthly_quota(Tier.BUSINESS)
        < monthly_quota(Tier.ENTERPRISE)
    )


def test_feature_gating_by_tier() -> None:
    assert not allows_webhooks(Tier.FREE)
    assert not allows_webhooks(Tier.DEVELOPER)
    assert allows_webhooks(Tier.BUSINESS)
    assert allows_saved_queries(Tier.ENTERPRISE)


# --- keys -------------------------------------------------------------------

def test_key_generation_and_hashing() -> None:
    k = generate_key()
    assert looks_like_key(k)
    assert hash_key(k) == hash_key(k)        # stable
    assert hash_key(k) != k                   # never stores plaintext
    assert generate_key() != generate_key()   # unique


def test_looks_like_key_rejects_garbage() -> None:
    assert not looks_like_key("")
    assert not looks_like_key("Bearer abc")
    assert not looks_like_key("nik_")


# --- quota ------------------------------------------------------------------

def test_quota_allows_until_limit() -> None:
    s = check_quota(used=0, limit=3)
    assert s.allowed and s.remaining == 2
    assert check_quota(used=2, limit=3).remaining == 0
    assert check_quota(used=2, limit=3).allowed is True


def test_quota_blocks_at_limit() -> None:
    s = check_quota(used=3, limit=3)
    assert s.allowed is False
    assert s.remaining == 0
    assert s.retry_after_recommended is True


# --- webhooks ---------------------------------------------------------------

def _rule(min_score: float = 50.0) -> WebhookRule:
    return WebhookRule(
        topics=frozenset({"moneter"}),
        actors=frozenset({"Bank Indonesia"}),
        regions=frozenset(),
        window="1h",
        min_score=min_score,
    )


def test_webhook_fires_above_threshold() -> None:
    assert webhook_matches(_rule(50), TrendRow("topic", "moneter", "moneter", 75.0)) is True


def test_webhook_silent_below_threshold() -> None:
    assert webhook_matches(_rule(50), TrendRow("topic", "moneter", "moneter", 40.0)) is False


def test_webhook_ignores_unwatched_target() -> None:
    assert webhook_matches(_rule(0), TrendRow("topic", "korupsi", "korupsi", 99.0)) is False


def test_webhook_actor_match_case_insensitive() -> None:
    tr = TrendRow("actor", "org_bi", "bank indonesia", 80.0)
    assert webhook_matches(_rule(50), tr) is True


def test_evaluate_webhooks_deterministic_and_only_matching() -> None:
    wh = WebhookSpec("wh1", "BI Monitor", "https://client/cb", _rule(50))
    trends = [
        TrendRow("topic", "moneter", "moneter", 60.0),    # fires
        TrendRow("topic", "korupsi", "korupsi", 90.0),    # unwatched
        TrendRow("actor", "org_bi", "Bank Indonesia", 30.0),  # below floor
    ]
    firings = evaluate_webhooks([wh], trends)
    assert len(firings) == 1
    assert isinstance(firings[0], Firing)
    assert firings[0].webhook_id == "wh1" and firings[0].name == "moneter"
    assert evaluate_webhooks([wh], trends) == firings  # deterministic

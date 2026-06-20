"""tiers.py — Product tiers, quotas, and feature flags (Layer A).

SPEC §17/§30: Free / Developer / Business / Enterprise. Monthly request quotas
and feature entitlements (webhooks + saved queries are Business+). Enterprise is
"custom"; we model it as a very high default that an admin can override per key.
"""

from __future__ import annotations

from enum import Enum


class Tier(str, Enum):
    FREE = "free"
    DEVELOPER = "developer"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


# Monthly request quotas (SPEC §17). Enterprise default is high + overridable.
TIER_MONTHLY_QUOTA: dict[Tier, int] = {
    Tier.FREE: 1_000,
    Tier.DEVELOPER: 50_000,
    Tier.BUSINESS: 500_000,
    Tier.ENTERPRISE: 10_000_000,
}

# Feature entitlements: webhooks + saved queries unlock at Business.
_PREMIUM_TIERS: frozenset[Tier] = frozenset({Tier.BUSINESS, Tier.ENTERPRISE})


def monthly_quota(tier: Tier) -> int:
    return TIER_MONTHLY_QUOTA[tier]


def allows_webhooks(tier: Tier) -> bool:
    return tier in _PREMIUM_TIERS


def allows_saved_queries(tier: Tier) -> bool:
    return tier in _PREMIUM_TIERS

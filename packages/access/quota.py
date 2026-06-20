"""quota.py — Monthly quota / rate-limit math (Layer A, pure).

The decision is a pure function of (used, limit); the app supplies `used` from
its usage meter for the current billing period and renders `reset` from a clock.
Output mirrors the `X-RateLimit-*` headers (SPEC §17) so the wiring is a direct
serialization with no logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitState:
    limit: int
    used: int
    remaining: int
    allowed: bool   # True if THIS request is within quota

    @property
    def retry_after_recommended(self) -> bool:
        return not self.allowed


def check_quota(used: int, limit: int) -> RateLimitState:
    """Evaluate a request against the monthly quota.

    `used` is the count *before* this request. The request is allowed iff
    `used < limit`; remaining is computed post-grant so a client sees it count
    down to zero. Never returns negative remaining.
    """
    allowed = used < limit
    consumed = used + 1 if allowed else used
    remaining = max(0, limit - consumed)
    return RateLimitState(limit=limit, used=consumed, remaining=remaining, allowed=allowed)

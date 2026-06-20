"""access_store.py — In-memory commercial state (keys, usage, webhooks, queries).

The mutable counterpart to the pure `packages.access` core. Process-global for
the v0.5 scaffold (a SQL-backed implementation behind the same shape is a later
phase). `enforce` gates authentication: it defaults **off** so the open
local/CI scaffold (and every pre-Phase-5 test) keeps working, and is flipped on
in deployments and the Phase 5 auth tests. Keys are stored only as hashes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.access.keys import generate_key, hash_key
from packages.access.tiers import Tier, monthly_quota
from packages.access.webhooks import WebhookRule, WebhookSpec


def current_period(now: datetime | None = None) -> str:
    """Billing period key 'YYYY-MM' (monthly quotas reset on the calendar month)."""
    dt = now or datetime.now(UTC)
    return f"{dt.year:04d}-{dt.month:02d}"


@dataclass
class ApiKeyRecord:
    key_hash: str
    name: str
    tier: Tier
    is_admin: bool = False
    quota_override: int | None = None

    def quota(self) -> int:
        return self.quota_override if self.quota_override is not None else monthly_quota(self.tier)


@dataclass
class StoredWebhook:
    webhook_id: str
    owner_hash: str
    spec: WebhookSpec


@dataclass
class SavedQuery:
    query_id: str
    owner_hash: str
    name: str
    params: dict[str, object]


@dataclass
class InMemoryAccessStore:
    enforce: bool = False
    _keys: dict[str, ApiKeyRecord] = field(default_factory=dict)
    _usage: dict[tuple[str, str], int] = field(default_factory=dict)
    _webhooks: dict[str, StoredWebhook] = field(default_factory=dict)
    _saved: dict[str, SavedQuery] = field(default_factory=dict)
    _seq: int = 0

    # --- keys ---------------------------------------------------------------

    def issue_key(
        self, name: str, tier: Tier, *, is_admin: bool = False, quota_override: int | None = None
    ) -> str:
        """Create a key; returns the plaintext (shown once, never stored)."""
        plaintext = generate_key()
        self.register_plaintext(
            plaintext, name, tier, is_admin=is_admin, quota_override=quota_override
        )
        return plaintext

    def register_plaintext(
        self, plaintext: str, name: str, tier: Tier, *,
        is_admin: bool = False, quota_override: int | None = None,
    ) -> ApiKeyRecord:
        """Register a known plaintext key (used by seeding + deterministic tests)."""
        rec = ApiKeyRecord(
            key_hash=hash_key(plaintext), name=name, tier=tier,
            is_admin=is_admin, quota_override=quota_override,
        )
        self._keys[rec.key_hash] = rec
        return rec

    def lookup(self, token: str) -> ApiKeyRecord | None:
        return self._keys.get(hash_key(token)) if token else None

    # --- usage metering -----------------------------------------------------

    def usage(self, key_hash: str, period: str) -> int:
        return self._usage.get((key_hash, period), 0)

    def record_usage(self, key_hash: str, period: str) -> None:
        self._usage[(key_hash, period)] = self.usage(key_hash, period) + 1

    # --- webhooks -----------------------------------------------------------

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq}"

    def create_webhook(
        self, owner_hash: str, name: str, target_url: str, rule: WebhookRule
    ) -> StoredWebhook:
        wid = self._next_id("wh")
        wh = StoredWebhook(
            webhook_id=wid,
            owner_hash=owner_hash,
            spec=WebhookSpec(webhook_id=wid, name=name, target_url=target_url, rule=rule),
        )
        self._webhooks[wid] = wh
        return wh

    def list_webhooks(self, owner_hash: str) -> list[StoredWebhook]:
        return [w for w in self._webhooks.values() if w.owner_hash == owner_hash]

    def all_webhook_specs(self) -> list[WebhookSpec]:
        return [w.spec for w in self._webhooks.values()]

    # --- saved queries ------------------------------------------------------

    def create_saved_query(
        self, owner_hash: str, name: str, params: dict[str, object]
    ) -> SavedQuery:
        qid = self._next_id("sq")
        q = SavedQuery(query_id=qid, owner_hash=owner_hash, name=name, params=params)
        self._saved[qid] = q
        return q

    def list_saved_queries(self, owner_hash: str) -> list[SavedQuery]:
        return [q for q in self._saved.values() if q.owner_hash == owner_hash]

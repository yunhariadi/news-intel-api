"""event_clusterer.py — Incremental, stable-ID event clustering (Layer A).

DESIGN.md §6: entity+time first, embeddings second. An article joins an existing
event or opens a new one; we **never** batch re-partition and reassign IDs
(that would break webhooks, saved searches, and timelines — Prime Directive: do
not reassign event IDs). Merges/splits are explicit, logged operations.

The matcher is a deterministic state machine — no I/O, no clock. `first_seen_hours`
(our trusted ingestion time, DESIGN.md §7) is passed in; the worker drives the
assignment. Embedding cosine is a *tie-breaker*, not the gate: it enters only via
an injected `similarity_fn` hook, so the core stays pure and testable and no heavy
model sits in Layer A.

Matching gate (cheap, robust): a candidate joins an event only if it is within
`WINDOW_HOURS` of the event's last activity AND (shares ≥1 canonical actor, OR
shares both a region and a topic). Among gated events it joins the highest-scoring
one above `JOIN_THRESHOLD`, else opens a new event. Blocking via inverted actor/
region indexes keeps it from comparing against every event.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

# Calibration knobs (tuned against the labeled event set; never inline magic).
WINDOW_HOURS: float = 48.0
W_ACTOR: float = 0.5
W_REGION: float = 0.2
W_TOPIC: float = 0.2
W_TIME: float = 0.1
W_EMBED: float = 0.2          # only applied when a similarity_fn is injected
JOIN_THRESHOLD: float = 0.25

SimilarityFn = Callable[[str, str], float]


@dataclass(frozen=True)
class ArticleForEvent:
    """A pure projection of an enriched article for event assignment."""

    article_id: str
    first_seen_hours: float
    original_source: str            # syndication-resolved origin (diversity basis)
    actor_keys: frozenset[str]
    region_ids: frozenset[str]
    topics: frozenset[str]
    title: str = ""


@dataclass
class Event:
    event_id: str
    members: list[ArticleForEvent] = field(default_factory=list)
    actor_keys: set[str] = field(default_factory=set)
    region_ids: set[str] = field(default_factory=set)
    topics: set[str] = field(default_factory=set)
    first_seen_hours: float = 0.0
    last_seen_hours: float = 0.0
    status: str = "active"
    representative_title: str = ""

    @property
    def article_ids(self) -> list[str]:
        return [m.article_id for m in self.members]

    @property
    def origin_sources(self) -> set[str]:
        return {m.original_source for m in self.members}

    def _absorb(self, art: ArticleForEvent) -> None:
        if not self.members:
            self.first_seen_hours = art.first_seen_hours
            self.representative_title = art.title
        self.members.append(art)
        self.actor_keys |= art.actor_keys
        self.region_ids |= art.region_ids
        self.topics |= art.topics
        self.first_seen_hours = min(self.first_seen_hours, art.first_seen_hours)
        self.last_seen_hours = max(self.last_seen_hours, art.first_seen_hours)


@dataclass(frozen=True)
class ClusterOp:
    """A logged merge/split operation (exposed to manual-review tools)."""

    kind: str                 # "merge" | "split"
    surviving_event_id: str
    other_event_id: str
    moved_article_ids: tuple[str, ...]


def _jaccard(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _event_id_for(seed_article_id: str) -> str:
    return f"evt_{seed_article_id}"


class EventClusterer:
    """Online, incremental event assignment with stable IDs."""

    def __init__(self, similarity_fn: SimilarityFn | None = None) -> None:
        self._events: dict[str, Event] = {}
        self._by_actor: dict[str, set[str]] = {}
        self._by_region: dict[str, set[str]] = {}
        self._of_article: dict[str, str] = {}
        self._log: list[ClusterOp] = []
        self._similarity_fn = similarity_fn

    # --- read side ----------------------------------------------------------

    @property
    def events(self) -> dict[str, Event]:
        return self._events

    @property
    def log(self) -> list[ClusterOp]:
        return list(self._log)

    def event_of(self, article_id: str) -> str | None:
        return self._of_article.get(article_id)

    # --- assignment ---------------------------------------------------------

    def _candidate_event_ids(self, art: ArticleForEvent) -> set[str]:
        candidates: set[str] = set()
        for k in art.actor_keys:
            candidates |= self._by_actor.get(k, set())
        for r in art.region_ids:
            candidates |= self._by_region.get(r, set())
        return candidates

    def _gate(self, art: ArticleForEvent, ev: Event) -> bool:
        if abs(art.first_seen_hours - ev.last_seen_hours) > WINDOW_HOURS:
            return False
        shares_actor = bool(art.actor_keys & ev.actor_keys)
        shares_region = bool(art.region_ids & ev.region_ids)
        shares_topic = bool(art.topics & ev.topics)
        return shares_actor or (shares_region and shares_topic)

    def _score(self, art: ArticleForEvent, ev: Event) -> float:
        gap = abs(art.first_seen_hours - ev.last_seen_hours)
        time_score = max(0.0, 1.0 - gap / WINDOW_HOURS)
        score = (
            W_ACTOR * _jaccard(art.actor_keys, ev.actor_keys)
            + W_REGION * _jaccard(art.region_ids, ev.region_ids)
            + W_TOPIC * _jaccard(art.topics, ev.topics)
            + W_TIME * time_score
        )
        if self._similarity_fn is not None:
            score += W_EMBED * self._similarity_fn(art.title, ev.representative_title)
        return score

    def _index(self, ev: Event) -> None:
        for k in ev.actor_keys:
            self._by_actor.setdefault(k, set()).add(ev.event_id)
        for r in ev.region_ids:
            self._by_region.setdefault(r, set()).add(ev.event_id)

    def assign(self, art: ArticleForEvent) -> str:
        """Assign one article to the best matching event, or open a new one.

        Idempotent: re-assigning an already-seen article returns its event id
        without changing state (re-runs must not reshuffle, Prime Directive on
        stable IDs).
        """
        if art.article_id in self._of_article:
            return self._of_article[art.article_id]

        best_id: str | None = None
        best_score = JOIN_THRESHOLD
        for eid in sorted(self._candidate_event_ids(art)):
            ev = self._events[eid]
            if not self._gate(art, ev):
                continue
            s = self._score(art, ev)
            # Deterministic tie-break by event_id (sorted iteration above).
            if s > best_score:
                best_score = s
                best_id = eid

        if best_id is None:
            best_id = _event_id_for(art.article_id)
            self._events[best_id] = Event(event_id=best_id)

        ev = self._events[best_id]
        ev._absorb(art)
        self._index(ev)
        self._of_article[art.article_id] = best_id
        return best_id

    def assign_all(self, articles: Sequence[ArticleForEvent]) -> dict[str, str]:
        """Assign a batch in deterministic order (first_seen, then id)."""
        ordered = sorted(articles, key=lambda a: (a.first_seen_hours, a.article_id))
        return {a.article_id: self.assign(a) for a in ordered}

    # --- explicit, logged merge/split --------------------------------------

    def merge(self, event_id_a: str, event_id_b: str) -> ClusterOp:
        """Merge b into a (a survives). Logged. The surviving id is the earlier
        (smaller) event_id so the operation is deterministic and stable."""
        survivor, other = sorted((event_id_a, event_id_b))
        a, b = self._events[survivor], self._events.pop(other)
        moved = tuple(m.article_id for m in b.members)
        for m in b.members:
            a._absorb(m)
            self._of_article[m.article_id] = survivor
        b.status = "merged"
        self._index(a)
        # Repoint b's index entries to the survivor.
        for idx in (self._by_actor, self._by_region):
            for ids in idx.values():
                if other in ids:
                    ids.discard(other)
                    ids.add(survivor)
        op = ClusterOp("merge", survivor, other, moved)
        self._log.append(op)
        return op

    def split(self, event_id: str, article_ids: Sequence[str]) -> ClusterOp:
        """Split the given articles out of an event into a fresh stable-ID event."""
        src = self._events[event_id]
        moving = [m for m in src.members if m.article_id in set(article_ids)]
        if not moving:
            raise ValueError("no matching articles to split")
        new_id = _event_id_for(min(m.article_id for m in moving))
        new_ev = Event(event_id=new_id)
        for m in moving:
            new_ev._absorb(m)
            self._of_article[m.article_id] = new_id
        self._events[new_id] = new_ev
        self._index(new_ev)
        # Rebuild the source event from its remaining members.
        remaining = [m for m in src.members if m.article_id not in set(article_ids)]
        self._rebuild(src, remaining)
        op = ClusterOp("split", event_id, new_id, tuple(m.article_id for m in moving))
        self._log.append(op)
        return op

    def _rebuild(self, ev: Event, members: list[ArticleForEvent]) -> None:
        ev.members = []
        ev.actor_keys.clear()
        ev.region_ids.clear()
        ev.topics.clear()
        ev.first_seen_hours = ev.last_seen_hours = 0.0
        for m in members:
            ev._absorb(m)
        self._index(ev)


# ---------------------------------------------------------------------------
# Event views — timeline + source comparison (diversity over ORIGINS)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimelineEntry:
    article_id: str
    first_seen_hours: float    # from first_seen_by_us (trusted), never published_at
    title: str
    origin_source: str


def event_timeline(ev: Event) -> list[TimelineEntry]:
    """Chronological timeline from `first_seen_by_us` (DESIGN.md §7)."""
    return [
        TimelineEntry(
            article_id=m.article_id,
            first_seen_hours=m.first_seen_hours,
            title=m.title,
            origin_source=m.original_source,
        )
        for m in sorted(ev.members, key=lambda m: (m.first_seen_hours, m.article_id))
    ]


@dataclass(frozen=True)
class SourceComparison:
    distinct_origins: int
    first_source: str | None       # earliest-seen origin
    most_active_source: str | None  # origin contributing the most articles
    origin_article_counts: dict[str, int]


def event_sources(ev: Event) -> SourceComparison:
    """Source comparison counting distinct ORIGINS, never carriers (Prime
    Directive #1 / SPEC §4.7 source diversity)."""
    ordered = sorted(ev.members, key=lambda m: (m.first_seen_hours, m.article_id))
    counts: dict[str, int] = {}
    for m in ordered:
        counts[m.original_source] = counts.get(m.original_source, 0) + 1
    first_source = ordered[0].original_source if ordered else None
    most_active = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0] if counts else None
    return SourceComparison(
        distinct_origins=len(counts),
        first_source=first_source,
        most_active_source=most_active,
        origin_article_counts=counts,
    )

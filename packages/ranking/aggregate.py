"""aggregate.py — Build trend windows from article+enrichment rows (Layer A).

The bridge between stored data and the pure scorers: it projects each in-window
article (its syndication-resolved origin, age, and enrichment) into the
`TargetWindow` / `SourceWindow` shapes the scorers consume. Still pure — the
worker fetches rows and the fixed `now`, computes `age_hours`, and passes them
in (mirroring how the reference engine is fed).

Two invariants are honored here, not in the scorer:
- **origin, never carrier** — every mention's `original_source` is the resolved
  origin id, so diversity/volume/burst count distinct origins (Prime Directive
  #1);
- **reference_scale is a rolling P95** of recent raw scores, so normalized 0–100
  thresholds stay stable as volume grows (DESIGN.md §4).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from packages.ranking.actor import actor_importance, mention_weight
from packages.ranking.region import region_importance, region_mention_weight
from packages.ranking.source import SourceWindow
from packages.ranking.trending import (
    REFERENCE_SCALE,
    Mention,
    TargetWindow,
    TrendType,
)


@dataclass(frozen=True)
class ActorRef:
    key: str          # entity_id or NER canonical key
    name: str
    kind: str
    is_quoted: bool = False
    in_title: bool = False


@dataclass(frozen=True)
class RegionRef:
    region_id: str
    name: str
    region_type: str
    confidence: float


@dataclass(frozen=True)
class TopicRef:
    name: str


@dataclass(frozen=True)
class ArticleForTrending:
    """One article projected for trend aggregation, already origin-resolved."""

    article_id: str
    original_source: str   # resolved origin id (carrier→origin already applied)
    source_id: str         # the carrier this row arrived on
    source_name: str
    is_origin: bool        # is this row the origin of its content cluster?
    age_hours: float
    topics: Sequence[TopicRef]
    actors: Sequence[ActorRef]
    regions: Sequence[RegionRef]


def _baseline(baselines: dict[str, float], key: str) -> float:
    return baselines.get(key, 0.0)


def build_topic_windows(
    articles: Sequence[ArticleForTrending],
    baselines: dict[str, float] | None = None,
) -> list[TargetWindow]:
    baselines = baselines or {}
    grouped: dict[str, list[Mention]] = {}
    for a in articles:
        for t in a.topics:
            grouped.setdefault(t.name, []).append(
                Mention(original_source=a.original_source, age_hours=a.age_hours)
            )
    return [
        TargetWindow(
            target_id=name,
            target_type=TrendType.TOPIC,
            target_name=name,
            mentions=tuple(ms),
            baseline_mean=_baseline(baselines, name),
            importance=1.0,  # topics get no entity_importance (reference rule #3)
        )
        for name, ms in grouped.items()
    ]


def build_actor_windows(
    articles: Sequence[ArticleForTrending],
    baselines: dict[str, float] | None = None,
) -> list[TargetWindow]:
    baselines = baselines or {}
    grouped: dict[str, list[Mention]] = {}
    meta: dict[str, tuple[str, str]] = {}  # key -> (name, kind)
    for a in articles:
        for ar in a.actors:
            grouped.setdefault(ar.key, []).append(
                Mention(
                    original_source=a.original_source,
                    age_hours=a.age_hours,
                    weight_multiplier=mention_weight(
                        is_quoted=ar.is_quoted, in_title=ar.in_title
                    ),
                )
            )
            meta[ar.key] = (ar.name, ar.kind)
    return [
        TargetWindow(
            target_id=key,
            target_type=TrendType.ACTOR,
            target_name=meta[key][0],
            mentions=tuple(ms),
            baseline_mean=_baseline(baselines, key),
            importance=actor_importance(meta[key][1]),
        )
        for key, ms in grouped.items()
    ]


def build_region_windows(
    articles: Sequence[ArticleForTrending],
    baselines: dict[str, float] | None = None,
) -> list[TargetWindow]:
    baselines = baselines or {}
    grouped: dict[str, list[Mention]] = {}
    meta: dict[str, tuple[str, str]] = {}  # id -> (name, type)
    for a in articles:
        for rg in a.regions:
            grouped.setdefault(rg.region_id, []).append(
                Mention(
                    original_source=a.original_source,
                    age_hours=a.age_hours,
                    weight_multiplier=region_mention_weight(rg.confidence),
                )
            )
            meta[rg.region_id] = (rg.name, rg.region_type)
    return [
        TargetWindow(
            target_id=rid,
            target_type=TrendType.REGION,
            target_name=meta[rid][0],
            mentions=tuple(ms),
            baseline_mean=_baseline(baselines, rid),
            importance=region_importance(meta[rid][1]),
        )
        for rid, ms in grouped.items()
    ]


def build_source_windows(
    articles: Sequence[ArticleForTrending],
    baselines: dict[str, float] | None = None,
) -> list[SourceWindow]:
    baselines = baselines or {}
    ages: dict[str, list[float]] = {}
    original: dict[str, int] = {}
    names: dict[str, str] = {}
    for a in articles:
        ages.setdefault(a.source_id, []).append(a.age_hours)
        original[a.source_id] = original.get(a.source_id, 0) + (1 if a.is_origin else 0)
        names[a.source_id] = a.source_name
    return [
        SourceWindow(
            source_id=sid,
            source_name=names[sid],
            article_ages_hours=tuple(age_list),
            original_count=original.get(sid, 0),
            baseline_mean=_baseline(baselines, sid),
        )
        for sid, age_list in ages.items()
    ]


def reference_scale_p95(
    raw_scores: Sequence[float], fallback: float = REFERENCE_SCALE
) -> float:
    """Rolling P95 of recent raw scores (DESIGN.md §4). Falls back to the cold
    -start constant until enough history exists, and never returns a
    non-positive scale (`scale_score` requires > 0)."""
    positives = [s for s in raw_scores if s > 0]
    if len(positives) < 2:
        return fallback
    ordered = sorted(positives)
    # Nearest-rank P95.
    rank = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return max(ordered[rank], fallback * 0.1)

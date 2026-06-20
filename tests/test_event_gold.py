"""Event-clustering labeled-set gate (BUILD_ORDER Phase 4).

Scores the clusterer's partition against hand-labeled gold events on **same-event
article pairs** (the standard clustering P/R), and pins ID stability across
re-runs. A change that starts false-merging (e.g. joining on shared region alone)
drops precision; one that fragments a real event drops recall — either fails CI.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

from packages.clustering.event_clusterer import ArticleForEvent, EventClusterer

_FIX = Path(__file__).resolve().parent / "fixtures" / "event_gold" / "articles.json"


def _load() -> dict:
    return json.loads(_FIX.read_text(encoding="utf-8"))


def _articles(spec: dict) -> list[ArticleForEvent]:
    return [
        ArticleForEvent(
            article_id=a["id"],
            first_seen_hours=a["hours"],
            original_source=a["origin"],
            actor_keys=frozenset(a["actors"]),
            region_ids=frozenset(a["regions"]),
            topics=frozenset(a["topics"]),
            title=a["id"],
        )
        for a in spec["articles"]
    ]


def _pair_pr(spec: dict) -> tuple[float, float]:
    arts = _articles(spec)
    assigned = EventClusterer().assign_all(arts)
    gold = {a["id"]: a["event"] for a in spec["articles"]}
    ids = [a["id"] for a in spec["articles"]]
    tp = fp = fn = 0
    for x, y in combinations(ids, 2):
        same_pred = assigned[x] == assigned[y]
        same_gold = gold[x] == gold[y]
        if same_pred and same_gold:
            tp += 1
        elif same_pred and not same_gold:
            fp += 1
        elif not same_pred and same_gold:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return precision, recall


def test_same_event_pair_precision_recall() -> None:
    spec = _load()
    precision, recall = _pair_pr(spec)
    th = spec["thresholds"]
    assert precision >= th["precision"], f"event precision {precision:.3f} < {th['precision']}"
    assert recall >= th["recall"], f"event recall {recall:.3f} < {th['recall']}"


def test_partition_is_stable_across_reruns() -> None:
    spec = _load()
    arts = _articles(spec)
    first = EventClusterer().assign_all(arts)
    second = EventClusterer().assign_all(arts)
    assert first == second


def test_region_without_topic_does_not_merge() -> None:
    # mp1 shares region reg_medan with the flood event but a different topic.
    spec = _load()
    assigned = EventClusterer().assign_all(_articles(spec))
    assert assigned["mp1"] != assigned["f1"]


def test_same_actor_outside_window_splits_into_two_events() -> None:
    spec = _load()
    assigned = EventClusterer().assign_all(_articles(spec))
    assert assigned["k1"] != assigned["k4"]  # >48h apart

"""NLP gold-set regression gate (BUILD_ORDER Phase 2).

Loads the hand-labeled corpus in `tests/fixtures/nlp_gold/` and asserts each
extractor meets a per-extractor precision/recall floor. A change that drops
quote/actor/region/topic quality below threshold fails CI — exactly the
"a merge that drops quote precision fails CI" discipline from CLAUDE.md §6.

The seed corpus is intentionally small but real; it is structured to grow toward
the ~300–500 labeled articles the spec calls for without changing this harness.
Thresholds are set below currently-observed scores so the gate flags genuine
regressions, not noise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from packages.nlp.enrich import build_enricher, enrich_article

_GOLD = Path(__file__).resolve().parent / "fixtures" / "nlp_gold" / "articles.json"
_ENR = build_enricher()

# Per-extractor (precision_floor, recall_floor). Set with margin below observed.
_THRESHOLDS = {
    "topics": (0.50, 0.85),
    "actors": (0.85, 0.85),
    "regions": (0.80, 0.85),
    "quotes": (0.80, 0.85),
}


@dataclass
class PR:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, predicted: set[str], expected: set[str]) -> None:
        self.tp += len(predicted & expected)
        self.fp += len(predicted - expected)
        self.fn += len(expected - predicted)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0


def _metrics() -> dict[str, PR]:
    gold = json.loads(_GOLD.read_text(encoding="utf-8"))
    m = {k: PR() for k in _THRESHOLDS}
    for g in gold:
        e = enrich_article(
            article_id=g["id"],
            title=g["title"],
            excerpt=g["excerpt"],
            raw_category=g["category"],
            source_url=f"https://news.example.id/{g['id']}",
            enricher=_ENR,
        )
        m["topics"].add({t.topic for t in e.topics}, set(g["topics"]))
        m["actors"].add({a.entity_id for a in e.actors if a.entity_id}, set(g["actors"]))
        m["regions"].add({r.region_id for r in e.regions}, set(g["regions"]))
        m["quotes"].add(
            {q.speaker_entity_id for q in e.quotes if q.speaker_entity_id and q.exposable},
            set(g["quote_speakers"]),
        )
    return m


def test_gold_set_has_minimum_size() -> None:
    gold = json.loads(_GOLD.read_text(encoding="utf-8"))
    assert len(gold) >= 16


def test_topic_precision_recall() -> None:
    pr = _metrics()["topics"]
    p_floor, r_floor = _THRESHOLDS["topics"]
    assert pr.precision >= p_floor, f"topic precision {pr.precision:.3f} < {p_floor}"
    assert pr.recall >= r_floor, f"topic recall {pr.recall:.3f} < {r_floor}"


def test_actor_precision_recall() -> None:
    pr = _metrics()["actors"]
    p_floor, r_floor = _THRESHOLDS["actors"]
    assert pr.precision >= p_floor, f"actor precision {pr.precision:.3f} < {p_floor}"
    assert pr.recall >= r_floor, f"actor recall {pr.recall:.3f} < {r_floor}"


def test_region_precision_recall() -> None:
    pr = _metrics()["regions"]
    p_floor, r_floor = _THRESHOLDS["regions"]
    assert pr.precision >= p_floor, f"region precision {pr.precision:.3f} < {p_floor}"
    assert pr.recall >= r_floor, f"region recall {pr.recall:.3f} < {r_floor}"


def test_quote_precision_recall() -> None:
    pr = _metrics()["quotes"]
    p_floor, r_floor = _THRESHOLDS["quotes"]
    assert pr.precision >= p_floor, f"quote precision {pr.precision:.3f} < {p_floor}"
    assert pr.recall >= r_floor, f"quote recall {pr.recall:.3f} < {r_floor}"

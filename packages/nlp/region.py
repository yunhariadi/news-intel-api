"""region.py — Region extraction with confidence (Layer A).

Gazetteer-backed (the same precision-tuned matcher as `gazetteer.py`) over the
Indonesian province/city list in `packages/db/gazetteer/regions.json`, with a
bounded confidence per DESIGN.md §5 / BUILD_ORDER Phase 2:

- **title boost** — a region named in the title is far more likely the story's
  locus than one mentioned in passing;
- **incident-word boost** — a region immediately after a locational preposition
  (`di Surabaya`, `wilayah Papua`) is a stronger geographic signal than a bare
  name (which might be a person's surname or an org fragment).

Confidence is clamped to [0,1]. The matcher is pure; only `load_regions` does
I/O. Region rows feed `article_regions(confidence)` (SPEC §10.7).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from packages.nlp.gazetteer import Gazetteer

_GAZ_DIR = Path(__file__).resolve().parents[1] / "db" / "gazetteer"

# Calibration knobs.
_BASE: float = 0.5
_TITLE_BOOST: float = 0.3
_INCIDENT_BOOST: float = 0.15
_REPEAT_BOOST: float = 0.05  # per additional body mention, capped

# Locational prepositions/nouns that, immediately preceding a region, mark it as
# the place an event happened rather than an incidental reference.
_LOC_WORDS: frozenset[str] = frozenset({
    "di", "ke", "dari", "wilayah", "kawasan", "daerah", "provinsi",
    "kabupaten", "kota", "menuju", "sekitar",
})

_PRECEDING_WORD = re.compile(r"(\w+)\s*$")


@dataclass(frozen=True)
class RegionScore:
    region_id: str
    name: str
    region_type: str
    confidence: float


def load_regions(path: Path | None = None) -> Gazetteer:
    """Load regions.json and adapt it to the gazetteer entry shape (I/O)."""
    raw = json.loads((path or (_GAZ_DIR / "regions.json")).read_text(encoding="utf-8"))
    entries: list[dict[str, object]] = [
        {
            "entity_id": r["region_id"],
            "canonical_name": r["name"],
            "entity_type": r["region_type"],
            "acronyms": [],
            "aliases": r.get("aliases", []),
        }
        for r in raw
    ]
    return Gazetteer(entries)


def _has_incident_cue(text: str, start: int) -> bool:
    m = _PRECEDING_WORD.search(text[:start])
    return m is not None and m.group(1).lower() in _LOC_WORDS


def _clamp(x: float) -> float:
    return round(min(1.0, max(0.0, x)), 4)


def extract_regions(title: str, body: str, gazetteer: Gazetteer) -> list[RegionScore]:
    """Rank regions for an article by bounded confidence.

    A region's confidence is the best single-mention score (base + title +
    incident boosts) plus a small bonus for repeated body mentions, clamped to
    1.0. Sorted by confidence desc, then name for determinism.
    """
    best: dict[str, float] = {}
    meta: dict[str, tuple[str, str]] = {}
    body_counts: dict[str, int] = {}

    for in_title, text in ((True, title), (False, body)):
        for men in gazetteer.find_mentions(text):
            score = _BASE
            if in_title:
                score += _TITLE_BOOST
            if _has_incident_cue(text, men.start):
                score += _INCIDENT_BOOST
            best[men.entity_id] = max(best.get(men.entity_id, 0.0), score)
            meta[men.entity_id] = (men.canonical_name, men.entity_type)
            if not in_title:
                body_counts[men.entity_id] = body_counts.get(men.entity_id, 0) + 1

    scores: list[RegionScore] = []
    for rid, base_conf in best.items():
        extra = max(0, body_counts.get(rid, 0) - 1)
        conf = _clamp(base_conf + min(extra, 3) * _REPEAT_BOOST)
        name, rtype = meta[rid]
        scores.append(RegionScore(region_id=rid, name=name, region_type=rtype, confidence=conf))

    scores.sort(key=lambda r: (-r.confidence, r.name))
    return scores

"""region.py — Region trend importance + per-mention weighting (Layer A).

Supplies the `importance` (incident_weight) and per-mention `weight_multiplier`
the type-agnostic `trending.py` scorer needs for **regions** (SPEC §4.4 trending
regions / regional heat).

- `region_importance(region_type)` — a more specific locus is a stronger signal
  that something actually *happened there*: a city/regency dateline localizes an
  incident, while a country-level mention is often just scope. So city/regency
  weigh above province above country. Bounded to the reference's band.
- `region_mention_weight(confidence)` — the region extractor's per-article
  confidence (title/incident-word boosted) rides on the mention weight, so a
  region named in a headline with a locational cue outweighs an incidental one.

Pure and bounded.
"""

from __future__ import annotations

# incident_weight by region_type. More specific = more newsworthy locus.
REGION_IMPORTANCE_BY_TYPE: dict[str, float] = {
    "country": 1.0,
    "province": 1.15,
    "city": 1.3,
    "regency": 1.3,
    "district": 1.4,
}
_DEFAULT_IMPORTANCE: float = 1.0
_MAX_IMPORTANCE: float = 1.5


def region_importance(region_type: str) -> float:
    """incident_weight for a region of the given type, bounded."""
    return min(REGION_IMPORTANCE_BY_TYPE.get(region_type, _DEFAULT_IMPORTANCE), _MAX_IMPORTANCE)


def region_mention_weight(confidence: float) -> float:
    """Per-mention weight from the extractor's region confidence, in [0.5, 1.5].

    Linear in confidence so a high-confidence headline locus (~1.0) weighs ~1.5
    and a weak passing mention (~0.5) weighs ~1.0; clamped so a zero-confidence
    artifact still contributes a little rather than vanishing or dominating.
    """
    return max(0.5, min(0.5 + confidence, 1.5))

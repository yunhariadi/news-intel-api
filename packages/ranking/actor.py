"""actor.py — Actor trend importance + per-mention weighting (Layer A).

The composite scorer in `trending.py` is type-agnostic: it takes an `importance`
per target and a `weight_multiplier` per mention. This module supplies those for
**actors**, so the same bounded, syndication-aware engine ranks trending actors
(SPEC §4.3) without a second formula.

- `actor_importance(kind)` — entity_importance in the reference's 1.0–2.0 band,
  by gazetteer entity type. Institutions that set the agenda (regulators,
  ministries) weigh above individual persons; unknown kinds fall back to 1.0.
- `mention_weight(is_quoted, in_title)` — the role/quote weighting the reference
  parks on `Mention.weight_multiplier`: an actor who is *quoted* or named in the
  *title* is more central to the story than one mentioned in passing.

Pure and bounded: importance ∈ [1.0, 2.0], mention weight ∈ [1.0, ~2.0].
"""

from __future__ import annotations

# entity_importance by gazetteer entity_type. Calibration knobs.
ACTOR_IMPORTANCE_BY_KIND: dict[str, float] = {
    "REGULATOR": 1.5,
    "MINISTRY": 1.5,
    "AGENCY": 1.4,
    "COURT": 1.4,
    "LEGISLATURE": 1.3,
    "PARTY": 1.2,
    "SOE": 1.2,
    "PERSON": 1.2,
}
_DEFAULT_IMPORTANCE: float = 1.0
_MAX_IMPORTANCE: float = 2.0

# Per-mention role/quote multipliers.
_QUOTE_WEIGHT: float = 1.5   # a quoted actor is central to the story
_TITLE_WEIGHT: float = 1.3   # a title mention outweighs a body mention


def actor_importance(kind: str) -> float:
    """entity_importance for an actor of the given gazetteer kind, in [1.0, 2.0]."""
    return min(ACTOR_IMPORTANCE_BY_KIND.get(kind, _DEFAULT_IMPORTANCE), _MAX_IMPORTANCE)


def mention_weight(*, is_quoted: bool = False, in_title: bool = False) -> float:
    """role_weight * quote_weight for one actor mention (>= 1.0)."""
    weight = 1.0
    if is_quoted:
        weight *= _QUOTE_WEIGHT
    if in_title:
        weight *= _TITLE_WEIGHT
    return weight

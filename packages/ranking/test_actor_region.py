"""Gate for actor.py / region.py — importance + mention weighting bounds."""

from __future__ import annotations

from packages.ranking.actor import actor_importance, mention_weight
from packages.ranking.region import region_importance, region_mention_weight


def test_actor_importance_band() -> None:
    assert actor_importance("REGULATOR") == 1.5
    assert actor_importance("PERSON") == 1.2
    assert actor_importance("UNKNOWN_KIND") == 1.0
    assert all(1.0 <= actor_importance(k) <= 2.0 for k in
               ["REGULATOR", "MINISTRY", "PARTY", "SOE", "COURT", "PERSON", "x"])


def test_institution_outweighs_person() -> None:
    assert actor_importance("REGULATOR") > actor_importance("PERSON")


def test_mention_weight_quote_and_title() -> None:
    assert mention_weight() == 1.0
    assert mention_weight(is_quoted=True) > 1.0
    assert mention_weight(in_title=True) > 1.0
    assert mention_weight(is_quoted=True, in_title=True) > mention_weight(is_quoted=True)


def test_region_importance_specificity() -> None:
    assert region_importance("city") > region_importance("province")
    assert region_importance("province") > region_importance("country")
    assert all(1.0 <= region_importance(t) <= 1.5 for t in
               ["country", "province", "city", "regency", "district", "x"])


def test_region_mention_weight_monotone_and_bounded() -> None:
    assert region_mention_weight(0.0) == 0.5
    assert region_mention_weight(1.0) == 1.5
    assert region_mention_weight(5.0) == 1.5  # clamped
    assert region_mention_weight(0.8) > region_mention_weight(0.3)

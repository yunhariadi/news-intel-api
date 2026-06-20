"""test_invariants.py — CI gate for the compliance predicates.

Pins the COMPLIANCE.md §6 table (P1, P2, P4, PR2, I1, I2, I3, C1). A change that
lets an exonerated suspect's label, a suppressed entity, an unverifiable quote,
a synthetic verbatim, an unattributed item, or an over-long excerpt through must
turn one of these red.

Run: pytest -q test_invariants.py
"""

from __future__ import annotations

from packages.compliance.invariants import (
    MAX_EXCERPT_CHARS,
    QUOTE_CONFIDENCE_FLOOR,
    AttributionStatus,
    EntityView,
    LegalStatus,
    NewsItemView,
    QuoteForm,
    QuoteView,
    cap_excerpt,
    has_required_attribution,
    is_entity_exposable,
    is_excerpt_within_cap,
    is_label_exposable,
    is_quote_exposable,
)


def _quote(**kw: object) -> QuoteView:
    base: dict[str, object] = {
        "quote_id": "q1",
        "confidence": 0.9,
        "attribution_status": AttributionStatus.AS_PUBLISHED,
        "source_paragraph_url": "https://example.id/article#p3",
        "served_as": QuoteForm.VERBATIM,
    }
    base.update(kw)
    return QuoteView(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# P1 — suspect lifecycle / presumption of innocence
# --------------------------------------------------------------------------

def test_p1_accusatory_label_exposable_while_case_live() -> None:
    assert is_label_exposable(LegalStatus.TERSANGKA, LegalStatus.TERSANGKA) is True
    assert is_label_exposable(LegalStatus.TERDAKWA, LegalStatus.TERDAKWA) is True


def test_p1_accusatory_label_unexposable_after_acquittal() -> None:
    # The headline invariant: acquittal/SP3 makes the prior suspect label vanish.
    assert is_label_exposable(LegalStatus.TERSANGKA, LegalStatus.BEBAS) is False
    assert is_label_exposable(LegalStatus.TERDAKWA, LegalStatus.SP3) is False


def test_p1_nonaccusatory_label_always_exposable() -> None:
    assert is_label_exposable(LegalStatus.SAKSI, LegalStatus.BEBAS) is True
    assert is_label_exposable(LegalStatus.TERPIDANA, LegalStatus.TERPIDANA) is True
    assert is_label_exposable(None, LegalStatus.BEBAS) is True


# --------------------------------------------------------------------------
# P2 / P4 — data-subject rights & protected persons
# --------------------------------------------------------------------------

def test_p2_suppressed_entity_never_exposable() -> None:
    e = EntityView("e1", legal_status=LegalStatus.TERPIDANA, suppressed=True)
    assert is_entity_exposable(e) is False


def test_p4_minor_and_sensitive_victim_never_exposable() -> None:
    assert is_entity_exposable(EntityView("m", is_minor=True)) is False
    assert is_entity_exposable(EntityView("v", is_sensitive_victim=True)) is False


def test_p1_through_entity_exposable_drops_exonerated() -> None:
    cleared = EntityView("e2", legal_status=LegalStatus.BEBAS)
    assert is_entity_exposable(cleared) is True  # status itself is non-accusatory
    still_accused = EntityView("e3", legal_status=LegalStatus.TERSANGKA)
    assert is_entity_exposable(still_accused) is True


# --------------------------------------------------------------------------
# I1 / I2 / I3 — quote safety
# --------------------------------------------------------------------------

def test_i1_quote_below_confidence_floor_not_exposable() -> None:
    assert is_quote_exposable(_quote(confidence=QUOTE_CONFIDENCE_FLOOR - 0.01)) is False
    assert is_quote_exposable(_quote(confidence=QUOTE_CONFIDENCE_FLOOR)) is True


def test_i2_quote_without_source_paragraph_url_not_exposable() -> None:
    assert is_quote_exposable(_quote(source_paragraph_url=None)) is False
    assert is_quote_exposable(_quote(source_paragraph_url="")) is False


def test_i3_inferred_attribution_not_served_as_verbatim() -> None:
    inferred_verbatim = _quote(
        attribution_status=AttributionStatus.INFERRED, served_as=QuoteForm.VERBATIM
    )
    assert is_quote_exposable(inferred_verbatim) is False
    # …but an inferred quote presented as a paraphrase is fine.
    inferred_paraphrase = _quote(
        attribution_status=AttributionStatus.INFERRED, served_as=QuoteForm.PARAPHRASE
    )
    assert is_quote_exposable(inferred_paraphrase) is True


# --------------------------------------------------------------------------
# PR2 — attribution + link-back
# --------------------------------------------------------------------------

def test_pr2_item_requires_source_and_url() -> None:
    assert has_required_attribution(NewsItemView("Kompas", "https://kompas.id/x")) is True
    assert has_required_attribution(NewsItemView(None, "https://kompas.id/x")) is False
    assert has_required_attribution(NewsItemView("Kompas", None)) is False
    assert has_required_attribution(NewsItemView("", "")) is False


# --------------------------------------------------------------------------
# C1 — excerpt cap
# --------------------------------------------------------------------------

def test_c1_excerpt_cap_enforced() -> None:
    assert is_excerpt_within_cap("x" * MAX_EXCERPT_CHARS) is True
    assert is_excerpt_within_cap("x" * (MAX_EXCERPT_CHARS + 1)) is False
    assert is_excerpt_within_cap(None) is True


def test_c1_cap_excerpt_truncates_at_write_time() -> None:
    capped = cap_excerpt("x" * (MAX_EXCERPT_CHARS + 50))
    assert capped is not None
    assert len(capped) == MAX_EXCERPT_CHARS
    assert is_excerpt_within_cap(capped) is True
    assert cap_excerpt(None) is None

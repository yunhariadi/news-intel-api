"""invariants.py — Compliance predicates for news-intel-api (Layer A).

Prime Directive #5: the rules in COMPLIANCE.md are *code, not comments*. This
module implements them as pure predicates and is pinned by
`test_invariants.py`. They run inside the API serialization path, so a row that
violates them cannot be returned even if it exists in the database.

Pure: no I/O, no clocks, no network. Inputs are frozen dataclasses; the worker /
API layer constructs them from DB rows and passes them in. Each predicate maps
to a row in the COMPLIANCE.md §6 table (P1, P2, P4, PR2, I1, I2, I3, C1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Enums / vocab
# ---------------------------------------------------------------------------


class LegalStatus(str, Enum):
    """Indonesian criminal-process lifecycle (DESIGN.md §2.4)."""

    TERLAPOR = "terlapor"      # reported
    SAKSI = "saksi"            # witness
    TERSANGKA = "tersangka"    # suspect (accusatory)
    TERDAKWA = "terdakwa"      # defendant (accusatory)
    TERPIDANA = "terpidana"    # convict
    BEBAS = "bebas"            # acquitted
    SP3 = "sp3"                # case dropped


# Labels that assert guilt/suspicion and must not survive exoneration.
ACCUSATORY_LABELS: frozenset[LegalStatus] = frozenset(
    {LegalStatus.TERSANGKA, LegalStatus.TERDAKWA}
)

# Terminal outcomes that clear an accusatory label.
EXONERATING_STATUSES: frozenset[LegalStatus] = frozenset(
    {LegalStatus.BEBAS, LegalStatus.SP3}
)


class AttributionStatus(str, Enum):
    AS_PUBLISHED = "as_published"  # verbatim from source text
    INFERRED = "inferred"          # reconstructed / paraphrased — never verbatim


class QuoteForm(str, Enum):
    VERBATIM = "verbatim"
    PARAPHRASE = "paraphrase"


# Default confidence floor (I1). Mirrors QUOTE_CONFIDENCE_FLOOR in .env.example;
# the API passes the configured value, this is the cold-start fallback.
QUOTE_CONFIDENCE_FLOOR: float = 0.75

# Default excerpt cap (C1). Mirrors MAX_EXCERPT_CHARS in .env.example.
MAX_EXCERPT_CHARS: int = 300


# ---------------------------------------------------------------------------
# Typed inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityView:
    """The compliance-relevant projection of an entity row."""

    entity_id: str
    legal_status: LegalStatus | None = None
    suppressed: bool = False        # P2: erasure/rectification tombstone
    is_minor: bool = False          # P4
    is_sensitive_victim: bool = False  # P4 (e.g. victim of a sexual offence)


@dataclass(frozen=True)
class QuoteView:
    """The compliance-relevant projection of a quote row."""

    quote_id: str
    confidence: float
    attribution_status: AttributionStatus
    source_paragraph_url: str | None
    served_as: QuoteForm  # how the caller intends to present it


@dataclass(frozen=True)
class NewsItemView:
    """The compliance-relevant projection of any serialized news item."""

    source_name: str | None
    origin_url: str | None
    excerpt: str | None = None


# ---------------------------------------------------------------------------
# P1 — Suspect lifecycle / presumption of innocence
# ---------------------------------------------------------------------------


def is_label_exposable(status: LegalStatus | None, current_status: LegalStatus | None) -> bool:
    """P1: an accusatory label (`tersangka`/`terdakwa`) is exposable only if the
    actor's *current* status has not reached exoneration (`bebas`/`sp3`).

    `status` is the label being considered for display; `current_status` is the
    actor's latest known status. A non-accusatory label is always exposable.
    """
    if status not in ACCUSATORY_LABELS:
        return True
    return current_status not in EXONERATING_STATUSES


# ---------------------------------------------------------------------------
# P2 / P4 — Data-subject rights & protected persons
# ---------------------------------------------------------------------------


def is_entity_exposable(entity: EntityView) -> bool:
    """P2 + P4: a suppressed entity, a minor, or a sensitive victim is never an
    exposable (queryable) actor, and any current accusatory label must still
    pass P1."""
    if entity.suppressed:
        return False
    if entity.is_minor or entity.is_sensitive_victim:
        return False
    return is_label_exposable(entity.legal_status, entity.legal_status)


# ---------------------------------------------------------------------------
# I1 / I2 / I3 — Quote safety (defamation, verifiability, no synthetic verbatim)
# ---------------------------------------------------------------------------


def is_quote_exposable(
    quote: QuoteView, confidence_floor: float = QUOTE_CONFIDENCE_FLOOR
) -> bool:
    """A quote is exposable only if ALL hold:

    - I1: confidence at or above the floor;
    - I2: it carries a non-empty `source_paragraph_url` (deep-link verifiable);
    - I3: it is not presented as verbatim unless attribution is `as_published`
      (Layer B paraphrase may never be served inside quotation marks).
    """
    if quote.confidence < confidence_floor:
        return False
    if not quote.source_paragraph_url:
        return False
    # I3: a verbatim-presented quote must be `as_published`.
    return not (
        quote.served_as is QuoteForm.VERBATIM
        and quote.attribution_status is not AttributionStatus.AS_PUBLISHED
    )


# ---------------------------------------------------------------------------
# PR2 — Mandatory attribution + link-back
# ---------------------------------------------------------------------------


def has_required_attribution(item: NewsItemView) -> bool:
    """PR2: every serialized news item carries an origin source name AND url."""
    return bool(item.source_name) and bool(item.origin_url)


# ---------------------------------------------------------------------------
# C1 — Excerpt cap
# ---------------------------------------------------------------------------


def is_excerpt_within_cap(excerpt: str | None, max_chars: int = MAX_EXCERPT_CHARS) -> bool:
    """C1: stored/served excerpts are hard-capped. None/empty is fine."""
    if excerpt is None:
        return True
    return len(excerpt) <= max_chars


def cap_excerpt(excerpt: str | None, max_chars: int = MAX_EXCERPT_CHARS) -> str | None:
    """C1 at write time: truncate to the cap so an over-long excerpt can never
    be persisted. Returns None unchanged."""
    if excerpt is None:
        return None
    return excerpt[:max_chars]

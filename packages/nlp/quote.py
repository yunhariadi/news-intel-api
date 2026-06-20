"""quote.py — High-precision quote extraction (Layer A).

This is the most compliance-sensitive extractor: a paid API attributing a
distorted or misattributed statement to a named person is a defamation (ITE)
exposure, so the rules are precision-first and every output carries the fields
the compliance gate (I1/I2/I3) checks.

Handled patterns (DESIGN.md §5 — including the cases the SPEC glosses over):
- **trailing**  `"…", kata X`            (say-verb + named speaker)
- **leading**   `X menegaskan bahwa "…"` (named speaker + verb + quote)
- **split**     `"X," kata Y, "Z."`      (one statement, fragments rejoined)
- **continuation / pronoun**  `"…", katanya` / `Ia menambahkan, "…"` — the
  speaker is a pronoun (`Ia`, `Dia`, `Beliau`) or the `-nya` clitic, resolved to
  the **last named speaker**; such attributions are flagged `speaker_inferred`
  and scored lower.

Provenance/compliance:
- the quote TEXT is always verbatim from source, so `attribution_status` is
  `as_published` (the extractor never fabricates verbatim text — that's the I3
  line Layer B may not cross);
- every quote gets a `source_paragraph_url` deep link (I2), built as a W3C text
  fragment so a reader lands on the exact sentence;
- `exposable` is precomputed against the confidence floor (I1) and the presence
  of that link (I2). Below the floor → never served.

Pure: text + source URL + gazetteer in, `Quote`s out. No I/O, no clock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote as urlquote

from packages.compliance.invariants import QUOTE_CONFIDENCE_FLOOR
from packages.nlp.actor import strip_gelar
from packages.nlp.gazetteer import Gazetteer

# Verbs that trail a quote: `"…", kata X`.
_SAY_VERBS = (
    "kata", "ujar", "tutur", "ungkap", "jelas", "tegas", "sebut", "papar",
    "imbuh", "tambah", "terang", "ucap", "pungkas", "lanjut", "tanya",
)
# Verbs in the leading form: `X mengatakan, "…"`.
_LEAD_VERBS = (
    "mengatakan", "menegaskan", "menyebutkan", "menjelaskan", "mengungkapkan",
    "menuturkan", "memaparkan", "menambahkan", "menerangkan", "mengucapkan",
    "menyatakan", "mengingatkan", "menyampaikan", "membantah", "mengklaim",
)
_PRONOUNS = frozenset({"ia", "dia", "beliau", "nya"})

# No '.' in the class: a name must not swallow a sentence-ending period (that
# would merge across sentence boundaries). Gelar like "Dr." is stripped later.
_NAME = r"[A-Z][a-zA-Z'\-]*(?:\s+[A-Z][a-zA-Z'\-]*){0,3}"
_SAY = "|".join(_SAY_VERBS)
_LEAD = "|".join(_LEAD_VERBS)

# After a closing quote: optional comma, a say-verb (+optional -nya clitic),
# then either a named speaker or nothing (pronoun/continuation).
_TRAIL = re.compile(
    rf'^\s*[,.]?\s*(?:(?P<verb>{_SAY})(?P<nya>nya)?)\s*(?P<who>{_NAME})?'
)
# Before an opening quote: a named speaker (or pronoun) + a leading verb.
_LEAD_RE = re.compile(
    rf'(?P<who>{_NAME}|Ia|Dia|Beliau)\s+(?:{_LEAD})\s*(?:bahwa)?\s*[,:]?\s*$'
)
# A pronoun-led continuation before an opening quote: `Ia menambahkan, "…"`.
_QUOTE_SPAN = re.compile(r'"([^"]{2,})"')

# Confidence knobs.
_C_NAMED: float = 0.85
_C_GAZ_BONUS: float = 0.1
_C_INFERRED: float = 0.7
_C_UNKNOWN: float = 0.4


@dataclass(frozen=True)
class Quote:
    quote_text: str
    speaker_display: str | None
    speaker_entity_id: str | None
    speaker_inferred: bool          # speaker resolved via pronoun/continuation
    confidence: float
    attribution_status: str         # always "as_published" from the extractor
    method: str                     # trailing | leading | split | continuation
    source_paragraph_url: str
    exposable: bool


def _is_pronoun(token: str | None) -> bool:
    return bool(token) and token.strip().lower() in _PRONOUNS  # type: ignore[union-attr]


def _resolve_speaker(raw: str | None, gz: Gazetteer) -> tuple[str | None, str | None]:
    """(display, entity_id) for a raw speaker name. Gazetteer hit is
    authoritative; otherwise the gelar-stripped surface is the display."""
    if not raw:
        return None, None
    hits = gz.find_mentions(raw)
    if hits:
        return hits[0].canonical_name, hits[0].entity_id
    display = strip_gelar(raw.strip())
    return (display or None), None


def _deep_link(source_url: str, quote_text: str) -> str:
    """W3C text-fragment deep link to the sentence (I2 verifiability)."""
    snippet = " ".join(quote_text.split()[:8])
    return f"{source_url}#:~:text={urlquote(snippet)}"


def _score(named: bool, resolved_entity: bool, inferred: bool) -> float:
    if inferred:
        return round(_C_INFERRED, 4)
    if not named:
        return round(_C_UNKNOWN, 4)
    return round(min(_C_NAMED + (_C_GAZ_BONUS if resolved_entity else 0.0), 0.95), 4)


def extract_quotes(
    text: str,
    source_url: str,
    gazetteer: Gazetteer,
    confidence_floor: float = QUOTE_CONFIDENCE_FLOOR,
) -> list[Quote]:
    """Extract attributed quotes from `text`.

    Single left-to-right pass over quote spans, tracking the last named speaker
    so pronoun/`-nya` continuations resolve correctly. Split quotes consume the
    following span and rejoin the fragments.
    """
    spans = list(_QUOTE_SPAN.finditer(text))
    quotes: list[Quote] = []
    last_speaker: tuple[str | None, str | None] = (None, None)
    i = 0
    while i < len(spans):
        span = spans[i]
        inner = span.group(1).strip()
        left = text[: span.start()]
        right = text[span.end() :]

        speaker_display: str | None = None
        entity_id: str | None = None
        inferred = False
        named = False
        method = "trailing"

        trail = _TRAIL.match(right)
        lead = _LEAD_RE.search(left)

        if trail and (trail.group("who") or trail.group("nya")):
            who = trail.group("who")
            if trail.group("nya") or _is_pronoun(who):
                speaker_display, entity_id = last_speaker
                inferred = True
                method = "continuation"
            else:
                speaker_display, entity_id = _resolve_speaker(who, gazetteer)
                named = speaker_display is not None
            # Split quote: `"q1," verb Speaker, "q2"` — rejoin fragments. The
            # separator must be a comma (a period would be a new sentence).
            rest = right[trail.end() :]
            split = re.match(r'\s*,\s*"([^"]{2,})"', rest)
            if split and not inferred:
                inner = f"{inner.rstrip(' ,.')} {split.group(1).strip()}"
                method = "split"
                i += 1  # consume the second fragment's span
        elif lead:
            who = lead.group("who")
            if _is_pronoun(who):
                speaker_display, entity_id = last_speaker
                inferred = True
                method = "continuation"
            else:
                speaker_display, entity_id = _resolve_speaker(who, gazetteer)
                named = speaker_display is not None
                method = "leading"
        else:
            # Bare quote with no adjacent attribution — unknown speaker.
            method = "trailing"

        if named and not inferred:
            last_speaker = (speaker_display, entity_id)

        # Indonesian style puts the joining comma inside the quotes; drop a
        # single trailing comma but keep a sentence-final period.
        inner = inner.strip()
        if inner.endswith(","):
            inner = inner[:-1].rstrip()

        confidence = _score(named, entity_id is not None, inferred)
        url = _deep_link(source_url, inner)
        exposable = confidence >= confidence_floor and bool(url) and bool(speaker_display)
        quotes.append(
            Quote(
                quote_text=inner,
                speaker_display=speaker_display,
                speaker_entity_id=entity_id,
                speaker_inferred=inferred,
                confidence=confidence,
                attribution_status="as_published",
                method=method,
                source_paragraph_url=url,
                exposable=exposable,
            )
        )
        i += 1
    return quotes

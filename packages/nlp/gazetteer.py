"""gazetteer.py — Gazetteer-backed entity matching (Layer A core + a thin loader).

DESIGN.md §5: "the gazetteer is the backbone, not NER." Off-the-shelf NER yields
PERSON/ORG/LOC and will never label MINISTRY/REGULATOR/SOE/COURT/PARTY — exactly
the high-value Indonesian types. So a curated, version-controlled list in
`packages/db/gazetteer/` is the primary signal; NER (see `actor.py`) is the
fallback for unknown names.

The matcher (`Gazetteer.find_mentions`) is **pure** — it operates on an
in-memory gazetteer object with no I/O. Only `load_organizations` touches the
filesystem; the worker calls it once at startup and passes the built gazetteer
into the pure path (mirroring how the trending worker fetches state and passes
it into the pure scorer).

Matching rules tuned for precision (a paid API must not misattribute):
- full names / lowercase aliases match case-insensitively, word-bounded;
- ACRONYMS match only when they appear uppercase in the source text, so "BI"
  the regulator is found but "bi" inside prose is not;
- the longest mention wins when spans overlap;
- a surface form that resolves to more than one entity is **ambiguous** and is
  dropped at build time rather than guessed (precision over recall).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_GAZ_DIR = Path(__file__).resolve().parents[1] / "db" / "gazetteer"


def _str_list(value: object) -> list[str]:
    """Coerce a gazetteer JSON field to a list of strings (tolerant of null)."""
    return [str(x) for x in value] if isinstance(value, list) else []


@dataclass(frozen=True)
class EntityMention:
    entity_id: str
    canonical_name: str
    entity_type: str
    surface: str
    start: int
    end: int


@dataclass(frozen=True)
class _Surface:
    """A searchable surface form compiled to a matcher."""

    pattern: re.Pattern[str]
    is_acronym: bool
    entity_id: str
    canonical_name: str
    entity_type: str


class Gazetteer:
    """An in-memory gazetteer. Construction precomputes matchers; `find_mentions`
    is a pure scan."""

    def __init__(self, entries: list[dict[str, object]]) -> None:
        self._by_id: dict[str, tuple[str, str]] = {}  # id -> (canonical, type)
        # surface(normalized) -> set of entity_ids, to detect ambiguity.
        form_owners: dict[tuple[str, bool], set[str]] = defaultdict(set)
        raw_forms: dict[tuple[str, bool], tuple[str, str, str]] = {}

        for e in entries:
            eid = str(e["entity_id"])
            canonical = str(e["canonical_name"])
            etype = str(e["entity_type"])
            self._by_id[eid] = (canonical, etype)
            for name in [canonical, *_str_list(e.get("aliases"))]:
                key = (name.lower(), False)
                form_owners[key].add(eid)
                raw_forms[key] = (eid, canonical, etype)
            for acro in _str_list(e.get("acronyms")):
                key = (acro, True)
                form_owners[key].add(eid)
                raw_forms[key] = (eid, canonical, etype)

        self._surfaces: list[_Surface] = []
        for key, owners in form_owners.items():
            if len(owners) > 1:
                continue  # ambiguous surface form — drop rather than guess
            text, is_acronym = key
            eid, canonical, etype = raw_forms[key]
            self._surfaces.append(
                _Surface(
                    pattern=re.compile(rf"\b{re.escape(text if is_acronym else text)}\b"),
                    is_acronym=is_acronym,
                    entity_id=eid,
                    canonical_name=canonical,
                    entity_type=etype,
                )
            )

    def canonical(self, entity_id: str) -> tuple[str, str] | None:
        """(canonical_name, entity_type) for an id, or None."""
        return self._by_id.get(entity_id)

    def find_mentions(self, text: str) -> list[EntityMention]:
        """Find non-overlapping, longest-preferred gazetteer mentions in `text`.

        Acronym surfaces are matched against the original (case-sensitive) text;
        name/alias surfaces against a lowercased copy (offsets align since
        lowercasing is length-preserving for the scripts we handle).
        """
        lowered = text.lower()
        candidates: list[EntityMention] = []
        for s in self._surfaces:
            haystack = text if s.is_acronym else lowered
            for m in s.pattern.finditer(haystack):
                candidates.append(
                    EntityMention(
                        entity_id=s.entity_id,
                        canonical_name=s.canonical_name,
                        entity_type=s.entity_type,
                        surface=text[m.start() : m.end()],
                        start=m.start(),
                        end=m.end(),
                    )
                )
        return _resolve_overlaps(candidates)


def _resolve_overlaps(mentions: list[EntityMention]) -> list[EntityMention]:
    """Greedy longest-match: sort by (start asc, length desc) and keep a mention
    only if it doesn't overlap one already kept."""
    ordered = sorted(mentions, key=lambda x: (x.start, -(x.end - x.start)))
    kept: list[EntityMention] = []
    occupied_end = -1
    for men in ordered:
        if men.start >= occupied_end:
            kept.append(men)
            occupied_end = men.end
    return kept


def _read(path: Path) -> list[dict[str, object]]:
    data: list[dict[str, object]] = json.loads(path.read_text(encoding="utf-8"))
    return data


def load_organizations(path: Path | None = None) -> Gazetteer:
    """Load the organization gazetteer JSON (I/O — worker/test boundary)."""
    return Gazetteer(_read(path or (_GAZ_DIR / "organizations.json")))


def load_persons(path: Path | None = None) -> Gazetteer:
    """Load the known-persons gazetteer JSON (notable officials + aliases)."""
    return Gazetteer(_read(path or (_GAZ_DIR / "persons.json")))


def load_entities(dir_path: Path | None = None) -> Gazetteer:
    """Load organizations + persons into one combined gazetteer (worker startup)."""
    base = dir_path or _GAZ_DIR
    return Gazetteer(_read(base / "organizations.json") + _read(base / "persons.json"))

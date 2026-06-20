"""rss.py — Generic RSS 2.0 adapter (Layer A normalization).

`parse_rss` is pure: bytes in (a feed snapshot the worker fetched), a list of
`NormalizedArticle` out. No network, no clock. This is what golden-file tests
pin — a saved feed snapshot maps to an exact normalized output, so a site's HTML
or feed-shape change that breaks extraction turns a test red.

Indonesian feeds are standard RSS 2.0; per-source quirks (canonical URL shape,
category vocab) ride on `SourceConfig`. Time is interpreted in the source's
declared zone then stored in UTC (DESIGN.md §7). Excerpts are hard-capped at
write time (compliance C1).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from packages.compliance.invariants import MAX_EXCERPT_CHARS, cap_excerpt
from packages.schemas.article import NormalizedArticle, SourceConfig

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# Query params that are tracking noise, stripped from the canonical URL so the
# same article shared with different campaign tags dedups to one canonical_url.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = frozenset({"fbclid", "gclid", "igshid", "ref", "source"})


def _text(elem: ET.Element | None) -> str | None:
    if elem is None or elem.text is None:
        return None
    cleaned = _WS.sub(" ", _TAG.sub(" ", elem.text)).strip()
    return cleaned or None


def _is_tracking(key: str) -> bool:
    return key in _TRACKING_KEYS or key.startswith(_TRACKING_PREFIXES)


def canonicalize_url(url: str) -> str:
    """Drop tracking query params and the fragment; keep meaningful query."""
    parts = urlsplit(url.strip())
    kept = [(k, v) for k, v in parse_qsl(parts.query) if not _is_tracking(k)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def _parse_published(raw: str | None, default_tz: str) -> datetime | None:
    """Parse an RSS pubDate to a UTC tz-aware datetime.

    RFC-822 dates usually carry an offset (e.g. +0700); if naive, interpret in
    the source's declared zone. Returns None on anything unparseable.
    """
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(default_tz))
    return dt.astimezone(UTC)


def parse_rss(
    raw_xml: bytes,
    source: SourceConfig,
    max_excerpt_chars: int = MAX_EXCERPT_CHARS,
) -> list[NormalizedArticle]:
    """Normalize an RSS 2.0 feed snapshot into typed articles.

    Items without a title or link are skipped — without both we can neither
    fingerprint nor link back (PR2), so they are not ingestable metadata.
    """
    root = ET.fromstring(raw_xml)
    articles: list[NormalizedArticle] = []
    for item in root.iter("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        if not title or not link:
            continue
        excerpt = cap_excerpt(_text(item.find("description")), max_excerpt_chars)
        published_at = _parse_published(_text(item.find("pubDate")), source.default_tz)
        articles.append(
            NormalizedArticle(
                source_id=source.source_id,
                url=link,
                canonical_url=canonicalize_url(link),
                title=title,
                excerpt=excerpt,
                published_at=published_at,
                published_tz=source.default_tz,
                language=source.language,
                raw_category=_text(item.find("category")),
            )
        )
    return articles

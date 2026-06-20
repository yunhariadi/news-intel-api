"""content_cluster.py — Near-duplicate grouping + carrier→origin resolution (Layer A).

This is the anti-syndication step (DESIGN.md §3, Prime Directive #1). Articles
whose `content_fingerprint` are within `hamming_max` bits AND whose ingestion
times are within `window_hours` are the same story carried by different outlets.
Each near-dup group becomes one `ContentCluster` with a single resolved ORIGIN:

    origin = earliest first_seen among `is_wire` sources,
             else earliest first_seen overall (deterministic tie-break by id).

Downstream, source diversity counts distinct ORIGIN sources across an event's
clusters — never carrier rows. That is what stops one wire dump from reading as
"30 sources".

Pure: no I/O, no clock reads. `first_seen_hours` is our monotonic ingestion time
(DESIGN.md §7 `first_seen_by_us`) expressed as hours from a fixed epoch; the
worker computes it and passes it in. Pairwise comparison is O(n²); the worker is
expected to pass a *candidate set* (e.g. a fingerprint prefix bucket), not the
whole corpus.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from packages.utils.simhash import hamming_distance

# Calibration knobs (mirror SIMHASH_HAMMING_MAX / NEAR_DUP_WINDOW_HOURS in env).
DEFAULT_HAMMING_MAX: int = 3
DEFAULT_WINDOW_HOURS: float = 48.0


@dataclass(frozen=True)
class ArticleForClustering:
    """The clustering-relevant projection of an article row."""

    article_id: str
    source_id: str
    is_wire: bool
    content_fingerprint: int  # 64-bit SimHash
    first_seen_hours: float   # monotonic ingestion time, hours from a fixed epoch


@dataclass(frozen=True)
class ContentCluster:
    cluster_id: str                 # deterministic: smallest member article_id
    article_ids: tuple[str, ...]    # sorted
    origin_source_id: str
    origin_article_id: str
    carrier_count: int
    first_seen_hours: float         # earliest in the cluster


def _is_near_dup(
    a: ArticleForClustering,
    b: ArticleForClustering,
    hamming_max: int,
    window_hours: float,
) -> bool:
    return (
        hamming_distance(a.content_fingerprint, b.content_fingerprint) <= hamming_max
        and abs(a.first_seen_hours - b.first_seen_hours) <= window_hours
    )


def resolve_origin(articles: Sequence[ArticleForClustering]) -> tuple[str, str]:
    """Carrier→origin: earliest wire source, else earliest seen overall.

    Returns (origin_source_id, origin_article_id). Ties broken by article_id so
    the result is deterministic.
    """
    if not articles:
        raise ValueError("cannot resolve origin of an empty cluster")
    wires = [a for a in articles if a.is_wire]
    pool = wires if wires else list(articles)
    origin = min(pool, key=lambda a: (a.first_seen_hours, a.article_id))
    return origin.source_id, origin.article_id


def cluster_content(
    articles: Sequence[ArticleForClustering],
    hamming_max: int = DEFAULT_HAMMING_MAX,
    window_hours: float = DEFAULT_WINDOW_HOURS,
) -> list[ContentCluster]:
    """Group near-duplicates and resolve each group's origin.

    Order-independent and deterministic: the same articles in any order produce
    the same clusters (sorted by `cluster_id`).
    """
    n = len(articles)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            # Attach to the lower index for a deterministic forest.
            parent[max(rx, ry)] = min(rx, ry)

    for i in range(n):
        for j in range(i + 1, n):
            if _is_near_dup(articles[i], articles[j], hamming_max, window_hours):
                union(i, j)

    groups: dict[int, list[ArticleForClustering]] = defaultdict(list)
    for idx in range(n):
        groups[find(idx)].append(articles[idx])

    clusters: list[ContentCluster] = []
    for members in groups.values():
        member_ids = tuple(sorted(a.article_id for a in members))
        origin_source_id, origin_article_id = resolve_origin(members)
        clusters.append(
            ContentCluster(
                cluster_id=member_ids[0],
                article_ids=member_ids,
                origin_source_id=origin_source_id,
                origin_article_id=origin_article_id,
                carrier_count=len(members),
                first_seen_hours=min(a.first_seen_hours for a in members),
            )
        )

    clusters.sort(key=lambda c: c.cluster_id)
    return clusters

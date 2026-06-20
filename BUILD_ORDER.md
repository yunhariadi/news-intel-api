# BUILD_ORDER.md — Phased Build Plan for `news-intel-api`

Build in this order. Do not skip ahead. Each phase has a goal, tasks, a
**definition of done (DoD)**, and the **CI gates** that must be green before the
phase is considered complete. The gates map to the Prime Directives in
`CLAUDE.md` and the invariants in `COMPLIANCE.md`.

The point of the ordering: get reliable, clean, deduplicated, syndication-aware
storage *first*. Intelligence and trends are worthless on dirty data.

---

## Phase 0 — Scaffolding

**Goal:** a runnable skeleton with the discipline baked in.

Tasks: repo layout per `CLAUDE.md §3`; `pyproject.toml` (ruff, mypy --strict,
pytest); `docker-compose.yml` (postgres+pgvector, redis, api, worker); `.env`
from `.env.example`; `GET /v1/health`; `make test|lint|up`; CI that runs
`make lint && make test`.

**DoD:** `make up` serves `/v1/health`; `make lint` and `make test` pass in CI.
**Gates:** CI pipeline exists and is green.

---

## Phase 1 — Ingestion & clean storage (v0.1)

**Goal:** collect and normalize news from 5–10 sources into clean, deduplicated,
**syndication-resolved** storage.

Tasks:
- DB schema from `DESIGN.md §2` incl. `content_clusters`, the **two hashes**
  (`dedup_key`, `content_fingerprint`), and the **two timestamps**
  (`published_at`, `first_seen_by_us`).
- Source registry + 3 source adapters (start: ANTARA, Kompas, CNBC Indonesia)
  with **golden-file tests**.
- RSS/sitemap ingestion worker: fetch → normalize → dedup → store. Idempotent on
  `dedup_key`; per-source rate limit + circuit breaker; polite User-Agent with
  bot-info URL.
- SimHash fingerprint + near-dup → `content_cluster`; carrier→origin resolution.
- `GET /v1/news`, `GET /v1/sources`, `GET /v1/sources/status` (cursor paginated).
- Time handling: store source-local tz + UTC.

**DoD:** worker fetches feeds on a schedule; articles stored; exact re-fetch is a
no-op; the same wire story across carriers lands in one `content_cluster` with a
single origin; `/v1/news` returns metadata only (no full bodies); source status
shows health.
**Gates (must be green):**
- Adapter golden-file tests.
- Dedup test: re-ingesting a URL does not duplicate; SimHash near-dups cluster.
- **Syndication test:** N carriers of one wire → 1 origin
  (`content_cluster.origin_source_id` correct, `carrier_count = N`).
- Compliance C1 (excerpt cap), PR2 (every item has source + url).

---

## Phase 2 — Intelligence layer (v0.2)

**Goal:** topics, actors, regions, quotes — hybrid NLP, gazetteer-backed.

Tasks:
- Text cleaner; language detect; topic classifier (keyword map + ML + override).
- Gazetteer (`db/gazetteer/`) of govt bodies, BUMN, parties, regulators +
  acronyms; NER fallback; actor alias resolver (gelar strip, acronym collisions).
- Region extractor with gazetteer + confidence (title/incident-word boosts).
- Quote extractor: high-precision rules **incl. continuation/pronoun and split
  quotes**; confidence floor → `exposable`; `source_paragraph_url` on every quote.
- Entity `legal_status` lifecycle populated where detectable.
- `packages/compliance/invariants.py` + tests (the full table in `COMPLIANCE.md`).
- `/v1/topics`, `/v1/actors`, `/v1/regions`, `/v1/quotes` — every row passes the
  compliance gate before serialization.
- **NLP gold set** (~300–500 labeled articles) in `tests/fixtures/` with
  per-extractor precision/recall thresholds in CI.

**DoD:** enrichment runs in the pipeline; gold-set P/R meets thresholds; no quote
is served without a source-paragraph link; exonerated/suppressed actors are
filtered.
**Gates:** NLP gold-set P/R; compliance invariants P1, P2, P4, I1, I2, I3.

---

## Phase 3 — Trending engine (v0.3)

**Goal:** detect what's trending, correctly.

Tasks:
- Use `packages/ranking/trending.py` (already implemented + tested) as the topic
  scorer. Implement `actor.py`, `region.py`, `source.py` reusing its primitives
  with their `importance` source.
- Worker computes per-window mentions, baselines, and the rolling
  `reference_scale` (P95 of raw) from `trend_snapshots`; passes them into the
  pure scorers.
- `GET /v1/trending?type=&window=&limit=`.
- **Trending regression set**: pinned real events ("on date D, topic T trended")
  in CI.

**DoD:** trends are syndication-aware, bounded 0–100, stable across windows; a
wire dump never tops the board; a cold-start item never reaches #1 on thin
evidence.
**Gates:** `test_trending.py` (23 tests) + the trending regression set.

---

## Phase 4 — Event clustering (v0.4)

**Goal:** group related articles into events with stable IDs.

Tasks:
- Blocking (shared actor / region+day) → entity+time similarity → embedding
  tie-break (multilingual-e5 / IndoBERT over title+lede).
- **Incremental, stable-ID** assignment; explicit merge/split ops (logged).
- Event timeline + source comparison (diversity over origins, not carriers).
- `/v1/events`, `/v1/events/{id}`, `/v1/events/{id}/timeline`,
  `/v1/events/{id}/sources`.

**DoD:** articles cluster into events; event IDs are stable across re-runs;
source comparison counts origins; timelines render from `first_seen_by_us`.
**Gates:** event-clustering labeled set (precision/recall on same-event pairs);
ID-stability test (re-running assignment does not change existing event IDs).

---

## Phase 5 — Commercial API (v0.5)

**Goal:** usable by external customers.

Tasks: API keys; rate limiting (`X-RateLimit-*`, `Retry-After`); usage metering;
saved queries; webhook alerts (use the bounded normalized score so `min_score`
is stable); billing-ready quotas; admin dashboard (source health, dup rate,
entity/quote review, event merge/split, data-subject-request console);
takedown/bot-info pages.

**DoD:** an external key can authenticate, is rate-limited per tier, can register
a webhook that fires on a stable score threshold, and a data-subject request can
be actioned end-to-end through the admin console.
**Gates:** auth/rate-limit tests; webhook-firing test on threshold; DSR workflow
test (erase → entity absent from all responses).

---

## Definition of done (every task, every phase)

Code + tests green + `ruff` clean + `mypy --strict` clean + the relevant Prime
Directives/invariants demonstrably held **by a test**. PR description lists which
directives/invariants the change touches and the tests that prove them.

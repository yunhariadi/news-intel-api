# CLAUDE.md — Agent Operating Manual for `news-intel-api`

> This file is the contract between you (the AI coding agent) and this codebase.
> Read it fully before writing any code. The original product spec
> (`docs/SPEC.md`) describes *what* to build; this file and `DESIGN.md` describe
> *how*, and override the spec wherever they disagree. The spec contains several
> seductive-but-wrong shortcuts (listed under "Do Not" below). Follow this file.

---

## 0. What this project is

An **API-first Indonesia News Intelligence system**. It ingests Indonesian news
metadata, normalizes it, extracts entities/quotes/regions/topics, clusters
near-duplicates and then events, scores trends, and serves structured JSON.

It is **not** a news republisher. It stores and returns *metadata and
intelligence* (titles, short excerpts, attributed quotes, entities, trend
scores, links back to the origin) — never full article bodies. This is a legal
constraint, not a preference. See `COMPLIANCE.md`.

Primary market: Indonesia. Default stack: **Python 3.12 + FastAPI**. Worker:
APScheduler for the MVP (Celery+Redis later). Storage: **PostgreSQL + pgvector
only** for v0.1. Search engine (OpenSearch) is deferred — do not add it until a
phase explicitly calls for it.

---

## 1. Prime Directives (non-negotiable invariants)

These are the rules that, if broken, mean the build is *wrong* even if the tests
you wrote pass. Each maps to a real failure mode. Treat them as load-bearing.

1. **Source diversity is counted over distinct *original* sources, never over
   URLs or carriers.** Indonesian media is dominated by wire syndication
   (ANTARA, Tribun Network, cross-posting). One wire story republished by 30
   outlets is **one** original source, not thirty. Counting carriers as sources
   silently corrupts trending. The pipeline must resolve carrier → origin
   (`content_cluster` step) *before* anything is scored.

2. **Trending scores are bounded, smoothed, and additive — never an unbounded
   product.** Never multiply by a raw `growth_rate = current / max(prev, 1)`:
   it explodes on cold starts. Burst is a clamped Poisson-style residual added
   on top of diversity-weighted volume. The reference implementation in
   `packages/ranking/trending.py` is canonical — match its behavior; its test
   suite is the gate.

3. **Provenance is honest.** `published_at` (claimed by the feed) and
   `first_seen_by_us` (our monotonic ingestion time) are **different columns**.
   Never compute "which media reported first" from feed timestamps alone and
   present it as fact. Label it "first observed by us" unless stronger
   provenance exists. Carry a `provenance_confidence`.

4. **Layer A is pure and tested before Layer B exists.** Layer A = all
   deterministic computation (dedup, fingerprinting, scoring, clustering math,
   compliance predicates). It has **no I/O, no network, no clock reads, no LLM
   calls**, and ships with a pytest gate. Layer B = LLM narration only
   (summaries, event titles), runs *after* Layer A, and may never feed back into
   a deterministic decision. If you find yourself wanting an LLM call inside a
   ranking or compliance function, stop — that belongs in Layer B.

5. **Compliance invariants are code, not comments.** The rules in
   `COMPLIANCE.md` are implemented as pure predicates in
   `packages/compliance/invariants.py` with their own pytest gate. An acquitted
   actor's `tersangka` label must be unexposable. A quote without a
   `source_paragraph_url` must be unreturnable. These tests block the build.

6. **Metadata, not republication.** No endpoint, field, or cache ever returns a
   full article body or a large verbatim excerpt. Excerpts are hard-capped.
   Summaries are abstractive and attributed. Always include the origin URL.

If a requested feature conflicts with one of these, raise it in your PR
description rather than quietly working around it.

---

## 2. Architecture (one screen)

```
Sources (RSS / sitemap / licensed feeds)
   → Ingestion workers  (fetch, normalize, dedup, store raw+normalized)
   → Content clustering (near-dup detection → carrier→origin resolution)   [Layer A]
   → NLP enrichment     (topic / NER+gazetteer / region / quote)           [A + B]
   → Event clustering   (entity+time blocking → stable online events)      [Layer A]
   → Ranking            (syndication-aware trends, bounded scores)         [Layer A]
   → API                (FastAPI, JSON, API keys, rate limits)
```

Two clustering layers, kept distinct:
- **`content_cluster`** = near-duplicate group (same story, many carriers).
  Source diversity counts origins across this group.
- **`event`** = semantic story group (related-but-distinct articles over time).

See `DESIGN.md` for the data model and each algorithm.

---

## 3. Repository layout

```
news-intel-api/
  README.md            # human entry point
  CLAUDE.md            # this file — agent manual
  DESIGN.md            # architecture + corrected algorithms (the "why")
  COMPLIANCE.md        # Indonesian regulatory invariants
  BUILD_ORDER.md       # phased plan with definition-of-done + CI gates
  .env.example
  pyproject.toml
  docker-compose.yml

  apps/
    api/               # FastAPI app, routes, middleware, deps
    worker/            # scheduler + jobs (fetch, enrich, cluster, trends)
  packages/
    source_adapters/   # one adapter per source; golden-file tested
    nlp/               # cleaner, topic, ner, actor_resolver, region, quote
    ranking/           # trending.py (DONE, reference) + actor/region/source
    clustering/        # content_cluster (near-dup) + event_clusterer
    compliance/        # invariants.py (pure predicates) + tests
    schemas/           # typed contracts (pydantic) shared across layers
    db/                # models, session, migrations, gazetteer seeds
    utils/             # time (WIB/WITA/WIT), hashing, simhash, text
```

---

## 4. Layer A / Layer B in practice

**Layer A (deterministic).** Pure functions over typed inputs. Example shape to
follow everywhere — this is `packages/ranking/trending.py`:

- inputs are frozen dataclasses / pydantic models;
- no `datetime.now()` inside — the caller passes `age_hours`/`now`;
- no DB or HTTP calls — the worker fetches state and passes it in;
- every module has `test_<module>.py` next to it;
- constants live at module top, marked as calibration knobs, never inline.

**Layer B (LLM narration).** Only two jobs in the MVP: short abstractive
article summaries and event titles. Rules: runs after Layer A; output is
display-only; is never an input to a score, a dedup decision, an event
assignment, or a compliance check; must be cheap (do not call an LLM per article
in the hot path — batch, cache, and gate behind `ENABLE_LLM_ENRICHMENT`).

---

## 5. Coding conventions

- **Python 3.12**, full type hints, `from __future__ import annotations`.
- **Typed contracts** in `packages/schemas/` (pydantic v2). Layer A may use
  frozen dataclasses for hot-path purity; convert at the boundary.
- **Pure Layer A**: a function that reads a clock, the network, or a DB is not
  Layer A. Push that to the worker/adapters.
- **Errors**: API returns the spec's error envelope
  `{"error": {"code", "message", "request_id"}}`. `request_id` is generated
  server-side (accept an inbound one for tracing if present).
- **Pagination**: cursor-based (`created_at` + `id`), never offset — the corpus
  updates live and offset paging double-serves/skips rows.
- **Time**: store `TIMESTAMPTZ`. Indonesia spans **three** zones (WIB/WITA/WIT);
  store source-local zone + UTC, compute all windows in UTC. Do not hardcode
  `Asia/Jakarta` as the single truth.
- **Lint/type**: `ruff` + `mypy --strict` on `packages/`. CI fails on either.
- **No browser storage / no secrets in code.** Config via env only.

---

## 6. Testing discipline (the gate)

- Every Layer A module ships a `pytest` suite that pins **behavior**, not
  implementation. `packages/ranking/test_trending.py` is the template (23 tests
  covering cold-start, syndication, diversity, burst, recency, determinism).
- Two regression corpora live in `tests/fixtures/` and are part of CI:
  - **NLP gold set** (~300–500 hand-labeled articles): per-extractor
    precision/recall with thresholds. A merge that drops quote precision below
    threshold fails CI.
  - **Trending regression set**: "on date D, topic T did trend" — pinned real
    events. A scoring change that stops detecting a known burst fails CI.
- Source adapters have **golden-file tests** (a saved feed snapshot → expected
  normalized output) plus a runtime **extraction-yield drift** alarm.
- Definition of done for any task: code + tests green + `ruff` + `mypy` clean +
  the relevant Prime Directives demonstrably held by a test.

Run:
```bash
make test        # pytest across packages
make lint        # ruff + mypy --strict
make up          # docker compose up (postgres+pgvector, api, worker)
```

---

## 7. Do Not (these are the spec's traps — do not implement them)

- ❌ `trend_score = count × ... × growth_rate × ...` (unbounded product / cold
  start). Use `packages/ranking/trending.py`.
- ❌ `content_hash = sha256(title + source + date)`. Putting `source` in the
  hash defeats cross-source dedup. Use two hashes: a URL-based `dedup_key` and a
  source-independent `content_fingerprint` (SimHash). See `DESIGN.md §dedup`.
- ❌ Counting carrier URLs as distinct sources for diversity.
- ❌ Asserting "first reported" from feed `published_at`.
- ❌ Exposing a `tersangka`/suspect label that survives an acquittal/SP3.
- ❌ Returning a quote without `source_paragraph_url` or below the confidence
  floor; letting Layer B paraphrase a quote as if verbatim.
- ❌ Returning full article bodies or large verbatim excerpts.
- ❌ Provisioning OpenSearch in v0.1 (Postgres FTS + pgvector is enough).
- ❌ Calling an LLM per article in the ingestion hot path.
- ❌ Batch re-clustering that reassigns event IDs (breaks webhooks/timelines).
  Events are assigned **incrementally** with stable IDs.

---

## 8. How to work a task

1. Pick the current phase from `BUILD_ORDER.md`. Do not skip ahead.
2. For each component: define the typed contract in `schemas/`, implement the
   **Layer A** core as pure functions, write its `pytest` gate first/alongside,
   make it green.
3. Wire it into the worker or API. Add integration coverage.
4. Re-read the Prime Directives and the phase's "definition of done". Confirm
   each is satisfied by a test, not by inspection.
5. In the PR description, list which Prime Directives the change touches and how
   the tests prove them.

When in doubt, prefer the conservative, deterministic, well-tested option over
the clever one. This system's value is trust; trust comes from Layer A.

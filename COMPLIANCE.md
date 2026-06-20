# COMPLIANCE.md — Regulatory Invariants for `news-intel-api`

> This is a build guardrail, not legal advice. It translates Indonesian law into
> machine-checkable invariants implemented in `packages/compliance/invariants.py`
> and pinned by `packages/compliance/test_invariants.py`. Before launch, have a
> licensed Indonesian lawyer review the commercial model. Facts below reflect the
> regulatory state as of mid-2026; verify currency before relying on them.

**Governing principle:** this system is a *structured metadata and intelligence
layer*, not an article republication engine. Every design choice that touches a
named person, a press company's content, or a legal case bends toward
metadata + attribution + link-back, never reproduction.

---

## 1. UU PDP — Personal Data Protection (Law 27/2022)

State: enacted 2022; **fully enforceable since 17 October 2024** (transition
period ended). Administrative fines up to **2% of annual revenue**, plus civil
and criminal exposure. The dedicated PDP Agency is targeted to be operational in
2026 (KOMDIGI performs interim oversight). The law has **extraterritorial
scope** and covers personal data of Indonesian subjects.

Why it applies here: the system processes personal data of identifiable
individuals (officials, executives, suspects). Public-figure status does not
exempt it. Crucially, **criminal-record-adjacent data** (`tersangka`/suspect
status) is treated as **special / sensitive** personal data and demands stronger
protection.

### Invariants
- **P1 — Suspect lifecycle / presumption of innocence.** Entities carry
  `legal_status ∈ {terlapor, saksi, tersangka, terdakwa, terpidana, bebas, sp3}`.
  When status reaches `bebas` (acquitted) or `sp3` (case dropped), any prior
  accusatory label (`tersangka`, `terdakwa`) is **unexposable**. The API must
  not return, and trends must not surface, an accusatory label for an exonerated
  person. *Test:* exonerated actor → `is_label_exposable(...) is False`.
- **P2 — Data subject rights.** Support access, rectification, erasure, and
  consent-withdrawal requests from day one (not "later"). An erasure/rectify
  request sets `entities.suppressed = true` and tombstones PII within an SLA;
  suppressed entities are filtered from all responses. *Test:* suppressed entity
  never appears in any serializer output.
- **P3 — Retention limits.** Raw fetched bodies are transient (used for
  extraction, then dropped/short-TTL). Personal data is retained only as long as
  the journalistic-intelligence purpose requires; document the retention window.
- **P4 — Minors & sensitive victims.** Do not expose names of minors or victims
  of sexual offences as queryable actors. Suppress by rule.

---

## 2. Publisher Rights — Perpres 32/2024

State: "Tanggung Jawab Perusahaan Platform Digital untuk Mendukung Jurnalisme
Berkualitas," signed 20 Feb 2024, **in force since 20 Aug 2024**. It governs the
relationship between Dewan-Pers-verified press companies and digital platforms
that *collect, manage, distribute, and present news for commercial purposes*.
KOMDIGI has stated the scope reaches any platform that distributes or
commercializes news content. Scope is tied to operating digital-platform
services in Indonesia (Art. 5). Notably, the Perpres sets **no explicit
sanctions** for non-compliance and channels obligations through agreements and a
committee; enforcement attention so far targets Google/Meta-scale platforms. As
of National Press Day Feb 2026, Dewan Pers is pushing to elevate it to a full
law — i.e. it is hardening, not fading.

Why it matters here: a commercial API deriving value from verified press output
is squarely in the conceptual scope, even if current enforcement targets giants.
This is a **business-model risk**, flagged loudly so it is a deliberate decision,
not an accident.

### Invariants & posture
- **PR1 — No republication.** Never serve full bodies; excerpts hard-capped;
  summaries abstractive. (Reinforces §4.)
- **PR2 — Mandatory attribution + link-back.** Every article/quote/event item in
  every response carries the origin source name and origin URL. *Test:* no
  serialized news item lacks `source` + `url`.
- **PR3 — Takedown & correction channel.** A documented, reachable takedown
  policy and a bot-info page (User-Agent links to it).
- **PR4 — Partnership path.** As the product commercializes, pursue licensing /
  partnership with verified press companies; keep the architecture
  metadata-first so a licensing conversation is about *enrichment*, not
  *replacement*.

---

## 3. UU ITE (EIT Law, as amended by Law 1/2024) — defamation

Exposing a quote attributed to a named real person through a paid API, where the
extractor misattributed or distorted it, is a *pencemaran nama baik* exposure.

### Invariants
- **I1 — Confidence floor.** A quote is `exposable` only above the confidence
  floor; below it, never returned.
- **I2 — Verifiability.** Every exposable quote carries `source_paragraph_url`
  (deep link) so the attribution is checkable against the origin.
- **I3 — No synthetic verbatim.** Layer B may summarize, but must **never**
  paraphrase a statement and present it inside quotation marks as verbatim.
  Verbatim text comes only from the rule-based extractor over source text.
  *Test:* a quote with `attribution_status='inferred'` is not `exposable` as
  verbatim.

---

## 4. Copyright — Hak Cipta (Law 28/2014)

Facts are not protected; expression is.

### Invariants
- **C1 — Excerpt cap.** `excerpt` is hard-capped (e.g. ≤ 300 chars / configurable
  `MAX_EXCERPT_CHARS`); the cap is enforced at write time. *Test:* over-long
  excerpt is rejected/truncated before persist.
- **C2 — Abstractive summaries.** Generated summaries are reworded, not
  near-copies, and attributed. Do not mirror the source's structure or lede.

---

## 5. Data subject request workflow (operational)

1. Intake (email/endpoint) → ticket with subject identity + request type.
2. Resolve to entity/articles. 3. Apply: rectify (correct field) or erase
(`suppressed=true`, tombstone PII). 4. Propagate: re-run serializers/caches so
suppressed data is gone from responses and trend snapshots. 5. Log the action
(who/when/what) for accountability (UU PDP demonstrable-compliance principle).

---

## 6. The compliance gate (what CI enforces)

`packages/compliance/invariants.py` exposes pure predicates; `test_invariants.py`
pins them. The build is red unless all hold:

| ID  | Invariant                                                       |
|-----|-----------------------------------------------------------------|
| P1  | Exonerated actor → accusatory label not exposable               |
| P2  | Suppressed entity → absent from every response                  |
| P4  | Minor / sensitive victim → not an exposable actor               |
| PR2 | Every news item serialized with source name + origin URL        |
| I1  | Quote below confidence floor → not returned                     |
| I2  | Exposable quote → has `source_paragraph_url`                     |
| I3  | `inferred` attribution → never served as verbatim quote         |
| C1  | Excerpt length ≤ `MAX_EXCERPT_CHARS` at persist time            |

These predicates run inside the API serialization path, so a row that violates
them cannot be returned even if it exists in the database.

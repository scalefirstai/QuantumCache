# BNY Agentic DDQ Platform — Data Plan

**Doc:** SA-2026-0142-DATA · **Status:** DRAFT v0.1 · **Classification:** Internal · **Companion to:** `SPEC.md`
**Audience:** Engineers building the data layer first, before any internal BNY system access.

---

## 0. Why data first

The platform is only as good as its corpus, taxonomy, and library. None of those need internal BNY access to bootstrap. This plan is what gets built **before** L01–L08 services come online — and what makes those services demoable from day one.

**Outcomes of this plan (in order):**

1. A real, hash-stable, legally-clean **knowledge corpus** built from BNY public disclosures and SEC EDGAR.
2. A real, machine-readable **canonical taxonomy** seeded from public frameworks (CAIQ + AFME + ADV + NIST CSF + ISO 27001 control families).
3. A real **framework mapping table** from each public framework's question into the canonical taxonomy.
4. A real **eval set v0** of `(canonical_id, evidence_span)` gold pairs to drive L03 retrieval evaluation and L02 citation guardrail tests.
5. A baseline **library** of ~50 SME-stub entries to exercise L04 lookup and L06 DraftComposer end-to-end on public material.

Once these exist, every layer in `SPEC.md` can be developed and tested against real artifacts. When internal data access is granted, the same pipelines ingest BNY-private corpora behind the same interfaces.

---

## 1. Source manifest — what's public, what isn't

| Source | Public | Format | License notes | Use |
|---|---|---|---|---|
| **AFME DDQ 2024** (custodian) | ✅ Free download | `.docx` + `.xlsx` | "AFME encourages the widest usage" — free for all | Canonical seed: sub-custody, ops resilience, regulatory |
| **AFME DDQ 2024** (CSD version) | ✅ Free download | `.docx` | Same | Sub-custody-specific canonical IDs |
| **AFME ESG DDQ** | ✅ Free download | `.pdf` | Same | ESG canonical seed |
| **CAIQ v4.1 (full)** | ✅ Free download | `.xlsx` + JSON + YAML + OSCAL | CSA license — free, redistribution permitted with attribution | Canonical seed: information security (17 domains, 261 Qs); machine-readable JSON is the gift |
| **CAIQ-Lite v4.1** | ✅ Free download | `.xlsx` | CSA license | Canonical seed: 138 Qs, lower-tier |
| **CCM v4.1 controls** | ✅ Free download | `.xlsx` + JSON + OSCAL | CSA license | Knowledge graph: control → evidence relationships in Neo4j |
| **CCM mappings** (NIST 800-53, ISO 27001, PCI, SOC 2, CCPA, GDPR, AICPA TSC) | ✅ Free download | `.xlsx` + JSON | CSA license | Cross-framework deflection ratios — the killer demo |
| **Form ADV bulk data** (all advisers, 2001→2024) | ✅ Public | `.csv` | Public domain (US government work) | Canonical seed: regulatory posture; entity-level filings for BNY adviser subsidiaries |
| **Form ADV** (live, post-Jan 2025) | ✅ Public | IAPD search | Public domain | Live filings |
| **NIST CSF 2.0** | ✅ Free download | OSCAL JSON | Public domain | SIG-shaped placeholder canonical IDs (until SIG license procured) |
| **NIST SP 800-53 rev5** | ✅ Free download | OSCAL JSON | Public domain | Control family scaffolding |
| **BNY 10-K** (annual) | ✅ Public | `.pdf` + EDGAR HTML | Public filing | Corpus: business segments, risk factors, governance |
| **BNY Pillar 3 disclosures** | ✅ Public | `.pdf` | Public filing | Corpus: capital, market risk, op risk |
| **BNY Proxy** (annual) | ✅ Public | `.pdf` + EDGAR HTML | Public filing | Corpus: governance, executive comp, board |
| **BNY Resolution Plan** (public sections) | ✅ Public | `.pdf` | Public filing | Corpus: legal entity structure, BCP |
| **BNY Sustainability / ESG Report** | ✅ Public | `.pdf` | Public publication | Corpus: ESG narrative |
| **BNY 8-Ks, 10-Qs, DEF 14A** | ✅ Public | EDGAR | Public filing | Corpus: ongoing material events |
| **SIG Lite / SIG Core** | ❌ **Licensed** | $6,500–$7,200/yr corporate license | Shared Assessments — **do not redistribute, do not scrape from third-party blogs** | Stub canonical IDs from NIST/ISO until license procured |

**Refresh cadence (informational; runtime cadence is a separate concern in L03):**
- AFME DDQ — ~annual; check `afme.eu/publications/standard-forms-and-documents` Q1 each year.
- CAIQ / CCM — ~annual; CSA cuts new versions roughly yearly (v3 → v4.0 → v4.0.2 → v4.0.3 → v4.1).
- Form ADV bulk — quarterly.
- BNY 10-K — annual (Feb–Mar). 10-Q quarterly. 8-K event-driven.
- NIST CSF / 800-53 — multi-year revision cycles.

**Hashes to record at ingest:** SHA-256 of the raw downloaded artifact, plus per-section SHA-256 after parse. These become the `doc_hash` and `span_hash` referenced in `SPEC.md` §L01/L03/L04.

---

## 2. Data plan vs. SPEC: what gets built where

The data plan does not introduce new architectural concepts. It populates the same domains defined in `SPEC.md` §5:

| `SPEC.md` domain | Populated by |
|---|---|
| **Knowledge** (mutable, S3 + Parquet) | §3 of this doc — BNY public corpus ingestion |
| **Canonical** (versioned, Mongo + S3) | §4 of this doc — taxonomy + framework mappings + library seed |
| **Audit** (immutable) | Not populated by this plan — audit is created at runtime per `SPEC.md` §L01 |

All ingest writes go through the same `core/ports/` interfaces the production system uses. A bootstrap script is just another client; no special path.

---

## 3. Knowledge corpus — building "mock BNY" from public sources

### 3.1 What we ingest

Per `SPEC.md` §L03, every document parses into `(doc_id, section_id, span_id, text, anchor, hash)` tuples. The data plan defines **four document types** to start:

1. **Annual reports (10-K)** — BNY Mellon Corp, last 5 years.
2. **Pillar 3 disclosures** — quarterly, last 8 quarters.
3. **Proxy statements (DEF 14A)** — last 3 years.
4. **Form ADV** — for every BNY-registered investment adviser subsidiary. The IAPD search finds these by entity name; ADV Part 1 is structured (CSV-friendly), Part 2 is narrative (PDF), Part 3 (CRS) is short-form.

This gives ~30–60 documents, several thousand pages — enough to make retrieval non-trivial and citation guardrails meaningful.

### 3.2 Where it lives

Identical to `SPEC.md` §5, with a `bootstrap=true` tag on every record so the runtime can distinguish seed from operational data:

```
s3://bny-ddq-knowledge-raw/<source>/<entity>/<doc_id>/<filename>          # raw, immutable
s3://bny-ddq-knowledge-parquet/year=YYYY/month=MM/source=<source>/...    # parsed, partitioned
```

Mongo gets the metadata index only (`knowledge.documents` collection: doc_id, source, entity, anchor map, hashes, ingest timestamp). Document bodies stay in S3.

### 3.3 Sources & access patterns

**SEC EDGAR — programmatic, free, no key required.** BNY Mellon Corp CIK is `1390777`.

- Submissions index: `https://data.sec.gov/submissions/CIK0001390777.json` returns the full filing history as JSON.
- Filing archive: `https://www.sec.gov/Archives/edgar/data/1390777/<accession>/...` for raw documents.
- Required header: `User-Agent: <Name> <email>` per SEC fair-access policy.
- Rate limit: 10 req/sec/IP. The ingest worker MUST honor this.

**BNY investor relations** — `https://www.bny.com/corporate/global/en/investor-relations/regulatory-filings.html` for non-SEC public docs (Pillar 3, sustainability).

**IAPD** — `https://adviserinfo.sec.gov/adv` for live Form ADV; bulk historical CSVs at `https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data`.

### 3.4 Parse strategy

- Per `SPEC.md` §L03: Unstructured.io produces `(doc_id, section_id, span_id, text, anchor, hash)` tuples.
- 10-K: parse on Item / sub-item boundaries (Item 1, 1A, 1B, 7, 7A, etc.). Section IDs map to standard 10-K structure.
- Pillar 3: parse on table boundaries plus narrative sections.
- ADV Part 1: skip parser; load directly from EDGAR's structured CSVs.
- ADV Part 2: parse PDF on item-level boundaries (the brochure structure).

### 3.5 Anchors

Every span carries either:
- `PageAnchor { page: int, doc_hash: str }` for PDFs.
- `SectionAnchor { item: str, subsection: str | None, doc_hash: str }` for structured filings.

These are exactly the anchors required by `SPEC.md` §L03 / §L02 guardrail 01. Citation resolution is testable against this corpus from day one.

### 3.6 Acceptance criteria

1. **Coverage:** all 4 document types ingested for BNY Mellon Corp; ≥ 5 ADV filings across BNY adviser subsidiaries.
2. **Hash stability:** re-running ingest with no source change produces zero new `doc_hash` values.
3. **Anchor resolution:** for any random span in any ingested doc, `corpus.fetch_span(span_hash)` returns text matching the original byte-for-byte.
4. **Freshness metadata:** every doc has `effective_date` and (where applicable) `expiry_date` set, so the L02 freshness guardrail has something real to evaluate.

---

## 4. Canonical taxonomy — seeding from public frameworks

Per `SPEC.md` §L05, the taxonomy is the hinge. The data plan defines the **bootstrap process** that produces the v0.1 taxonomy snapshot.

### 4.1 Strategy

Build the taxonomy from machine-readable sources first, narrative sources second:

| Pass | Source | What it gives |
|---|---|---|
| 1 | CAIQ v4.1 JSON / OSCAL | 261 questions across 17 domains, with control IDs and CCM mappings to NIST/ISO/PCI/SOC2 — direct seed for `canon.is.*` and `canon.cyber.*` |
| 2 | AFME DDQ Excel | ~250 questions across 15 sections — direct seed for `canon.subc.*`, `canon.or.*`, `canon.reg.*` |
| 3 | Form ADV Part 1 schedule items | Structured fields → canonical questions about advisory activities, custody, AUM, disciplinary history — direct seed for `canon.reg.*` |
| 4 | NIST CSF 2.0 OSCAL | Functions/Categories/Subcategories — fills SIG-shaped canonical placeholders until SIG license is procured |
| 5 | AFME ESG DDQ + BNY sustainability disclosures | ESG question patterns — seed for `canon.esg.*` |

After pass 5, expect roughly **400–600 canonical IDs**, distributed roughly:

- `canon.is.*` — ~200 (CAIQ + NIST overlap)
- `canon.or.*` — ~80 (AFME ops + BCP)
- `canon.reg.*` — ~80 (AFME compliance + ADV)
- `canon.subc.*` — ~60 (AFME custodian-specific)
- `canon.cyber.*` — ~60 (CAIQ subset, NIST CSF)
- `canon.esg.*` — ~30 (AFME ESG + sustainability)

This is the seed the platform demos against. Real production scale is the spec's stated 1,800+; that target is reached after SME curation passes on real DDQ history.

### 4.2 Generation pipeline

```
public sources ─► structured extraction ─► dedup + cluster (embedding) ─► canonical_id assignment ─► framework_mappings populated ─► SME review pass ─► v0.1 snapshot
```

Each canonical ID conforms to `SPEC.md` §L05 schema. Bootstrap-generated entries carry `owners: ["bootstrap.seed"]` and `tier: 2` by default; SME review reassigns owners and tiers.

### 4.3 Framework mappings — the deflection demo

The strongest demo to leadership is the cross-framework deflection ratio (operating lever, opportunity #i in the architecture doc). Build it in:

- For every CAIQ question, populate `framework_mappings` with the CCM mapping bundle's pre-existing maps to NIST 800-53, ISO 27001, PCI DSS 4.0, SOC 2 TSC. **All from CSA, free, machine-readable.** This is the single highest-leverage day-one win.
- For every AFME question, manually map to the closest CAIQ canonical ID (where it exists) — this gives AFME→CAIQ→NIST→ISO chains.
- For every ADV item, map to its `canon.reg.*` ID.

Result: the moment a single canonical answer is library-approved, it can satisfy 1 AFME question, ≥1 CAIQ question, and (transitively) NIST/ISO/PCI mappings. Measure and surface this ratio in the dashboards (`SPEC.md` §9.2).

### 4.4 SIG placeholder strategy

Until a SIG license is procured:

- Tag canonical IDs that are likely-SIG-relevant (derived from NIST CSF + ISO 27001) with `tags: ["sig-candidate"]`.
- Leave `framework_mappings` empty for SIG entries.
- The Mapper agent (per `SPEC.md` §L06 `QuestionMapper`) classifies any incoming SIG question against the existing taxonomy as if SIG mappings were absent — it still works because SIG is heavily NIST/ISO-aligned.
- When license is procured, populate `framework_mappings.SIG_*` retroactively. No structural change.

**Do not** ingest SIG content from blog posts, vendor marketing, or third-party "SIG explainer" sites. Even if technically accessible, the questions are copyrighted by Shared Assessments.

### 4.5 Acceptance criteria

1. **Coverage:** v0.1 snapshot has ≥ 400 canonical IDs across all 6 domains.
2. **Mapping density:** ≥ 95% of CAIQ questions have at least one populated `framework_mappings` entry beyond CAIQ itself (typically NIST + ISO via CCM bundle).
3. **Snapshot integrity:** v0.1 sealed to S3 per `SPEC.md` §L05, signed, with `merkle_root` matching live Mongo state at cut time.
4. **Round-trip:** TaxonomyService can `get(canonical_id, version="tx_v0.1")` and recover every entry bit-exact.

---

## 5. Library v0 — seeding ~50 demo entries

Per `SPEC.md` §L04, a library entry is an SME-approved, citation-verified answer for a `(canonical_id, entity, product)` triple. The data plan seeds a small, demo-grade library so L06 (DraftComposer) and L07 (orchestrator) have something to exercise end-to-end.

### 5.1 Selection — pick canonical IDs that the public corpus can actually answer

Good seed picks are canonical IDs whose answer is plainly recoverable from BNY's 10-K, Pillar 3, or proxy. Examples:

- `canon.reg.entity_structure.principal_subsidiaries` → 10-K Item 1, list of principal subsidiaries.
- `canon.or.business_continuity.governance` → Pillar 3 op-risk section.
- `canon.reg.governance.board_composition` → Proxy.
- `canon.reg.financial.aum` → 10-K + ADV Part 1.
- `canon.is.audit.soc_attestations.scope` → BNY public trust pages (where present).

Avoid canonical IDs that depend on internal-only material; those wait for real BNY ingest.

### 5.2 Construction

For each of ~50 picks:

1. Identify the canonical_id (must already exist in v0.1 taxonomy).
2. Identify the evidence span(s) in the public corpus — record `(doc_hash, span_hash, anchor)`.
3. Draft answer text **extractively** (per `SPEC.md` §1 invariant 4: extractive over generative for facts). For these public-fact questions, almost all answer text should be a direct quote or near-paraphrase of the cited span.
4. Run through `Validator` (L02): citations resolve, freshness in window, confidentiality scrub a no-op since source is already public.
5. Mark `approvers: [{"role": "bootstrap.seed", ...}]` — these are demo entries, not regulator-defensible. Tag `tags: ["bootstrap", "public-only"]` so production never ships them.
6. Seal versioned snapshot to S3.

### 5.3 What this lets you demo

- L03 retrieval returns the seeded evidence span for queries that map to seeded canonical IDs.
- L04 library lookup hits cleanly.
- L06 DraftComposer drafts on top of real evidence.
- L02 validator runs all four guardrails on output that *should* pass — proving the pipeline.
- The full graph in `SPEC.md` §L07 runs end-to-end with no synthetic placeholders.

### 5.4 Acceptance criteria

1. ≥ 50 entries seeded, each citing ≥ 1 real span in the public corpus.
2. Every entry passes the L02 validator with `verdict == "pass"` (where it doesn't, fix the entry — these are the cleanest possible cases).
3. Replay test (`SPEC.md` §L01 acceptance criterion 1) succeeds for at least 5 sample runs that consume seeded entries.
4. All seeded entries are tagged `bootstrap` and excluded from production response paths by default OPA policy.

---

## 6. Eval set v0 — 100 questions for L03 / L06 evaluation

Per `SPEC.md` §9.3 the production target is a 500-question regression set. The data plan delivers v0 at 100, drawn from public material so it's safe to commit to the repo.

### 6.1 Composition

| Slice | Count | Source |
|---|---|---|
| AFME custodian questions with public-disclosable answers | 30 | AFME DDQ + BNY 10-K/Pillar 3 |
| CAIQ questions answerable from public BNY material | 25 | CAIQ + BNY public trust pages, sustainability report |
| ADV Part 1 questions | 20 | Form ADV Part 1 schedule items, BNY adviser subsidiary filings |
| ESG questions | 15 | AFME ESG + BNY sustainability report |
| Adversarial (no answer in corpus) | 10 | Hand-crafted; tests the L02 citation guardrail's halt path |

### 6.2 Per-item structure

```jsonc
{
  "eval_id": "ev_<ulid>",
  "framework": "AFME | CAIQ | ADV | AFME_ESG | ADVERSARIAL",
  "framework_question_ref": "AFME-IS-3.4 | ...",
  "raw_question_text": "...",
  "expected_canonical_id": "canon.is.access_control.privileged_access_review",
  "expected_evidence_spans": [
    { "doc_hash": "...", "span_hash": "...", "anchor": {...} }
  ],
  "expected_verdict": "pass | halt | escalate",
  "notes": "..."
}
```

### 6.3 What it drives

- **L05 mapping precision** (`SPEC.md` §L05 AC #1) — measured against `expected_canonical_id`.
- **L03 recall@k** (`SPEC.md` §L03 AC #1) — measured against `expected_evidence_spans`.
- **L06 hallucination rate** (`SPEC.md` §L06 AC #2) — every claim in DraftComposer output checked against the evidence bundle.
- **L02 citation resolution** (`SPEC.md` §L02 AC #2) — adversarial slice ensures the halt path is exercised.

### 6.4 Acceptance criteria

1. 100 items checked into `evals/fixtures/v0/` with hashes pinned to corpus v0.
2. Eval harness in `evals/runners/` runs all 100 and emits `evals/reports/v0-baseline.json`.
3. Thresholds in `evals/thresholds.yaml` set with v0 numbers as floor; CI blocks promotion on regression.

---

## 7. Repository additions — what gets added under `SPEC.md` §3

The data plan requires no new top-level directories. It adds:

```
ddq-platform/
├── data/
│   ├── sources/                          # vendored or fetched-on-demand
│   │   ├── afme/
│   │   │   ├── ddq-2024-custodian.docx
│   │   │   ├── ddq-2024-csd.docx
│   │   │   └── esg-ddq.pdf
│   │   ├── caiq/
│   │   │   ├── ccm-v4.1.xlsx
│   │   │   ├── caiq-v4.1.json           # CSA machine-readable bundle
│   │   │   └── ccm-mappings.json
│   │   ├── nist/
│   │   │   ├── csf-2.0.json             # OSCAL
│   │   │   └── sp800-53-rev5.json       # OSCAL
│   │   └── README.md                    # licenses + provenance for every file
│   ├── bootstrap/
│   │   ├── 01_fetch_edgar.py            # SEC EDGAR ingest
│   │   ├── 02_fetch_bny_ir.py           # BNY investor relations ingest
│   │   ├── 03_parse_caiq.py             # CAIQ JSON → canonical seeds
│   │   ├── 04_parse_afme.py             # AFME docx → canonical seeds
│   │   ├── 05_parse_adv.py              # Form ADV CSV → canonical seeds
│   │   ├── 06_build_taxonomy_v0.py      # merge + dedup + version-cut
│   │   ├── 07_seed_library.py           # generate ~50 library entries
│   │   └── 08_build_evalset_v0.py       # generate 100 eval items
│   └── manifests/
│       ├── corpus-v0.json               # all doc_hashes + provenance
│       └── taxonomy-v0.1.json           # signed snapshot manifest
└── evals/
    └── fixtures/
        └── v0/                          # 100 eval items
```

Bootstrap scripts are executed in numeric order. Each writes through the production `core/ports/` interfaces — the in-memory adapter set during dev, real adapters once L01 is up.

---

## 8. Build sequence (replaces / precedes `SPEC.md` §10 M1)

This sequence runs **before or alongside** M1 of the spec. Roughly two weeks of work for one engineer; less if parallelized.

### Day 1–2 — Vendor & verify
- Download every public source listed in §1 into `data/sources/`.
- Record SHA-256 of each artifact in `data/sources/README.md`.
- Verify CAIQ machine-readable JSON loads cleanly; verify CCM mapping bundle covers NIST 800-53, ISO 27001, PCI, SOC 2.

### Day 3–4 — EDGAR & IR ingest
- `01_fetch_edgar.py`: pull BNY Mellon Corp filings (10-K, 10-Q, 8-K, DEF 14A) for last 5 years via `data.sec.gov/submissions/CIK0001390777.json`. Honor 10 req/sec, set `User-Agent`.
- `02_fetch_bny_ir.py`: scrape Pillar 3 + sustainability PDFs from `bny.com/corporate/global/en/investor-relations/`.
- Identify BNY adviser subsidiary CIKs via IAPD; pull their ADV filings.
- Store raw to `s3://bny-ddq-knowledge-raw/...` (LocalStack in dev).

### Day 5–7 — Parse & index
- Run Unstructured.io on every PDF; produce `(doc_id, section_id, span_id, text, anchor, hash)` tuples per `SPEC.md` §L03.
- Write Parquet shadow.
- Index into OpenSearch (BM25) + Qdrant (dense embeddings via Bedrock Titan or equivalent — abstracted behind `LLMClient`).

### Day 8–9 — Canonical taxonomy v0.1
- `03_parse_caiq.py`: CAIQ JSON → ~261 canonical entries with full CCM-derived mappings.
- `04_parse_afme.py`: AFME Excel → ~250 entries.
- `05_parse_adv.py`: ADV Part 1 schema → ~80 entries.
- `06_build_taxonomy_v0.py`: dedup via embedding similarity, assign `canonical_id`s, attach `framework_mappings`, write to Mongo, cut signed v0.1 snapshot to S3.

### Day 10–11 — Library v0
- `07_seed_library.py`: 50 entries hand-curated from public corpus, each with real `(doc_hash, span_hash, anchor)` evidence refs. Run through validator stub.

### Day 12 — Eval set v0
- `08_build_evalset_v0.py`: 100 items, structured per §6.2, committed to `evals/fixtures/v0/`.

### Day 13–14 — Wire it up
- Run the L07 graph end-to-end on 5 eval items using the bootstrap library and corpus.
- Capture baseline metrics into `evals/reports/v0-baseline.json`.

At this point the platform demos a real query, real retrieval, real citation, real validation — entirely from public sources. M2 of the spec (the spine) builds against this from day one.

---

## 9. Risks, gaps, and what to flag to the architecture board

1. **SIG license gap.** The platform demonstrably works without it, but coverage of `canon.is.*` is partial until SIG content is licensed. Procurement decision needed in parallel; ~$6,500/yr.
2. **CCM machine-readable bundle versioning.** CSA cuts new CAIQ versions yearly. Pin to `v4.1` in the bootstrap; plan a re-run procedure when v4.2 ships.
3. **EDGAR rate-limit.** SEC's 10 req/sec is enforced. Bootstrap script must implement backoff. Don't run bootstrap from CI without a token bucket.
4. **BNY adviser subsidiary identification.** Manual at first — IAPD search by entity name. Worth a small spike to map all known subsidiaries' CIKs into a config file.
5. **Anchor stability across PDF re-uploads.** If BNY republishes a 10-K with cosmetic changes, page numbers shift. Anchor strategy MUST prefer section-level over page-level when section structure is reliably parseable.
6. **Bootstrap library tagged "do not ship".** OPA policy MUST exclude `tags: ["bootstrap"]` entries from any production outbound response. Add an explicit policy + test before any non-dev environment exists.
7. **License attribution.** CSA requires attribution for redistribution. If the canonical taxonomy is ever exported, attribution clauses are surfaced in the export. Cover in the taxonomy snapshot's `signed_by` block.

---

## 10. What this plan does NOT do

For clarity, what's deliberately deferred:

- Real BNY-internal policies, procedures, control evidence — wait for internal access.
- Real client DDQ history — wait for ops team to share past responses.
- SME-defensible library entries — these need real SMEs; the seed library is demo-grade only.
- The full 500-question regression set — v0 is 100; the rest comes from real DDQ history.
- SIG content — wait for license.

These are all unblocked the moment internal access lands, and none of them block the platform from being demoable end-to-end on public data.

---

## 11. Reading order alongside `SPEC.md`

1. `SPEC.md` §1 (invariants) — the contract.
2. `DATA-PLAN.md` §1 (sources) — what you actually have to work with.
3. `DATA-PLAN.md` §8 (build sequence) — what to do this week.
4. `SPEC.md` §4 (layers) — the architecture this data populates.
5. `SPEC.md` §10 (build sequencing) — what to build once data is live.

---

*End of data plan. Update via PR; tag `@architecture-board` for any source/license changes.*

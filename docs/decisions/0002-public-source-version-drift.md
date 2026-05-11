# ADR 0002 — Public source version drift vs. DATA-PLAN §1

**Status:** Accepted (2026-05-08)
**Driver:** Day 1–2 vendor pass uncovered three places where the live public
source has drifted from what `docs/DATA-PLAN.md` §1 names. Documenting the
deltas so the taxonomy bootstrap (`03_parse_caiq.py`, `04_parse_afme.py`)
can be written against ground truth, not the plan-as-of-Q1.

## Discovered drift

### 1. CAIQ machine-readable: v4.1 (plan) vs v4.0.3 (CSA today)

DATA-PLAN §1 names "CAIQ v4.1 (full) — `.xlsx` + JSON + YAML + OSCAL". Live
CSA distribution (verified 2026-05-08):

| Bundle | Generated | Contents |
|---|---|---|
| `ccm-machine-readable-bundle-json-yaml-oscal` | 2024-06-03 | CCM v4.0.12 + CAIQ v4.0.3 in JSON + YAML; CCM v4.0.12 in OSCAL |
| `cloud-controls-matrix-v4-1` | 2026-01-13 | CAIQ v4.1.0 + CCM v4.1.0 — **xlsx only**; PDF guidance |

CAIQ v4.1 ships only as XLSX as of today. JSON / YAML / OSCAL is still v4.0.3
/ v4.0.12. Record count holds at 261 across versions, so canonical ID counts
in DATA-PLAN §4.1 ("CAIQ v4.1 JSON … 261 questions") remain valid; the JSON
parse just lands on v4.0.3 content.

**Decision.**
- `03_parse_caiq.py` parses the **JSON v4.0.3** dataset for canonical IDs +
  framework mappings. The mapping bundles (NIST 800-53 rev5, ISO 27001:2022,
  PCI DSS v4.0, AICPA TSC 2017) are all present in the JSON dataset.
- We separately track the **v4.1 XLSX** for delta review — when CSA publishes
  the v4.1 machine-readable bundle, we'll re-cut canonical IDs.
- Taxonomy snapshot tag is `tx_v0.1` regardless; we record both source
  versions in the snapshot's signed manifest.

### 2. AFME DDQ: 2024 (plan) vs 2026 (live)

DATA-PLAN §1 names "AFME DDQ 2024". Today's AFME publications page lists
the 2026 versions; 2024 is no longer published. Hashes vary (revisions
between 2024 and 2026 include question reordering and added items per
AFME's release notes — to be reviewed by SME during taxonomy seeding).

**Decision.**
- Vendor the 2026 versions. Record version in `framework_mappings.version`
  per `ddq.md` §L05 schema (e.g., `{ "framework": "AFME", "version": "2026", ... }`).
- Add the 2024 versions to the deferred sources list if a back-mapping is
  ever needed for legacy library entries; not required for v0 demo.

### 3. AFME ESG DDQ: doesn't exist as a standalone

DATA-PLAN §1 names "AFME ESG DDQ". The closest live publication is
"AFME Recommended ESG Disclosure and Diligence Practices for the European
High Yield Market — Jan 2026" (HY-scoped, not a generic ESG DDQ).

**Decision.**
- Vendor the HY ESG document and tag canonical IDs derived from it as
  `tags: ["sig-candidate", "scope:eu-hy"]` to flag scope on use.
- Defer broader ESG canonical seeding to AFME ESG content from the BNY
  sustainability report (DATA-PLAN §3 Day 3–4 ingest), where the canonical
  IDs are entity-specific anyway.

## Mapping naming: SOC 2 vs AICPA TSC

Not drift, just naming: DATA-PLAN names "SOC 2" mappings; CSA names them
`AICPA_TSC_2017` (the underlying Trust Services Criteria; SOC 2 is the audit
product). `verify_sources.py` recognizes both. No further action.

## Consequences

- DATA-PLAN §1 source manifest is **out of date**. Update via PR alongside
  this ADR — point readers at this ADR for the why.
- Acceptance criteria in DATA-PLAN §4.5 ("CAIQ v4.1 framework_mappings ≥
  95%") remain attainable; the mappings are present in the v4.0.3 JSON
  bundle.
- Re-vendor cadence (DATA-PLAN §1 "Refresh cadence") still holds — annual,
  Q1 each year.

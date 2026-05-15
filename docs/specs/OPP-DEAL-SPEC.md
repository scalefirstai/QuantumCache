# BNY Asset Servicing — Opportunity-to-Deal Platform — Technical Specification

**Doc:** SA-2026-0143 · **Status:** DRAFT v0.1 · **Classification:** Internal · **Companion to:** `SPEC.md` (DDQ Platform)
**Audience:** Engineers building this in Claude Code. Assume competence; skip the marketing.

---

## 0. Reading guide

This spec is the build contract for the eight-stage platform that runs Asset Servicing opportunities from inbound lead through sealed, contracted deal — integrating eCRM, the Universal Client Master (UCM), the Universal Product Master (UPM), the DDQ platform, complexity scoring, operational cost modeling, technology capacity analysis, pricing, and operating-model / FTE planning into one journaled workflow. The durable asset is the **deal baseline**: the sealed bundle that the eventual contract is measured against and that compounds into pricing and capacity intelligence over time.

**Relationship to `SPEC.md`:** the DDQ platform is one *consumer* of UCM/UPM and one *producer* of commitments that this platform contracts. Stage S03 of this spec wraps the DDQ platform; commitments captured in DDQ library entries flow forward as enforceable contract schedule items here.

**Build order (recommended):** S00 (canonical entities — UCM, UPM, app registry, location/role catalogue) → S08 (deal journal, the audit spine) → S01 (intake + eCRM hub) → S02 (product scoping) → S04 (complexity) → S05 (cost) → S06 (pricing) → S07 (operating model) → S03 (DDQ integration) → S08 surfaces. Like `SPEC.md`, validation/observability/eval are cross-cutting.

**Conventions in this doc:**
- `MUST` / `SHOULD` / `MAY` follow RFC 2119.
- Code/identifiers in `monospace`. Schemas in JSON-ish for clarity, not ceremony.
- Every section ends with **Acceptance criteria** — what "done" means for that piece.

---

## 1. System invariants (read this first, refer back often)

These hold for every stage, every code path, every PR. Violation = halt.

1. **No opportunity without UCM resolution.** An opportunity record cannot exist in eCRM without a resolved UCM entity tree. Net-new entities pass through a KYC kickoff gate that produces a UCM ID before the deal advances.
2. **No product scope without UPM resolution.** Every line item in the deal scope MUST resolve to a UPM product code with a current `effective` status in the requested jurisdiction(s).
3. **Capacity is priced, not assumed.** Every UPM product code in scope resolves to its delivery app stack. Any app whose projected post-deal load exceeds its capacity envelope triggers a capacity decision (expand or decline) before pricing closes.
4. **FTE plans honor the location strategy.** FTE allocation respects the published BNY Asset Servicing global delivery location strategy (which functions can be performed in which centers) and the role-level location eligibility matrix. Cost-optimal allocations that violate the strategy are rejected, not warned.
5. **DDQ commitments are contractual.** Any commitment made in a sealed DDQ response that materially affects operating model or controls (SLA, control statement, jurisdiction coverage, data residency) flows into the contract schedule. Pricing and operating-model stages MUST consume the live DDQ run state for in-flight prospects.
6. **Complexity tier gates everything downstream.** Approval authority, pricing committee composition, operating model review depth, and the cost-model variance threshold are all derived from the deal's complexity tier. Tier reassessment is journaled.
7. **Sealed deal bundles are immutable and reproducible.** Once a deal is sealed (S3 Object Lock), the bundle — cost stack, pricing, operating model, FTE plan, app impact, DDQ commitment set — is bit-exact reproducible. Actuals are measured against this baseline.
8. **Total client value, not headline fee.** Every pricing decision MUST surface the full client P&L: asset-based fees, transaction fees, sec lending revenue share, FX revenue, NII on operating balances, adjacent revenue (Markets, Wealth, Pershing cross-sell). Headline-bp-only pricing approvals are rejected by policy.
9. **No override bypasses approval gates.** Tier-based approval gates are enforced by policy; any override is a journaled event with named CFO / segment CEO approval.

---

## 2. Stack of record

| Concern | Choice | Notes |
|---|---|---|
| Live transactional state | **MongoDB Atlas** (M40+, multi-region) | Same posture as `SPEC.md`; abstract via repository pattern |
| Durable / immutable artifacts | **S3** with Object Lock (Compliance mode) | Sealed deal bundles, sealed UCM/UPM snapshots |
| Analytical reads | **DuckDB** over S3 Parquet | Win/loss analytics, actuals-vs-baseline, capacity forecast |
| Workflow orchestration | **LangGraph** + **Temporal** | Deal workflows span weeks/months with human gates — Temporal's durability is the point |
| eCRM | **Salesforce Financial Services Cloud** (assumed BNY standard) | Adapter in `infra/adapters/ecrm/`; spec abstracts behind `OpportunityRepo` |
| UCM | **Internal BNY UCM service** | Read via stable API; cache versioned snapshots locally for reproducibility |
| UPM | **Internal BNY UPM service** | Same pattern as UCM |
| App and capacity registry | **Internal service** (new build — see §9) | Source of truth for app inventory, capacity envelopes, cost-to-serve rates |
| Role/rate catalogue | **Internal HR + Finance data** via warehouse | Location-eligibility matrix, fully-loaded rates by role × location |
| Sub-custodian rate cards | **Network management feed** | Refreshed quarterly; per-market fees and SLAs |
| LLM access | **AWS Bedrock** with **Anthropic API** fallback | For agents in S04 (complexity), S05 (cost narrative), S07 (operating model narrative) |
| LLM models | Claude **Opus 4.7** (synthesis), **Sonnet 4.6** (drafting), **Haiku 4.5** (classification) | Tier-routed per agent budget |
| Policy engine | **OPA** | Approval gates, location-strategy enforcement, override audit |
| State cache | **Redis** | Deal-state cache, idempotency keys |
| Pricing engine | **Internal numeric service** (Python, deterministic) | Not an LLM — pricing math is deterministic, auditable, and stress-tested |
| Cost engine | **Internal numeric service** (Python, deterministic) | Same posture as pricing — LLMs draft narratives, not numbers |
| Capacity engine | **Internal numeric service** (Python, deterministic) | Consumes app registry; produces fits/expansions list |
| Tracing | **Langfuse** + **OpenTelemetry** | |
| Audit / SIEM | **AWS CloudTrail** + **Splunk** | |
| API gateway / surface | **FastAPI** + **React + TypeScript** | |
| Auth | **OIDC via Okta**, mTLS service-to-service | |
| Languages | **Python 3.12**, **TypeScript**, **Rego** | |

**Repository pattern is mandatory** — same as `SPEC.md` §2. eCRM, UCM, UPM, app registry, role catalogue, sub-custodian feed are each accessed through interfaces in `core/ports/`. Tests use in-memory adapters; integration tests use real services via testcontainers or recorded fixtures (for the internal BNY systems).

---

## 3. Repository layout

```
opp-deal-platform/
├── apps/
│   ├── api-gateway/              # FastAPI, public-facing API
│   ├── ui/                       # React + TS, deal workspace + approval consoles
│   ├── orchestrator/             # LangGraph + Temporal worker
│   └── ingest-worker/            # RFP / inbound document ingestion
├── services/
│   ├── intake/                   # S01 — inbound RFP/lead intake
│   ├── opportunity/              # S01 — eCRM hub adapter + opportunity domain
│   ├── client-resolver/          # S01 — UCM resolution + hierarchy walk
│   ├── product-scoper/           # S02 — UPM resolution + app-stack expansion
│   ├── ddq-bridge/               # S03 — links to DDQ platform (run lifecycle, commitments)
│   ├── complexity/               # S04 — scoring engine
│   ├── cost/                     # S05 — operational cost model
│   ├── capacity/                 # S05 — technology capacity analyzer
│   ├── pricing/                  # S06 — pricing engine + total-client-value model
│   ├── operating-model/          # S07 — FTE plan, org design, app impact, controls
│   ├── approval/                 # S08 — tier-gated approval workflows
│   └── deal-journal/             # S08 — append-only deal event journal
├── core/                         # Domain logic, no I/O
│   ├── domain/                   # Entities, value objects
│   ├── ports/                    # Interfaces
│   └── policies/                 # Pure validation logic
├── infra/
│   ├── adapters/                 # eCRM (Salesforce FSC), UCM, UPM, app-registry, role-catalogue, sub-custody-feed, ...
│   ├── terraform/
│   ├── helm/
│   └── opa-policies/             # Rego files (approval gates, location strategy)
├── packages/
│   ├── schemas/
│   ├── deal-sdk/
│   └── llm-sdk/
├── evals/                        # Backtesting suite (see §9.3)
│   ├── fixtures/
│   ├── runners/
│   └── reports/
├── docs/
│   ├── runbooks/
│   └── decisions/
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

Service-to-service traffic identical pattern to `SPEC.md` §3: HTTP+Pydantic contracts, async via Temporal.

---

## 4. The eight stages

Each stage subsection contains: **Responsibility** · **Interfaces** · **Schemas** · **Behavior** · **Risks/edge cases** · **Acceptance criteria**.

---

### S01 · Intake, eCRM hub, and client resolution

**Responsibility.** Capture an inbound opportunity from any channel; resolve the prospect to UCM (existing entity tree or new-entity KYC kickoff); create the canonical opportunity record in eCRM as the deal's hub; populate the relationship graph (existing book, at-risk revenue, cross-sell adjacencies, related entities already serviced).

**Channels in scope.**
- Inbound RFP via email to a shared deal inbox or RFP portal
- RM-submitted opportunity via eCRM directly
- Consultant-driven RFP (bfinance, Mercer, Aon, WTW, Cambridge Associates)
- Cross-segment referral from Markets, Wealth, Pershing, Treasury Services
- Re-tender / renewal trigger from an existing client (lifecycle event in eCRM)

**Interfaces.**
```python
class IntakeService(Protocol):
    def ingest(self, source: IntakeSource, payload: IntakePayload) -> OpportunityDraft: ...

class ClientResolver(Protocol):
    def resolve(self, signals: ClientSignals) -> ClientResolution: ...
    # returns either a UCM entity tree or a NewEntityKycRequest

class OpportunityRepo(Protocol):
    def create(self, draft: OpportunityDraft, resolution: ClientResolution) -> OpportunityId: ...
    def get(self, opp_id: OpportunityId) -> Opportunity: ...
    def update(self, opp_id: OpportunityId, patch: OpportunityPatch) -> None: ...
```

**Schemas.**
```jsonc
// Opportunity — Mongo "opportunities" + mirrored to eCRM
{
  "opportunity_id": "opp_<ulid>",
  "ecrm_id": "006...",                          // Salesforce id
  "status": "intake | resolving | scoping | ddq | pricing | approval | won | lost | withdrawn",
  "source": { "channel": "rfp_email | rm_submitted | consultant | cross_segment | retender",
              "consultant": "bfinance | mercer | aon | wtw | cambridge | null",
              "received_at": "RFC3339",
              "raw_artifacts": ["s3://..."] },
  "client": {
    "ucm_id": "ucm_<...>",                      // null until resolved; resolution event journaled
    "ucm_snapshot_version": "ucm_v2026.05.13",
    "entity_tree_roles": [
      { "role": "manco | aifm | fund_umbrella | sub_fund | share_class | plan_sponsor | mandate", "ucm_id": "ucm_<...>" }
    ],
    "kyc_status": "complete | refresh_due | new_entity_in_progress",
    "client_segment": "asset_manager | asset_owner_pension | sovereign | insurance | alts_manager"
  },
  "relationship_context": {
    "existing_revenue_usd_annual": 12500000,
    "existing_products": ["custody", "fund_admin"],     // UPM codes
    "cross_sell_pipeline": [...],
    "at_risk_book": { "competitor_clients_in_scope": [...], "internal_substitution_revenue_usd": 0 },
    "named_relationships": { "rm": "u_...", "exec_sponsor": "u_..." }
  },
  "scope_summary": {
    "products_requested": ["custody_global", "fund_accounting", "to_admin"],   // UPM codes; details in S02
    "jurisdictions": ["IE", "LU", "US", "KY"],
    "estimated_aum_usd": 85000000000,
    "indicative_go_live": "2027-01-01"
  },
  "ddq_run_id": "run_<...> | null",             // linked once S03 starts
  "created_at": "...", "updated_at": "..."
}
```

**Behavior.**
- RFP intake: documents parsed via Unstructured.io (reuse DDQ platform's ingestion); structured fields extracted (client name, requested products, target AUC, deadline). Operator confirms before opportunity is created.
- Client resolution: a deterministic match against UCM by LEI first, then by legal name + jurisdiction. Below match-confidence threshold → manual review queue. Asset manager entity trees are deep — the resolver MUST walk the tree and present **all** related entities (ManCo, AIFM, fund umbrellas, sub-funds, share classes) so the deal team sees the full surface area.
- Asset-owner clients have a different tree shape: plan sponsor → individual plans → underlying mandate managers (who may themselves be BNY Asset Servicing clients, surfaced as "cross-leg" relationships for revenue picture).
- The UCM snapshot version is pinned on opportunity creation; downstream stages read against that pin. Replay requires the pinned UCM snapshot.
- Existing book and at-risk analysis: query UCM relationship graph + finance warehouse for current revenue. Surface conflicts (competitor mandates, regulatory conflicts of interest) to the deal team explicitly.
- Every opportunity creation/update emits a `deal_journal` event (S08).

**Risks.**
- Ambiguous client identity (private equity rollups, multi-LEI conglomerates) → resolution falls back to RM-confirmed identity; the resolution decision is journaled with confidence and reviewer.
- Stale UCM snapshots — UCM mutates as KYC refreshes complete; runs that exceed 90 days on a pinned snapshot get a soft warning to re-pin.
- eCRM sync drift — eCRM is the system of record for sales pipeline; this platform's `Opportunity` doc is a control-plane mirror. Conflict resolution: eCRM wins for commercial fields (forecast amount, stage); this platform wins for engineered fields (complexity tier, sealed bundle ref).

**Acceptance criteria.**
1. 100% of created opportunities have a non-null `client.ucm_id` and pinned `ucm_snapshot_version`.
2. Entity-tree completeness: for an asset manager opportunity, the resolver returns ≥ ManCo + ≥1 fund umbrella + ≥1 sub-fund where they exist in UCM.
3. Bidirectional sync probe: an opportunity created in eCRM appears here within 60s; an opportunity created here appears in eCRM within 60s.
4. Existing-book query: for any client, surface current annual revenue and current product set within 2s P95.

---

### S02 · Product scoping against UPM

**Responsibility.** Decompose the opportunity into canonical UPM product codes, jurisdiction-scoped, with full delivery app-stack expansion. Produce the **scope manifest** that S04/S05/S06/S07 all consume.

**UPM product set (Asset Servicing scope — illustrative, not exhaustive).**

| Product family | UPM codes (representative) |
|---|---|
| Custody | `custody.global`, `custody.subcustody.network`, `custody.fx_standing_instruction`, `custody.income_collection`, `custody.corporate_actions` |
| Fund accounting | `fa.daily_nav`, `fa.intraday_nav_etf`, `fa.monthly_nav`, `fa.multi_class`, `fa.multi_currency`, `fa.expense_accrual` |
| Fund administration | `fadmin.financial_reporting`, `fadmin.regulatory_reporting.ucits`, `fadmin.regulatory_reporting.aifmd`, `fadmin.regulatory_reporting.us40act`, `fadmin.board_reporting` |
| Transfer agency | `ta.lux`, `ta.dublin`, `ta.us`, `ta.dealing_daily`, `ta.aml_kyc_investor` |
| ETF services | `etf.create_redeem`, `etf.basket_calc`, `etf.ap_management` |
| Alts | `alts.pe_admin`, `alts.private_credit_admin`, `alts.real_estate_admin`, `alts.hedge_admin`, `alts.investor_services` |
| Middle office | `moo.trade_lifecycle`, `moo.ibor`, `moo.abor`, `moo.recon`, `moo.otc_derivatives_ops` |
| Collateral | `collat.triparty`, `collat.segregated`, `collat.otc_margin` |
| Sec lending | `seclen.agency` |
| FX | `fx.standing_instruction`, `fx.restricted_markets`, `fx.execution` |
| Data & analytics | `data.eagle_pace`, `data.eagle_access`, `data.performance`, `data.risk_analytics`, `data.esg` |
| Depositary | `depo.ucits`, `depo.aifmd` |
| Connectivity | `conn.nexen_portal`, `conn.swift`, `conn.fix`, `conn.sftp_reporting`, `conn.api` |

**Each UPM code carries.**
```jsonc
// UpmProduct — read-only mirror of internal UPM service
{
  "upm_code": "fa.daily_nav",
  "label": "Daily NAV Fund Accounting",
  "eligible_jurisdictions": ["IE", "LU", "US", "KY", "SG", "HK", "UK"],
  "regulatory_permissions_required": [
    { "jurisdiction": "IE", "permission": "fund_administrator_authorisation_cbi" }
  ],
  "delivery_stack": [
    { "app_id": "app.invest_one.prod", "role": "primary_accounting", "load_factor": "per_nav_strike" },
    { "app_id": "app.eagle_pace.prod", "role": "data_layer", "load_factor": "per_holding" },
    { "app_id": "app.nexen.prod", "role": "client_portal", "load_factor": "per_user" }
  ],
  "dependencies": ["custody.global", "data.eagle_pace"],   // hard dependencies; missing → invalid scope
  "bny_legal_entity_options": ["bny_fund_services_ireland", "bny_mellon_sa_nv"],
  "status": "active | sunsetting | restricted",
  "version": 17
}
```

**Interfaces.**
```python
class ProductScoper(Protocol):
    def scope(self, opp_id: OpportunityId, raw_requests: list[RawProductRequest]) -> ScopeManifest: ...
    def validate_scope(self, manifest: ScopeManifest) -> list[ScopeIssue]: ...

class ScopeManifest(BaseModel):
    opportunity_id: OpportunityId
    upm_snapshot_version: str
    line_items: list[ScopeLineItem]
    legal_entity_assignment: dict[str, BnyLegalEntity]   # per fund umbrella → servicing entity
    derived_app_set: list[AppId]                          # union of all delivery apps
    derived_jurisdictions: list[Jurisdiction]
    issues: list[ScopeIssue]                              # eligibility, dependency, permission gaps
```

**Behavior.**
- Operator (deal team) or LLM-assisted parser (S01 ingestion output) produces `RawProductRequest` entries.
- Scoper resolves each request against UPM (current snapshot pinned at scope creation), checks eligibility against requested jurisdictions, walks `dependencies` to add implicit products, expands `delivery_stack` to produce `derived_app_set`.
- Legal-entity assignment per fund umbrella is policy-driven: e.g., a UCITS umbrella in Ireland must be serviced via `bny_fund_services_ireland`; a Lux SICAV via `bny_mellon_sa_nv` for depositary. OPA policies in `infra/opa-policies/legal-entity-routing/`.
- `derived_app_set` is the join key for S05 capacity analysis. Scoper does NOT compute load — only enumerates apps. The capacity engine consumes this set with volume estimates.
- `ScopeIssue` examples: requested product not eligible in jurisdiction, dependency missing (`fa.daily_nav` requested without `custody.global`), regulatory permission absent for legal entity, product status `restricted` or `sunsetting`.

**Risks.**
- UPM gaps for newly-launched products → scoper supports `provisional` codes flagged for product-management resolution.
- Multi-domicile fund ranges with shared service requirements need careful legal-entity assignment; the policy engine produces per-fund assignment with traceable rationale.
- App-set expansion is union-typed; double-counting prevented in the capacity engine.

**Acceptance criteria.**
1. Every scope manifest with `issues: []` MUST cover all upstream stages — meaning S04/S05/S06/S07 never need to query UPM directly, they consume the manifest only.
2. Dependency closure: any line item with missing hard dependency surfaces as a `ScopeIssue.severity == "blocking"` and prevents progression to S04.
3. Replay: re-running scope against the pinned `upm_snapshot_version` produces a byte-identical `ScopeManifest`.

---

### S03 · DDQ integration

**Responsibility.** Bridge to the DDQ platform (`SPEC.md`) so prospect DDQs run with the right context, and commitments captured in DDQ responses flow forward to the contract schedule.

**Interface contract with the DDQ platform.**

DDQ runs are *started by* this platform when:
- An inbound RFP includes a DDQ artifact (most asset manager and asset owner RFPs do)
- The prospect requests due diligence ahead of contracting
- A re-tender triggers refresh of standing DDQ responses

The DDQ run is scoped using outputs from S01 and S02:
- `entity` from `client.entity_tree_roles` — the specific BNY legal entity in scope
- `product` from `ScopeManifest.line_items` — the products this DDQ should answer for
- `taxonomy_version` pin from the DDQ platform (per `SPEC.md` §L05)

**Interfaces.**
```python
class DdqBridge(Protocol):
    def start_run_for_opportunity(self, opp_id: OpportunityId, ddq_artifact: S3Uri) -> RunId: ...
    def link_run(self, opp_id: OpportunityId, run_id: RunId) -> None: ...
    def get_commitment_set(self, run_id: RunId) -> CommitmentSet: ...
    def watch_run(self, run_id: RunId, on_sealed: Callable[[SealedRun], None]) -> None: ...
```

**Commitment extraction.**
```jsonc
// Commitment — derived from sealed DDQ library entries cited in the run
{
  "commitment_id": "cmt_<ulid>",
  "opportunity_id": "opp_<ulid>",
  "ddq_run_id": "run_<...>",
  "canonical_id": "canon.or.business_continuity.rto",
  "library_entry_hash": "sha256:...",
  "commitment_text": "Recovery Time Objective for core fund accounting platform is 4 hours.",
  "commitment_class": "sla | control | jurisdiction_coverage | data_residency | reporting | other",
  "material": true,                          // affects pricing/operating model? Drives propagation.
  "contract_schedule_target": "schedule_b.sla | schedule_c.controls | ...",
  "extracted_at": "..."
}
```

**Behavior.**
- For each sealed DDQ run linked to an opportunity, an extraction pass identifies **material commitments** — claims that, if delivered, require operating capability, control coverage, jurisdictional presence, or SLA adherence. A simple classifier (Haiku tier) plus rule-based filters (anything mentioning numeric SLA, control ID, certification, RTO/RPO).
- Material commitments are queued for review by the deal team and the appropriate SME (re-using the DDQ platform's SME queue infrastructure where domain matches).
- Approved commitments flow into the contract schedule template in S08.
- Cross-check at sealing: any commitment with `material: true` MUST be reflected in operating model (S07) — e.g., if RTO 4h is committed, the operating model's resilience section MUST show how it's met.

**Risks.**
- Sealed DDQ runs may be amended (rare but possible) — bridge subscribes to DDQ journal events and updates commitments accordingly.
- Commitment drift between DDQ response and operating model is the single most common post-go-live audit finding industry-wide. The cross-check in S07 is the structural defense.
- DDQ platform is a separate service with its own SLOs; if it's down, opportunity progresses up to S03 and waits.

**Acceptance criteria.**
1. Every sealed DDQ run linked to an opportunity produces a `CommitmentSet` within 5 minutes of seal.
2. Cross-check test: for a sample of 20 sealed deals, every material commitment maps to either a schedule item in the contract or an explicit operating-model section.
3. Replay parity: re-running commitment extraction against a pinned sealed DDQ run produces an identical `CommitmentSet`.

---

### S04 · Complexity measurement

**Responsibility.** Score the deal across well-defined dimensions to produce a complexity tier that routes downstream pricing approval, operating-model review depth, and modeling variance thresholds.

**Dimensions.**
```jsonc
// ComplexityScorecard
{
  "scorecard_version": "cx_v1.0",
  "dimensions": [
    { "key": "fund_count_structure", "score": 1..5, "notes": "..." },
    { "key": "jurisdictional_spread", "score": 1..5, "notes": "..." },
    { "key": "asset_class_breadth", "score": 1..5, "notes": "..." },
    { "key": "nav_cadence_sla", "score": 1..5, "notes": "..." },
    { "key": "regulatory_regime_coverage", "score": 1..5, "notes": "..." },
    { "key": "bespoke_reporting", "score": 1..5, "notes": "..." },
    { "key": "client_system_integration_footprint", "score": 1..5, "notes": "..." },
    { "key": "transition_aggression", "score": 1..5, "notes": "..." },
    { "key": "servicing_model_dedicated_vs_pooled", "score": 1..5, "notes": "..." },
    { "key": "data_residency_constraints", "score": 1..5, "notes": "..." }
  ],
  "weights": { /* per-dimension weights, sum to 1.0; version-controlled */ },
  "composite_score": 3.4,
  "tier": "T1_low | T2_standard | T3_high | T4_exceptional",
  "rationale_narrative": "...",                  // Sonnet-tier draft, deal team approves
  "scored_at": "...", "scored_by": "u_..."
}
```

**Interfaces.**
```python
class ComplexityScorer(Protocol):
    def score(self, opp_id: OpportunityId, manifest: ScopeManifest, client: ClientResolution) -> ComplexityScorecard: ...
    def reassess(self, opp_id: OpportunityId, reason: str) -> ComplexityScorecard: ...
```

**Behavior.**
- Each dimension has a deterministic rubric in `core/policies/complexity/`. E.g., `jurisdictional_spread`:
  - 1 = single domicile, single market footprint
  - 2 = 2–3 domiciles, developed markets only
  - 3 = 4–6 domiciles, includes emerging
  - 4 = 7+ domiciles, includes frontier
  - 5 = global, frontier-heavy, complex sub-custody footprint
- Inputs come from S02 manifest + S01 client context + optionally DDQ run for SLA aggression and bespoke-reporting signals.
- The narrative is LLM-drafted (Sonnet) from the rubric outputs; the deal team approves before the score locks. The score itself is deterministic.
- Tier thresholds: T1 ≤ 2.0, T2 2.0–2.9, T3 3.0–3.9, T4 ≥ 4.0 (tunable, version-controlled).
- Reassessment triggers: scope change ≥ 1 line item added/removed, AUC estimate change > 20%, jurisdiction change. Each reassessment is journaled with reason.

**Risks.**
- Sandbagging or gaming the score to route around senior approval → all scorecards are open to peer review in the deal review meeting; quarterly retrospectives compare predicted vs. actuals on cost/FTE/capacity to recalibrate weights and rubrics.
- Cold-start without history → initial weights are uniform; recalibration after 50 sealed deals.

**Acceptance criteria.**
1. Rubric coverage: every dimension has a documented 1–5 rubric with examples drawn from anonymized historical deals.
2. Reproducibility: same inputs → same score, every time. LLM narrative variation is acceptable; the numeric composite is not.
3. Calibration metric (steady state): predicted-tier vs. actual-effort correlation ≥ 0.7 on the trailing 50 sealed deals.

---

### S05 · Operational cost and technology capacity modeling

**Responsibility.** Produce the fully-loaded cost stack and the technology capacity impact. Two engines, one stage, because they share inputs and run together in the workflow.

#### S05a · Cost engine

**Inputs.** `ScopeManifest`, `ClientResolution`, `ComplexityScorecard`, volume estimates (AUC, NAV strike count, transaction count, shareholder count, capital events/year), location strategy, role/rate catalogue.

**Outputs.**
```jsonc
// CostStack
{
  "cost_stack_id": "cost_<ulid>",
  "opportunity_id": "opp_<ulid>",
  "horizon_years": 5,
  "direct_fte": [
    { "function": "fund_accounting", "location": "lux", "role": "fa_specialist_l2", "count": 12.0, "fully_loaded_rate_usd": 145000, "year": 1 },
    { "function": "custody_ops_corp_actions", "location": "pune", "role": "ca_specialist_l1", "count": 8.0, "fully_loaded_rate_usd": 38000, "year": 1 }
    // ... by year
  ],
  "sub_custody_passthrough": [
    { "market": "BR", "annual_usd": 280000 },
    { "market": "NG", "annual_usd": 95000 }
  ],
  "technology_run_cost": [
    { "app_id": "app.invest_one.prod", "annual_usd": 320000, "basis": "per_nav_strike_share" }
  ],
  "technology_capacity_expansion": [
    { "app_id": "app.invest_one.prod", "expansion_cost_usd": 450000, "one_time": true, "lead_time_weeks": 12 }
  ],
  "transition_one_time": {
    "implementation_fte_usd": 1850000,
    "parallel_running_usd": 320000,
    "data_migration_usd": 180000,
    "client_integration_build_usd": 240000
  },
  "risk_compliance_overhead": [
    { "function": "aml_monitoring", "annual_usd": 95000 }
  ],
  "allocated_overhead_pct": 0.18,
  "totals": {
    "year_1_total_usd": 8650000,
    "year_2_total_usd": 6940000,
    "year_3_total_usd": 7080000,
    "five_year_npv_usd": 32400000
  }
}
```

**Behavior.**
- Deterministic: every number traceable to an input × a rate × a count. No LLM in the numeric path.
- Volume estimates: produced from a combination of (a) RFP-stated volumes (often present), (b) UCM-derived for existing book, (c) industry benchmarks for the client profile (per asset class, per AUC band).
- FTE counts derived from scaling formulas per function — e.g., `fund_accounting.fa_specialist_l2_count = ceil(nav_strikes_per_day × complexity_factor / productivity_norm)`. Formulas in `core/policies/cost/scaling/`, version-controlled.
- Location assignment: optimization respects the location-eligibility matrix. Solver minimizes cost subject to (i) location strategy constraints, (ii) client data-residency requirements from S03 commitments, (iii) regulatory presence requirements per jurisdiction.
- Sub-custody costs: looked up from the sub-custodian rate card feed; assume 80% pass-through to client unless deal-specific, in which case the residual is BNY cost.
- LLM-drafted narrative explains the cost stack to the approval committee — deterministic numbers, drafted commentary.

#### S05b · Capacity engine

**Inputs.** `ScopeManifest.derived_app_set`, volume estimates, app registry (capacity envelopes, current utilization).

**App registry shape.**
```jsonc
// AppCapacityProfile — internal app registry record
{
  "app_id": "app.invest_one.prod",
  "label": "InvestOne Production",
  "domain": "fund_accounting",
  "current_utilization": {
    "nav_strikes_per_day_capacity": 4200,
    "nav_strikes_per_day_current": 3650,
    "storage_tb_capacity": 480,
    "storage_tb_current": 412,
    "batch_window_minutes_capacity": 360,
    "batch_window_minutes_current": 285
  },
  "expansion_options": [
    { "step": "scale_out_compute", "delta_capacity_pct": 25, "cost_usd_one_time": 450000, "lead_time_weeks": 12 }
  ],
  "sunset_status": "active",
  "cost_per_nav_strike_usd": 0.85
}
```

**Outputs.**
```jsonc
// CapacityImpact
{
  "capacity_impact_id": "cap_<ulid>",
  "opportunity_id": "opp_<ulid>",
  "app_impacts": [
    {
      "app_id": "app.invest_one.prod",
      "projected_delta": { "nav_strikes_per_day": 380, "storage_tb": 22, "batch_window_minutes": 38 },
      "post_deal_utilization_pct": { "nav_strikes_per_day": 96.0, "storage_tb": 90.4, "batch_window_minutes": 89.7 },
      "verdict": "expansion_required | fits_in_headroom | declining_risk",
      "recommended_action": "scale_out_compute",
      "expansion_cost_usd": 450000,
      "lead_time_weeks": 12
    }
  ],
  "blocking_constraints": [
    { "app_id": "...", "constraint": "batch_window_will_exceed_360min_at_t0_nav_sla", "severity": "high" }
  ]
}
```

**Behavior.**
- Capacity engine is deterministic. Volume → app load delta via the `load_factor` declared on each UPM `delivery_stack` entry (see S02).
- Any `verdict: expansion_required` flows back into `CostStack.technology_capacity_expansion`. Lead time is critical input to S07 transition planning.
- Any `blocking_constraints` with `severity: high` force a deal decision before pricing: expand, descope, or decline. Surfaced at the approval gate explicitly.

**Risks.**
- Capacity envelopes drift over time as tech adds load from other deals — registry is updated continuously; capacity analysis pins a snapshot at run time so the deal is consistent with itself.
- Some apps share underlying infra (e.g., Eagle PACE feeds many products) — the registry models this through shared-resource pools to avoid double-counting headroom.
- The app registry is the riskiest data dependency in the whole platform — see §9.

**Acceptance criteria (S05 combined).**
1. Determinism: same inputs produce byte-identical `CostStack` and `CapacityImpact`.
2. Traceability: every line in `CostStack.direct_fte` traces back to a scaling formula × a UPM line item × a location decision.
3. Capacity sanity: a deal that doubles existing AUC for a given product MUST show app utilization increase commensurate with the load factor; tested via fixture.
4. Expansion propagation: any `expansion_required` verdict triggers a `CostStack.technology_capacity_expansion` entry within the same run.

---

### S06 · Pricing

**Responsibility.** Produce the pricing proposal with full fee structure, total-client-value model, margin analysis at proposed price, and sensitivity to volume assumptions.

**Inputs.** `CostStack`, `ComplexityScorecard`, `ScopeManifest`, `ClientResolution`, competitive context (win/loss history from eCRM + analytics), target margin policy.

**Outputs.**
```jsonc
// PricingProposal
{
  "pricing_proposal_id": "px_<ulid>",
  "opportunity_id": "opp_<ulid>",
  "fee_structure": {
    "asset_based": [
      { "asset_class": "developed_eq", "tier_bp": [ {"aum_band_usd": [0, 5e9], "bp": 1.5}, {"aum_band_usd": [5e9, 20e9], "bp": 1.0} ] },
      { "asset_class": "alts_pe", "tier_bp": [ {"aum_band_usd": [0, 2e9], "bp": 9.0} ] }
    ],
    "transactional": [
      { "event": "trade_settlement", "fee_usd": 4.50 },
      { "event": "corp_action", "fee_usd": 18.00 },
      { "event": "nav_strike", "fee_usd": 85.00 }
    ],
    "fixed_retainers": [ { "service": "board_reporting", "annual_usd": 240000 } ],
    "passthrough_oop": ["sub_custody", "swift", "regulatory_fees"],
    "minimum_fee_floor_usd_annual": 4200000,
    "term_years": 5,
    "term_discount_pct": 0.08,
    "bundled_discount_pct": 0.05
  },
  "sec_lending_revenue_share": { "client_pct": 75, "bny_pct": 25 },
  "fx_revenue_model": { "standing_instruction_margin_bp": 2.5, "disclosure_class": "transparent" },
  "total_client_value": {
    "year_1": {
      "direct_fee_usd": 9200000,
      "sec_lending_revenue_usd": 1450000,
      "fx_revenue_usd": 820000,
      "nii_on_balances_usd": 1100000,
      "adjacent_revenue_usd": { "markets_fx_execution": 340000, "treasury_services": 180000 }
    },
    "five_year_total_usd": 64500000
  },
  "margin_analysis": {
    "year_1_direct_margin_pct": 0.062,
    "year_1_total_margin_pct": 0.215,
    "five_year_npv_usd": 14800000,
    "irr_pct": 0.18,
    "payback_years": 2.6
  },
  "sensitivity": [
    { "scenario": "aum_minus_20pct", "year_1_margin_pct": -0.03 },
    { "scenario": "fx_revenue_minus_50pct", "five_year_npv_usd": 12100000 }
  ],
  "approval_tier_required": "tier_4_segment_ceo_cfo",
  "rationale_narrative": "..."
}
```

**Interfaces.**
```python
class PricingEngine(Protocol):
    def propose(self, opp_id: OpportunityId, cost: CostStack, complexity: ComplexityScorecard) -> PricingProposal: ...
    def stress(self, proposal_id: PricingProposalId, scenarios: list[Scenario]) -> SensitivityReport: ...
```

**Behavior.**
- Pricing math is deterministic. The proposed bp scale comes from the rate-card library; overrides require explicit reason codes journaled at proposal time.
- Total client value is computed from finance models — NII assumes rate-curve consumed from finance, sec lending and FX revenue from product specialists' standing estimates per client profile.
- Margin: net of all S05 cost stack components plus allocated overhead.
- Approval tier: function of complexity tier × deal size × margin × strategic value. Defined in OPA policy.
- Per invariant 8: any proposal that lacks `total_client_value` is rejected at the engine level, not at review.

**Risks.**
- FX revenue is sensitive politically and legally — pricing must reflect the deal's actual FX disclosure class, not aspirational margin.
- NII assumptions are rate-curve dependent; lock the curve assumption per proposal version.
- Competitive pressure pulls bp down; the engine surfaces the "walk away" floor based on direct margin requirement, and any proposal below floor requires CFO override.

**Acceptance criteria.**
1. Total client value present on 100% of proposals; proposals without it cannot be submitted to approval.
2. Margin reproducibility: same `CostStack` + same fee structure → same margin numbers.
3. Sensitivity coverage: every tier-3/tier-4 proposal carries ≥ 5 scenarios including AUC-down, rate-curve-flat, FX-revenue-half, transition-overrun-20pct.
4. Approval routing test: 100 synthetic proposals across the tier matrix route to the policy-correct approval gate.

---

### S07 · Operating model and FTE plan

**Responsibility.** Produce the day-1 / day-90 / day-365 operating model: service model, FTE plan (by function × location × timing), app impact summary, resilience posture, control environment changes, and the explicit cross-check that S03 commitments are met.

**Inputs.** All prior stages: scope, complexity, cost, capacity, pricing, DDQ commitments.

**Outputs.**
```jsonc
// OperatingModelPlan
{
  "operating_model_id": "om_<ulid>",
  "opportunity_id": "opp_<ulid>",
  "service_model": {
    "client_service_layer": {
      "model": "dedicated | hybrid | pooled",
      "named_roles": [
        { "role": "client_service_director", "location": "ny", "named_person": "tbd | u_..." },
        { "role": "head_of_client_service", "location": "lux", "named_person": "tbd | u_..." }
      ],
      "escalation_path": [...],
      "governance_cadence": [
        { "forum": "operating_committee", "cadence": "weekly", "participants": [...] },
        { "forum": "steering_committee", "cadence": "monthly", "participants": [...] },
        { "forum": "exec_sponsor_review", "cadence": "quarterly", "participants": [...] }
      ]
    },
    "operational_delivery_layer": {
      "footprint": [
        { "function": "fund_accounting", "primary_location": "lux", "follow_the_sun": ["pune"] }
      ]
    }
  },
  "fte_plan": {
    "by_year": [
      {
        "year": 1,
        "net_new_hires": [
          { "role": "fa_specialist_l2", "location": "lux", "count": 12, "hiring_start": "2026-06-01", "hiring_lead_time_weeks": 16 }
        ],
        "redeployment": [
          { "role": "client_service_manager", "from_location": "lux", "from_pool": "asset_owner_team_a", "count": 2 }
        ],
        "total_fte": 84.0
      }
    ],
    "parallel_running": { "duration_weeks": 12, "start": "2026-10-01", "fte_overhead": 18.0 },
    "transition_milestones": [
      { "milestone": "first_nav_parallel", "target_date": "2026-11-15", "dependencies": ["hiring.fa_specialist_l2.tranche_1"] },
      { "milestone": "cutover", "target_date": "2027-01-01" }
    ]
  },
  "app_impact_summary": {
    "apps_in_scope": [
      { "app_id": "app.invest_one.prod", "scope_role": "primary_accounting", "capacity_action": "scale_out_compute", "go_live_dependency": true }
    ],
    "roadmap_dependencies": [
      { "roadmap_item": "nexen_api_v3_release", "needed_by": "2026-12-01", "status": "on_track | at_risk" }
    ],
    "integration_build": [
      { "integration": "client_oms_aladdin_fix", "build_weeks": 8, "owner": "client_connectivity_team" }
    ],
    "reporting_build": [
      { "report": "bespoke_solvency_ii_extract", "build_weeks": 6, "owner": "reporting_team" }
    ]
  },
  "resilience_posture": {
    "bcp_coverage_per_location": [...],
    "key_person_risk_register": [...],
    "single_points_of_failure_added": [],
    "rto_rpo_commitments": [
      { "service": "fund_accounting", "rto_hours": 4, "rpo_minutes": 15, "ddq_commitment_ref": "cmt_..." }
    ]
  },
  "control_environment_changes": {
    "new_controls": [...],
    "extended_controls": [...],
    "soc_scope_change_required": true,
    "soc_scope_change_cost_usd": 85000,
    "audit_readiness_milestone": "2026-12-15"
  },
  "ddq_commitment_crosscheck": [
    { "commitment_id": "cmt_...", "met_by": "resilience_posture.rto_rpo_commitments[0]", "status": "met" },
    { "commitment_id": "cmt_...", "met_by": "control_environment_changes.new_controls[2]", "status": "met" },
    { "commitment_id": "cmt_...", "met_by": null, "status": "unmet" }   // BLOCKS approval
  ]
}
```

**Interfaces.**
```python
class OperatingModelDesigner(Protocol):
    def design(self, opp_id: OpportunityId,
               scope: ScopeManifest, cost: CostStack, capacity: CapacityImpact,
               commitments: CommitmentSet) -> OperatingModelPlan: ...
    def validate_crosscheck(self, plan: OperatingModelPlan) -> CrosscheckReport: ...
```

**Behavior.**
- Service-model design is partially template-driven (per client segment + complexity tier produces a starting template) and partially LLM-drafted for the narrative sections.
- FTE plan numerically aligned to `CostStack.direct_fte`; the two MUST reconcile. A reconciliation guard in S08 enforces this — pricing margin can't be computed against a different FTE count than the operating model commits.
- Hiring lead times sourced from the role/rate catalogue; the planner walks back from the go-live date and surfaces any role where required start date precedes today plus lead time. This is the single most actionable output for the deal team because it surfaces deal-slipping risk early.
- DDQ commitment cross-check is the structural defense against post-go-live audit findings (per invariant 5). Any unmet commitment blocks approval. Acceptable resolutions: meet it, descope the commitment via DDQ amendment, or get an override journaled.

**Risks.**
- Hiring market for scarce-skill roles (experienced fund accountants in Lux, alts admin specialists, depositary controllers) is the chronic constraint. The planner surfaces shortfalls; resolution is a real HR/recruitment conversation, not a model output.
- Over-optimistic transition timelines are an industry-wide pattern in asset servicing — the planner enforces minimum parallel-running windows by complexity tier as a structural defense.

**Acceptance criteria.**
1. FTE reconciliation: `OperatingModelPlan.fte_plan.by_year[*].total_fte` matches `CostStack.direct_fte` aggregations within 0.5 FTE per year.
2. Commitment cross-check: any plan with `ddq_commitment_crosscheck[].status == "unmet"` cannot be submitted to S08 approval.
3. Hiring lead-time surfacing: for any role with `hiring_start < today + hiring_lead_time_weeks`, the plan flags a `transition_risk: high` event.
4. Roadmap dependency cross-check: every `roadmap_dependencies[].roadmap_item` resolves to a real entry in the tech roadmap registry; orphaned dependencies fail validation.

---

### S08 · Approval, contracting handoff, and the deal journal

**Responsibility.** Run the tier-gated approval workflow, seal the deal bundle, hand off to contracting / implementation / capacity planning / hiring, and operate the append-only deal journal that is this platform's audit spine (mirroring `SPEC.md` §L01).

**Approval gates (illustrative — tunable in OPA).**

| Complexity tier | Deal size (5-yr NPV) | Approvers required |
|---|---|---|
| T1 low | < $5M | RM + Segment Head |
| T2 standard | $5–25M | Segment Head + Asset Servicing CFO delegate |
| T3 high | $25–100M | AS CFO + AS COO + Risk |
| T4 exceptional | ≥ $100M, or strategic | AS CEO + AS CFO + Risk + relevant regulator notification (where applicable) |

**Schemas.**
```jsonc
// SealedDealBundle — S3 Object Lock
{
  "deal_id": "deal_<ulid>",
  "opportunity_id": "opp_<ulid>",
  "sealed_at": "...",
  "ucm_snapshot_version": "ucm_v2026.05.13",
  "upm_snapshot_version": "upm_v2026.05.13",
  "ddq_run_ids": ["run_..."],
  "scope_manifest_hash": "sha256:...",
  "complexity_scorecard_hash": "sha256:...",
  "cost_stack_hash": "sha256:...",
  "capacity_impact_hash": "sha256:...",
  "pricing_proposal_hash": "sha256:...",
  "operating_model_plan_hash": "sha256:...",
  "commitment_set_hash": "sha256:...",
  "approval_chain": [
    { "role": "segment_head", "user_id": "u_...", "ts": "...", "signature": "..." },
    { "role": "as_cfo", "user_id": "u_...", "ts": "...", "signature": "..." }
  ],
  "merkle_root": "sha256:...",
  "platform_version": "v0.1.0",
  "handoff_targets": ["contracting", "implementation_pm", "capacity_planning", "hr_recruitment"]
}

// DealJournalEvent — append-only, hash-chained, mirrors AuditEvent in SPEC.md §L01
{
  "event_id": "evt_<ulid>",
  "deal_id": "deal_<ulid>",
  "opportunity_id": "opp_<ulid>",
  "actor": { "kind": "user | system", "id": "...", "role": "..." },
  "kind": "intake | resolve | scope | ddq.link | ddq.commitment | complexity.score | cost.compute | capacity.analyze | pricing.propose | operating_model.design | approval.request | approval.decision | override | seal | handoff | actuals.update",
  "ts": "RFC3339",
  "payload": { /* kind-specific */ },
  "payload_hash": "sha256:...",
  "prev_hash": "sha256:...",
  "signature": "..."
}
```

**Interfaces.**
```python
class ApprovalService(Protocol):
    def request(self, deal_id: DealId, gate: ApprovalGate) -> ApprovalRequestId: ...
    def decide(self, request_id: ApprovalRequestId, decision: ApprovalDecision) -> None: ...

class DealJournal(Protocol):
    def append(self, event: DealJournalEvent) -> EventReceipt: ...
    def seal(self, opp_id: OpportunityId) -> SealedDealBundle: ...
    def replay(self, deal_id: DealId) -> ReplayBundle: ...

class Handoff(Protocol):
    def to_contracting(self, bundle: SealedDealBundle) -> None: ...
    def to_implementation(self, bundle: SealedDealBundle) -> None: ...
    def to_capacity_planning(self, bundle: SealedDealBundle) -> None: ...
    def to_hr_recruitment(self, bundle: SealedDealBundle) -> None: ...
    def to_ecrm(self, bundle: SealedDealBundle) -> None: ...     # opp → won/in_implementation
```

**Behavior.**
- Approval gate evaluated by OPA against the deal package; required approver set is deterministic from `(complexity_tier, deal_size, strategic_flag)`.
- Approvers act in the deal review UI (S08 surface); decisions emit journal events.
- On full approval, seal: bundle written to S3 with Object Lock, hashes recorded, handoffs fire.
- Handoff to contracting includes commitment set → contract schedule mapping (per S03).
- Handoff to capacity planning includes the `CapacityImpact.expansion_required` list with funding tagged to the deal.
- Handoff to HR includes the FTE plan with role-level requisitions.
- Handoff to eCRM moves the opportunity to "won / in implementation"; revenue forecast updated.
- Post-seal, the **actuals tracking** loop begins: monthly/quarterly actuals come in from finance, ops, HR, and tech; comparison to baseline drives recalibration of cost/capacity/complexity rubrics (see §9).

**Risks.**
- Approval bottleneck: tier-4 deals can stall in committee; the journal makes the bottleneck visible and dashboarded.
- Late-stage scope change after approval requires explicit re-sealing — partial amendments are not supported by the bundle model.
- Lost-deal disposition: opportunities that don't win still seal a "lost bundle" with reason codes for win/loss analytics; this is the strongest source of long-term pricing intelligence.

**Acceptance criteria.**
1. Replay test: any sealed deal bundle regenerates bit-exact from journal + pinned snapshots.
2. Approval gate enforcement: zero deals seal without the policy-required approver set; tested via fuzzing.
3. Handoff completeness: every sealed bundle produces handoffs to all four downstream systems within 5 minutes of seal; failures alert.
4. Actuals loop closed: at 6 months post-seal, every deal has at least one `actuals.update` journal event; missing actuals trigger an SLO breach.

---

## 5. The data spine — three domains, three engines

Same shape as `SPEC.md` §5, with stage-specific content.

| Domain | Mutability | Mongo | S3 | DuckDB |
|---|---|---|---|---|
| **Canonical entities** (UCM, UPM, app registry, role/rate catalogue) | Mutable, version-tracked | Local snapshots / indexes | Pinned snapshots | Coverage and drift analytics |
| **Deal state** (opportunities, scope, cost, capacity, pricing, op-model in flight) | Mutable until sealed | Live state | Sealed bundles | Win/loss, pipeline analytics |
| **Deal journal** (intake → seal → actuals) | Immutable | Hot 60d | Object Lock (system of record) | Full-history analytics, baseline-vs-actuals |

UCM/UPM/app-registry snapshots are pinned per opportunity at the moment they're first read; the pin is in the journal; replay requires the pin be retrievable from S3.

---

## 6. Request flow (stage = audit cluster)

```
S01 INTAKE       Inbound → opportunity → UCM resolution → eCRM hub created      [journal: intake, resolve]
S02 SCOPE        Products → UPM resolution → app-stack expansion                [journal: scope]
S03 DDQ          DDQ run linked → commitments extracted                         [journal: ddq.link, ddq.commitment]
S04 COMPLEXITY   Dimensions scored → tier assigned                              [journal: complexity.score]
S05 COST + CAP   Cost stack + capacity impact (parallel)                        [journal: cost.compute, capacity.analyze]
S06 PRICING      Fee structure + total client value + margin                    [journal: pricing.propose]
S07 OP MODEL     Service model + FTE + app impact + commitment crosscheck       [journal: operating_model.design]
S08 APPROVAL     Tier-gated approval → seal → handoff → actuals loop opens      [journal: approval.*, seal, handoff, actuals.update]
```

Each stage emits ≥ 1 journal event. Any stage can route back to an earlier stage with a typed reason (`scope_change`, `volume_revision`, `commitment_addition`).

---

## 7. Operating levers (non-negotiable practices)

1. **Canonical data as foundation (40% of total effort).** UCM resolution, UPM completeness, app registry accuracy. Without these, every downstream stage is guesswork.
2. **Numeric engines are deterministic.** Cost, capacity, pricing math has no LLM in the path. LLMs draft commentary; numbers are auditable arithmetic.
3. **Total client value, never headline bp.** Per invariant 8; enforced by engine, not by review.
4. **DDQ-to-contract traceability.** Every material DDQ commitment shows up as a schedule item; nothing falls through.
5. **Actuals feedback closes the loop.** Quarterly recalibration of scaling formulas, complexity weights, and capacity load factors against sealed-bundle baselines vs. actuals.
6. **Evals on history.** Backtest the cost/capacity/pricing engines against historical sealed deals before any rubric or rate-card change ships. CI gate.

---

## 8. The five guardrails (recap, normative)

```
guardrail.01_ucm_resolution_complete       → no opportunity without resolved UCM + pinned snapshot, or HALT
guardrail.02_upm_scope_clean               → no progression past S02 with blocking scope issues, or HALT
guardrail.03_commitment_crosscheck         → no operating model with unmet DDQ commitments, or HALT
guardrail.04_capacity_blocking_clear       → no pricing with high-severity capacity constraints unresolved, or HALT
guardrail.05_approval_tier_enforced        → no seal without policy-required approver chain, or HALT
```

Encoded as Rego policies in `infra/opa-policies/`. Override path: named CFO/segment-CEO approval, journaled, time-boxed.

---

## 9. Cross-cutting concerns

### 9.1 Hardest data dependency — the app and capacity registry

The single biggest risk in this platform is the app registry. UPM-to-app mapping plus current capacity envelopes plus load factors — none of this typically exists as a queryable model in asset servicing organizations; it lives as tribal knowledge in tech and ops. Without it, capacity analysis is confident nonsense, and the FTE plan and pricing built on top of it are no better.

Plan accordingly:
- Treat the registry as its own product with named ownership in tech infrastructure.
- Bootstrap from the existing platform consolidation work (post-merger BNY+Mellon platform unification, Eagle integration history).
- Run a 6–12 month data-build effort in parallel with stages S04–S07 so the deterministic engines come online with real data, not placeholders.
- Establish a quarterly review cadence with tech leads to refresh envelopes as actual utilization shifts.

### 9.2 Security & tenancy

- mTLS service-to-service; secrets in AWS Secrets Manager.
- Per-BNY-legal-entity access scoping for UCM data (e.g., a deal team in EMEA may not see US plan-sponsor identifying data unless KYC says so).
- Sub-custodian rate card data is confidential and license-restricted; access via OPA policy with audit.

### 9.3 Backtesting and evals

- Backtest harness in `evals/` replays historical sealed deals against current engines and rubrics. Required for any change to cost scaling, capacity load factors, complexity weights, or pricing rate cards.
- Calibration metrics tracked in dashboards: predicted-vs-actual FTE, predicted-vs-actual capacity utilization, predicted-vs-actual margin, complexity-tier-vs-effort correlation.
- New deals replay through the engines as soon as 12-month actuals are available; the delta feeds rubric recalibration.

### 9.4 Observability

- OpenTelemetry traces with `opportunity_id` and `deal_id` propagated end-to-end.
- Langfuse for the LLM-drafted narrative paths (complexity narrative, cost commentary, operating-model write-ups).
- Mandatory dashboards: pipeline by stage, time-in-stage by complexity tier, approval throughput, deal NPV vs. baseline, capacity headroom by app, FTE plan vs. hiring actuals, win/loss by client segment and complexity tier.

### 9.5 Testing

- Unit: pure logic in `core/`.
- Integration: testcontainers; recorded fixtures for internal BNY services (eCRM/UCM/UPM/app-registry) that are not testcontainer-friendly.
- E2E: 10 representative deals end-to-end (mix of asset manager / asset owner / alts manager; mix of complexity tiers); asserted against gold sealed bundles.
- Engine determinism tests: every numeric engine has a fixture set proving identical inputs → identical outputs.

### 9.6 Versioning & deployment

- Semver per service.
- Blue/green via Helm.
- Scaling formulas, complexity rubrics, pricing rate cards, capacity load factors are version-controlled artifacts deployed independently from code, gated by backtest pass.
- UCM/UPM snapshot cadence: daily snapshots pinned to S3; opportunities pin at first read.

---

## 10. Build sequencing — milestones for Claude Code

### M1 · Foundations (week 1–3)
- Repo skeleton, CI, IaC stubs.
- `core/domain` and `core/ports` definitions.
- Deal journal MVP (S08): event schema, hash chain, Mongo hot store, S3 seal job, replay shell.
- LLM SDK with Bedrock + Anthropic adapters (reused from DDQ platform if possible).
- Adapter stubs for eCRM (Salesforce FSC), UCM, UPM, app registry, role catalogue, sub-custody feed.
- Eval harness skeleton.

### M2 · Canonical data and intake (week 4–6)
- UCM resolver service (S01) with confidence-scored matching.
- UPM scoper (S02) with dependency closure and legal-entity assignment policies.
- App registry — start with a curated v0 covering 8–12 anchor apps for the most common product set.
- eCRM bidirectional adapter.

### M3 · Numeric engines (week 7–10)
- Complexity scorer (S04) with v1 rubrics and uniform weights.
- Cost engine (S05a) with scaling formulas for the anchor product set.
- Capacity engine (S05b) against the v0 app registry.
- Pricing engine (S06) with rate-card library and total-client-value model.

### M4 · DDQ integration and operating model (week 11–13)
- DDQ bridge (S03) — start_run, commitment extraction, watch.
- Operating model designer (S07) with service-model templates per segment and FTE planner.
- Commitment cross-check enforcement.

### M5 · Approval, surface, and ops (week 14–16)
- Approval service (S08) with OPA-driven tier gates.
- Deal workspace UI (S08 surface), approval consoles, deal-journal explorer.
- Handoff adapters to contracting / implementation / capacity / HR.
- Dashboards, runbooks, on-call.

### M6 · Hardening and backtest (week 17–18)
- Backtest harness in CI as a hard gate.
- 10 historical deals replayed; calibration baseline set.
- Load test: 50 concurrent in-flight deals.
- Chaos: eCRM down (deals queue), UCM stale (warn), app registry version skew (block scope progression).

---

## 11. Open decisions (track in `docs/decisions/`)

1. **eCRM source of truth boundary.** Which fields are authoritative in eCRM vs. here; conflict resolution rules. Draft RACI in `docs/decisions/0001-ecrm-ownership.md`.
2. **App registry ownership.** Tech infrastructure vs. Asset Servicing engineering vs. shared. Single owner with named accountability is non-negotiable.
3. **Sub-custodian rate card refresh cadence.** Currently quarterly via network management; tighter would help fast-moving deals.
4. **Pricing rate card governance.** Who owns the rate card, who approves changes, what backtest coverage gates a rate-card update.
5. **Lost-deal data sharing.** Win/loss intelligence is highest-leverage when shared across segments; data governance and competitive sensitivity need a policy decision.

---

## 12. Glossary

- **UCM** — Universal Client Master; canonical client/entity hierarchy.
- **UPM** — Universal Product Master; canonical product taxonomy with delivery app stacks.
- **eCRM** — enterprise CRM (Salesforce Financial Services Cloud assumed); the commercial system of record for opportunities and pipeline.
- **Scope manifest** — the structured, UPM-resolved scope of a deal; sole input shared across cost/capacity/pricing/op-model engines.
- **Complexity tier** — T1 (low) → T4 (exceptional); drives approval routing, model variance, and review depth.
- **Cost stack** — fully-loaded operational cost over the deal horizon, by FTE function/location, technology run + expansion, sub-custody passthrough, transition one-time, risk/compliance, and allocated overhead.
- **Capacity impact** — per-app projected utilization post-deal; fits-in-headroom / expansion-required / declining-risk verdict.
- **Total client value** — direct fees + sec lending share + FX revenue + NII on balances + adjacent revenue across BNY segments.
- **Commitment** — a material claim in a sealed DDQ response (SLA, control, jurisdiction, residency) that becomes a contract schedule item.
- **Sealed deal bundle** — the immutable record of an approved deal; baseline for actuals tracking.
- **Deal journal** — append-only, hash-chained event log per opportunity → deal; this platform's audit spine.

---

## 13. Reading order for an engineer joining the project

1. Section 1 (invariants) — the contract.
2. Section 9.1 (app registry risk) — the hardest data dependency, read before believing any numeric output.
3. Section 4 (eight stages) — what to build.
4. Section 10 (build sequencing) — what to do this week.
5. `SPEC.md` §L01 (audit journal) — the DDQ-platform pattern this platform's deal journal mirrors.
6. The relevant ADR(s) in `docs/decisions/` for any open decision touching your work.

---

*End of spec. Update via PR; tag `@architecture-board` for changes to invariants, schemas, or guardrails. Cross-reference with `SPEC.md` (DDQ Platform) for shared infrastructure decisions.*

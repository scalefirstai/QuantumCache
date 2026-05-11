# BNY Agentic DDQ Response Platform — Technical Specification

**Doc:** SA-2026-0142 · **Status:** DRAFT v0.4 · **Classification:** Internal
**Audience:** Engineers building this in Claude Code. Assume competence; skip the marketing.

---

## 0. Reading guide

This spec is the build contract for the eight-layer agentic platform that responds to industry-standard due diligence questionnaires (AFME, SIG Lite, SIG Core, CAIQ, ADV, bespoke) at institutional scale. The durable asset is the **answer library**, not the agent.

**Build order (recommended):** L01 → L02 → L05 (taxonomy) → L04 (library) → L03 (retrieval) → L06 (agents) → L07 (orchestration) → L08 (UI). Validation/observability are cross-cutting and built alongside.

**Conventions in this doc:**
- `MUST` / `SHOULD` / `MAY` follow RFC 2119.
- Code/identifiers in `monospace`. Schemas in JSON-ish for clarity, not ceremony.
- Every section ends with **Acceptance criteria** — what "done" means for that piece.

---

## 1. System invariants (read this first, refer back often)

These hold for every layer, every code path, every PR. Violation = halt.

1. **Citation resolution is total.** Every factual claim in any outbound response resolves to a source span with a content hash. No claim → no source → no send.
2. **Sealed runs are immutable.** Once a run is sealed (S3 Object Lock), it is bit-exact reproducible. The journal IS the system of record.
3. **Separate retrieve from draft.** One agent finds/validates evidence. A different agent drafts narrative. Same agent never does both.
4. **Extractive over generative for facts.** Numbers, dates, framework versions, control IDs — extracted verbatim with anchors. Never paraphrase a fact a regulator might verify.
5. **Confidence-tier everything.** Every answer carries a confidence score. High → auto-pass. Low → SME queue by domain.
6. **Versioned canonical IDs.** Every outbound answer references `(canonical_id, taxonomy_version, library_entry_hash)`. Reproducibility is the regulatory contract.
7. **No override path bypasses guardrails.** Overrides themselves are journaled events with named approval.

---

## 2. Stack of record

| Concern | Choice | Notes |
|---|---|---|
| Live transactional state | **MongoDB Atlas** (M40+, multi-region) | Open decision: Atlas vs self-managed on EKS — spec assumes Atlas, code abstracts via repository pattern |
| Durable / immutable artifacts | **S3** with Object Lock (Compliance mode) | WORM; no delete, no overwrite, no exception |
| Analytical reads | **DuckDB** over S3 Parquet (with Iceberg layer) | Open decision: Iceberg vs raw Parquet — start raw, plan Iceberg migration in Q2 |
| Workflow orchestration | **LangGraph** (in-process graph) + **Temporal** (durable execution) | LangGraph defines node topology; Temporal handles durability, retries, timers, human-in-loop waits |
| Lexical retrieval | **OpenSearch** (BM25, custom analyzers) | |
| Dense retrieval | **Qdrant** (HNSW, payload-filtered) | |
| Reranker | **Cohere Rerank v3** | |
| Knowledge graph | **Neo4j** (taxonomy relations, evidence linkage) | |
| Document parsing | **Unstructured.io** | |
| LLM access | **AWS Bedrock** (preferred) with **Anthropic API** fallback | Open decision; abstract behind `LLMClient` interface |
| LLM models | Claude **Opus 4.7** (synthesis), **Sonnet 4.6** (drafting), **Haiku 4.5** (classification) | Tier-routed per agent budget |
| State cache | **Redis** | Run-state cache, idempotency keys |
| Policy engine | **OPA** (Open Policy Agent) | All guardrail rules as Rego policies |
| PII | **Microsoft Presidio** | Detection + redaction |
| Tracing | **Langfuse** + **OpenTelemetry** | |
| Audit / SIEM | **AWS CloudTrail** + **Splunk** | |
| API gateway / surface | **FastAPI** (Python services), **React + TypeScript** (UI) | |
| Auth | **OIDC via Okta**, mTLS service-to-service | |
| IaC | **Terraform** + **Helm** | EKS-hosted services |
| Languages | **Python 3.12** (services, agents), **TypeScript** (UI), **Rego** (policies) | |

**Repository pattern is mandatory.** Every external system is accessed through an interface in `core/ports/`. Adapters live in `infra/adapters/`. Tests use in-memory adapters; integration tests use real services via testcontainers.

---

## 3. Repository layout

```
ddq-platform/
├── apps/
│   ├── api-gateway/              # FastAPI, public-facing API
│   ├── ui/                       # React + TS, SME + client portal
│   ├── orchestrator/             # LangGraph + Temporal worker
│   └── ingest-worker/            # Document ingestion pipeline
├── services/
│   ├── intake/                   # L08 ingest (email, portal, file)
│   ├── classifier/               # L05 framework + canonical mapping
│   ├── retrieval/                # L03 hybrid retrieval service
│   ├── library/                  # L04 answer library service
│   ├── drafter/                  # L06 drafting agent
│   ├── validator/                # L02 guardrails service
│   ├── approval/                 # L08 SME queue service
│   └── audit/                    # L01 journal service
├── core/                         # Domain logic, no I/O
│   ├── domain/                   # Entities, value objects
│   ├── ports/                    # Interfaces (Repository, LLMClient, etc.)
│   └── policies/                 # Pure validation logic
├── infra/
│   ├── adapters/                 # Mongo, S3, OpenSearch, Qdrant, Bedrock, etc.
│   ├── terraform/
│   ├── helm/
│   └── opa-policies/             # Rego files
├── packages/                     # Shared libraries
│   ├── schemas/                  # Pydantic + JSON Schema (generated for TS)
│   ├── audit-sdk/                # Journaling client
│   └── llm-sdk/                  # LLMClient, prompt registry
├── evals/                        # Regression suite (the 500-question set)
│   ├── fixtures/
│   ├── runners/
│   └── reports/
├── docs/
│   ├── runbooks/
│   └── decisions/                # ADRs
└── tests/
    ├── unit/
    ├── integration/              # testcontainers
    └── e2e/
```

**Service-to-service:** internal HTTP via gRPC-style contracts (we use HTTP+Protobuf or HTTP+Pydantic). Async work flows through Temporal, not direct calls.

---

## 4. The eight layers

Each layer subsection contains: **Responsibility** · **Interfaces** · **Schemas** · **Behavior** · **Risks/edge cases** · **Acceptance criteria**.

### L01 · Audit, Observability & Platform (BASE)

**Responsibility.** Append-only signed journal of every prompt, retrieval, model call, tool invocation, edit, and approver action. Trace every run. Reproducibility contract: any past sealed response regenerates bit-exact from the journal.

**Interfaces.**
```python
class AuditJournal(Protocol):
    def append(self, event: AuditEvent) -> EventReceipt: ...
    def seal_run(self, run_id: RunId) -> SealedRun: ...
    def replay(self, run_id: RunId) -> ReplayBundle: ...
    def get_event(self, event_id: EventId) -> AuditEvent: ...
```

**Schemas.**
```jsonc
// AuditEvent — every event is one of these
{
  "event_id": "evt_<ulid>",
  "run_id": "run_<ulid>",
  "parent_event_id": "evt_<ulid> | null",
  "actor": { "kind": "agent | sme | system | client", "id": "...", "version": "..." },
  "kind": "intake | classify.match | retrieve.query | retrieve.result |
           llm.prompt | llm.response | tool.call | validate.check |
           approval.request | approval.decision | seal | error",
  "ts": "RFC3339 with µs",
  "payload": { /* kind-specific */ },
  "payload_hash": "sha256:...",
  "prev_hash": "sha256:...",        // hash chain
  "signature": "ed25519:..."        // signed by service identity
}

// SealedRun — written to S3 with Object Lock
{
  "run_id": "run_<ulid>",
  "sealed_at": "RFC3339",
  "events": [ /* full ordered chain */ ],
  "merkle_root": "sha256:...",
  "outbound_response_hash": "sha256:...",
  "library_entry_hashes": ["sha256:...", ...],
  "source_document_hashes": ["sha256:...", ...],
  "model_call_manifest": [ { "model": "...", "prompt_hash": "...", "response_hash": "...", "params": {...} } ],
  "taxonomy_version": "tx_v2026.04.01",
  "platform_version": "v0.4.2"
}
```

**Behavior.**
- Hot window 30 days in MongoDB (`audit.events` collection). Background job seals runs older than 24h to S3 Object Lock buckets, writes Parquet shadow for DuckDB queries.
- Event chain MUST be hash-linked; tampering is detectable on replay.
- `replay(run_id)` MUST produce a deterministic bundle: same prompts, same retrieval results (cached), same model temperature parameters → same response, byte-for-byte. If any input is missing/changed, replay fails loudly.
- All services emit OpenTelemetry spans tagged with `run_id`, `event_id`, `actor.id`. Langfuse receives LLM-specific traces.

**Risks.**
- Clock skew across services → use Temporal's logical clock for event ordering; wall clock is observational only.
- High write volume on long DDQs (200+ questions × ~10 events each) → batched writes acceptable, but seal latency MUST stay under 60s after run completion.
- S3 Object Lock requires bucket-level config; once enabled, cannot be disabled. Confirm with Risk before applying to any prod bucket.

**Acceptance criteria.**
1. Replay test: pick any sealed run from the eval corpus, regenerate; output hash matches stored `outbound_response_hash`.
2. Tamper test: modify any event in the chain, replay fails with chain-break error pointing to the modified event.
3. SIEM sink: every event of kind `error`, `approval.decision`, `seal`, or `validate.check` (when failed) reaches Splunk within 30s.

---

### L02 · Validation & Guardrails

**Responsibility.** Block any response that fails the four non-negotiable checks. No override bypasses; overrides are themselves journaled events requiring named legal/security approval.

**The four guardrails.**
1. **Citation Resolution.** Every factual claim resolves to a source span with content hash. Fails if any claim is unanchored or anchor's hash doesn't match current corpus.
2. **Evidence Freshness.** SOC reports, audit reports, policy versions, certs all current per the freshness index. SOC 1/2 < 12 months, ISO 27001 within validity window, policies at current published version.
3. **Cross-DDQ Consistency.** Same canonical_id answered differently in another in-flight or recently-shipped DDQ → halt + escalate. Tolerance for prose variation; intolerance for factual divergence.
4. **Confidentiality Scrub.** PII (Presidio), internal-only refs (regex + classifier), client-specific commercials (lookup against deal data) — detected and stripped or escalated.

**Interfaces.**
```python
class Validator(Protocol):
    def validate(self, draft: DraftResponse, ctx: RunContext) -> ValidationReport: ...

class ValidationReport(BaseModel):
    run_id: RunId
    checks: list[CheckResult]   # one per guardrail
    verdict: Literal["pass", "halt", "escalate"]
    halt_reason: str | None
    escalate_to: list[SmeDomain]
```

**Behavior.**
- Validator runs as a Temporal activity. All four checks run in parallel. Single fail → halt.
- Citation check uses content-addressed lookup: each claim carries `(span_hash, doc_hash)`; both MUST exist in current corpus.
- Cross-DDQ check queries DuckDB over the response register: same `canonical_id` shipped within last 90 days where text divergence > threshold (semantic similarity < 0.92) → halt.
- Confidentiality scrub returns either a sanitized draft + warnings (for low-severity PII like a public exec name in a quote) or a halt (for SSNs, account numbers, internal codenames).
- All guardrail rules expressed as **Rego policies** in `infra/opa-policies/`. Validator service evaluates against OPA.

**Risks.**
- False positives on consistency check during legitimate updates (e.g., a SOC report version bumped) → version-aware comparison; only same-version answers compared.
- Presidio over-redacts proper nouns → custom recognizers for BNY entity names.
- Performance: 4 parallel checks on a 200-question DDQ — budget P95 < 2s per question.

**Acceptance criteria.**
1. Test suite covers each guardrail with at least 5 fail cases and 5 pass cases.
2. No code path can mark a response as send-ready without a `ValidationReport.verdict == "pass"`.
3. Override audit: every override is an `approval.decision` event linked to the halted check; the legal-review register grows by exactly one entry per override.

---

### L03 · Retrieval & Knowledge

**Responsibility.** Given a canonical question and run context, return a ranked set of evidence spans from policies, SOC reports, audits, regulatory filings, BCP tests, and prior approved responses. Every span resolves to a page or section anchor.

**Corpus.** S3 raw + Parquet shadow. Documents parsed by Unstructured.io into `(doc_id, section_id, span_id, text, anchor, hash)` tuples. Tuples indexed in OpenSearch (BM25), embedded into Qdrant (dense), and node/edge-modeled in Neo4j.

**Interfaces.**
```python
class RetrievalService(Protocol):
    def retrieve(self, query: RetrievalQuery) -> list[EvidenceSpan]: ...

class RetrievalQuery(BaseModel):
    canonical_id: CanonicalId
    free_text: str                       # the actual question, used for dense
    framework: Framework
    entity: BnyEntity                    # which BNY legal entity is in scope
    product: Product | None
    k: int = 20
    filters: dict[str, Any] = {}         # e.g., {"doc_type": "soc_report", "freshness_max_days": 365}

class EvidenceSpan(BaseModel):
    doc_id: str
    doc_hash: str
    section_id: str
    span_id: str
    span_hash: str
    text: str
    anchor: PageAnchor | SectionAnchor   # for citation
    score: float                         # post-rerank
    provenance: Provenance               # who authored, when, version
```

**Behavior.**
- Hybrid pipeline: BM25 top-100 ∪ dense top-100 → Cohere Rerank → top-k.
- Filters MUST honor entity and product scoping (e.g., never return Pershing-only evidence for a BNY Mellon Custody question).
- Knowledge-graph traversal: when a question maps to a control, expand retrieval to evidence linked to that control via Neo4j (`Control -[:EVIDENCED_BY]-> Document`).
- All retrievals MUST be journaled (kind `retrieve.query`, `retrieve.result`) — including the full ranked list, not just what was used.
- Caching: per `(query_hash, corpus_version)` in Redis with TTL 24h. Cache key includes `corpus_version` so corpus updates invalidate.

**Risks.**
- Stale corpus → corpus version bumped on any document add/replace; retrieval clients MUST refuse to serve stale corpus past 5 min after version bump.
- Multi-tenant entity bleed → entity filter is enforced server-side via OPA policy, not client-supplied.
- P95 < 1.2s recall is the SLA.

**Acceptance criteria.**
1. Recall@10 ≥ 0.85 on the eval set's labeled gold spans.
2. Entity-isolation test: 100 cross-entity probes, zero leakage.
3. Trace: every retrieval emits a span carrying `retrieval.candidates`, `retrieval.reranked`, `retrieval.returned`.

---

### L04 · Answer Library

**Responsibility.** SME-curated, version-controlled corpus of approved responses keyed on `(canonical_id, entity, product)`. Every entry: content hash, evidence references, approver chain, effective date, expiry. The agent is replaceable; this corpus compounds in value.

**Schemas.**
```jsonc
// LibraryEntry — Mongo "library.entries"
{
  "entry_id": "lib_<ulid>",
  "canonical_id": "canon.is.access_control.privileged_access_review",
  "entity": "BNY_FUND_SERVICES",
  "product": null,                           // or specific product
  "answer_text": "...",                      // approved prose
  "evidence_refs": [
    { "doc_hash": "...", "span_hash": "...", "anchor": {...} }
  ],
  "approvers": [
    { "user_id": "u_...", "role": "sme.infosec", "ts": "...", "comment": "..." },
    { "user_id": "u_...", "role": "legal.review", "ts": "...", "comment": "..." }
  ],
  "effective_date": "2026-01-15",
  "expiry_date": "2027-01-15",               // hard expiry, drives freshness
  "review_due": "2026-07-15",                // soft, drives review queue
  "version": 4,
  "supersedes": "lib_<ulid> | null",
  "content_hash": "sha256:...",              // hash of the canonical entry content
  "tags": ["soc2", "control-access-3"],
  "do_not_answer": false                     // true → routes to legal, never auto-served
}
```

**Storage split.**
- Live entries → MongoDB `library.entries`. Active reads.
- Each version sealed → S3 `s3://bny-ddq-library-sealed/<entry_id>/<content_hash>.json` (Object Lock).
- Parquet shadow → DuckDB analytics (reuse rates, expiry forecast).

**Interfaces.**
```python
class LibraryService(Protocol):
    def lookup(self, key: LibraryKey) -> LibraryEntry | None: ...
    def propose(self, draft: DraftLibraryEntry, run_id: RunId) -> ProposalId: ...
    def approve(self, proposal_id: ProposalId, approver: Approver) -> LibraryEntry: ...
    def expire(self, entry_id: EntryId, reason: str) -> None: ...
    def search(self, q: LibrarySearch) -> list[LibraryEntry]: ...
```

**Behavior.**
- `lookup` returns the highest-versioned non-expired entry for `(canonical_id, entity, product)`, falling back through (entity, null product), (parent canonical), in that order.
- Approver chain is policy-driven (OPA): tier-1 questions need `sme.domain` + `legal.review`; tier-2 only `sme.domain`; tier-3 only `senior.sme`.
- Every approval is a `approval.decision` audit event with the entry's `content_hash`.
- Expiry job (daily): mark entries expired, fire freshness alerts, surface to review queue.

**Risks.**
- Multiple in-flight proposals for the same key → optimistic locking with `version + 1` constraint; conflicts surface to SME merge UI.
- Drift between library and source evidence → on every retrieval, library entry's `evidence_refs` are re-validated against current corpus; mismatch → entry quarantined.

**Acceptance criteria.**
1. 100% reproducibility: any historical sealed response can be regenerated with the exact library entry version it cited.
2. Expiry coverage: zero shipped responses cite expired entries.
3. Approver chain enforcement test: zero entries reach `approved` state without the policy-required approver set.

---

### L05 · Canonical Question Taxonomy

**Responsibility.** The hinge of the platform. Hierarchical taxonomy of canonical question IDs. Every framework's question maps to one canonical ID. New questions classified by embedding similarity, confirmed by SME.

**Hierarchy.** Six top-level domains:
```
canon.is             — Information Security
canon.or             — Operational Resilience
canon.reg            — Regulatory Posture
canon.esg            — ESG
canon.subc           — Sub-Custody
canon.cyber          — Cyber
```
Each domain has subdomains (e.g. `canon.is.access_control`), each subdomain leaf canonical questions (e.g. `canon.is.access_control.privileged_access_review`).

**Schemas.**
```jsonc
// CanonicalQuestion — Mongo "taxonomy.questions"
{
  "canonical_id": "canon.is.access_control.privileged_access_review",
  "label": "Privileged Access Review Cadence",
  "description": "Frequency, scope, and approval chain for privileged access reviews.",
  "parent_id": "canon.is.access_control",
  "synonyms_embedding": "vec_id_qdrant",
  "framework_mappings": [
    { "framework": "AFME", "version": "2025", "question_ref": "AFME-IS-3.4" },
    { "framework": "SIG_CORE", "version": "2026", "question_ref": "SC-AC-7" },
    { "framework": "CAIQ", "version": "v4", "question_ref": "IAM-04" }
  ],
  "tier": 1,                                 // 1=high-risk, 2=standard, 3=low
  "do_not_answer": false,
  "owners": ["sme.infosec"],
  "created_at": "...", "updated_at": "..."
}

// TaxonomyVersion — sealed snapshots in S3
{
  "version": "tx_v2026.04.01",
  "ts": "...",
  "merkle_root": "sha256:...",
  "question_count": 1842,
  "framework_coverage": { "AFME": 612, "SIG_LITE": 130, "SIG_CORE": 850, "CAIQ": 287, "ADV": 95 },
  "signed_by": "compliance.architecture.lead"
}
```

**Storage split.**
- Live taxonomy → MongoDB `taxonomy.questions`.
- Versioned snapshots → S3 (signed, Object Lock).
- Relationships → Neo4j (`(:Canonical)-[:CHILD_OF]->(:Canonical)`, `(:Canonical)-[:MAPS_TO]->(:FrameworkQuestion)`).
- Embeddings of synonyms/descriptions → Qdrant (used for new-question classification).
- DuckDB analytics → mapping coverage by framework/version.

**Interfaces.**
```python
class TaxonomyService(Protocol):
    def get(self, canonical_id: CanonicalId, version: TaxonomyVersion | None = None) -> CanonicalQuestion: ...
    def map_framework_question(self, framework: Framework, ref: str, version: str) -> CanonicalId | None: ...
    def classify_new_question(self, text: str, framework: Framework) -> ClassificationResult: ...
    def propose_mapping(self, fq: FrameworkQuestion, candidate: CanonicalId, run_id: RunId) -> ProposalId: ...
    def cut_version(self, signer: Signer) -> TaxonomyVersion: ...
```

**Behavior.**
- `classify_new_question`: embed text, top-k from Qdrant, cross-encode rerank, return top candidate + score. Below threshold → `unclassified`, routes to SME.
- Versioning: every change accumulates in a draft. `cut_version` creates a signed snapshot, sealed to S3, broadcast to all consumers via event bus. Live runs continue on their pinned version until completion.
- SKOS / OWL serialization is an export concern, not the runtime format.

**Risks.**
- Mis-mapping cascades into wrong library lookups → all auto-classifications below confidence threshold MUST go to SME confirmation before being used in a sealed run.
- Taxonomy drift across consumers → every service calling Taxonomy MUST pin a version per run; the pin is recorded in the audit journal.

**Acceptance criteria.**
1. Mapping precision ≥ 0.95 on eval-labeled mapping pairs.
2. Version pin: every sealed run has exactly one `taxonomy_version` recorded; replay fails if that version's snapshot is missing.
3. Coverage report: 100% of questions in the eval set's incoming DDQs map to a canonical_id (with SME confirmation as needed).

---

### L06 · Agent Roster

**Responsibility.** Specialized agents, single responsibilities. No agent both retrieves and drafts. Each agent has: scoped tools, model tier, prompt registry entry, eval coverage.

**Roster.**
| Agent | Model tier | Tools | Responsibility |
|---|---|---|---|
| `QuestionMapper` | Haiku | Taxonomy.classify | Maps incoming framework Q → canonical_id; emits confidence |
| `EvidenceSourcer` | Sonnet | Retrieval.retrieve, Library.lookup | Produces evidence bundle; never drafts prose |
| `DraftComposer` | Sonnet (default), Opus (tier-1, complex) | (read-only context) | Drafts response from evidence bundle; cites every claim |
| `CitationVerifier` | Haiku | Corpus.fetch_span | Verifies every cited span resolves and matches |
| `ConsistencyChecker` | Sonnet | DuckDB.query_response_register | Compares against recent shipped responses for same canonical_id |
| `PiiScrubber` | Haiku + Presidio | Presidio.analyze | Detects/redacts PII, internal-only refs |
| `FreshnessAuditor` | (rule-based, not LLM) | Library.expiry, Corpus.freshness | Flags stale evidence/library entries |
| `ApprovalRouter` | (rule-based) | OPA.evaluate | Routes to right SME queue by domain + tier |

**Interfaces.**
Every agent implements:
```python
class Agent(Protocol):
    name: str
    version: str
    def run(self, input: AgentInput, ctx: RunContext) -> AgentOutput: ...
```

`AgentInput` and `AgentOutput` are Pydantic models per agent, registered in `packages/schemas/agents/`. Inputs and outputs MUST be JSON-serializable for journaling.

**Prompt registry.** All prompts in `services/<agent>/prompts/<version>.md` with header:
```yaml
---
agent: DraftComposer
version: 1.4.0
model: claude-sonnet-4-6
temperature: 0
max_tokens: 2048
eval_set: drafter_v1
---
```
Prompts are versioned. Promotion to prod requires regression pass.

**LLM access.**
```python
class LLMClient(Protocol):
    def complete(self, req: LLMRequest) -> LLMResponse: ...
    def stream(self, req: LLMRequest) -> Iterator[LLMChunk]: ...
```
Bedrock and Anthropic API are interchangeable adapters. Prompt + response always journaled with both prompt hash and response hash.

**Tiered model routing rules (within DraftComposer).**
- Tier-1 canonical (high-risk: regulatory, security control, financial reporting) → Opus 4.7.
- Tier-2 (standard: operational, ESG narrative) → Sonnet 4.6.
- Tier-3 (boilerplate, factual lookup) → Haiku 4.5 with extractive-only mode.
- Override: explicit per-question routing override journaled as a config event.

**Risks.**
- Agent sprawl → no new agent without an ADR and an eval slice. Reuse beats new.
- Prompt drift across environments → registry hash compared at startup; mismatch fails the deploy.
- Cost: tier-1 Opus calls expensive → measure per-DDQ cost; if exceeding budget, consistency-check downgrade decisions.

**Acceptance criteria.**
1. Each agent has ≥ 50 eval cases with gold outputs; CI fails if regression drops.
2. Hallucination rate < 0.5% measured on the eval set (any factual claim in the draft not present in evidence bundle counts).
3. Cost dashboard: per-agent token cost, P50/P95 latency, failure rate, surfaced in Langfuse.

---

### L07 · Orchestration & State

**Responsibility.** Stateful multi-agent workflows with explicit graph topology, durable execution across SME wait states (which can be hours or days), checkpointing, retries with idempotency keys, human-in-the-loop gates as first-class graph nodes.

**Topology.** LangGraph defines the node graph. Temporal executes it durably.

**Graph (per question):**
```
intake ─► classify ─► library_lookup
                          │
              ┌───────────┴───────────┐
              ▼ hit                   ▼ miss
         freshness_check         retrieve_evidence
              │                        │
              │                        ▼
              │                   draft_compose
              │                        │
              ▼                        ▼
              └────► validate_guardrails ◄────┐
                              │                │
              ┌───────────────┼───────────────┐│
              ▼ pass          ▼ escalate      ▼ halt
         seal_response    sme_approval    legal_review
                              │                │
                              ▼                ▼
                         (loop to validate, with edits)
                              │
                              ▼
                         seal_response
                              │
                              ▼
                         deliver
```

**Per-DDQ aggregator graph** runs N question subgraphs in bounded parallelism (e.g., 8 concurrent), aggregates results, ships unified package.

**Durability.** Temporal workflows survive process death, redeploys, and SME wait states up to 30 days. Each agent call is a Temporal activity with retry policy, idempotency key (`run_id + node_id + attempt`), and timeout.

**State store.**
- Live run state → MongoDB `runs.live`.
- Hot cache for active runs → Redis (TTL 7 days).
- Sealed runs → S3 (Object Lock) + Parquet shadow.

**Interfaces.**
```python
class Orchestrator(Protocol):
    def start_run(self, request: RunRequest) -> RunId: ...
    def get_run(self, run_id: RunId) -> Run: ...
    def submit_sme_decision(self, run_id: RunId, node_id: str, decision: SmeDecision) -> None: ...
    def cancel(self, run_id: RunId, reason: str) -> None: ...
```

**Risks.**
- Long SME waits cause Mongo doc churn → state writes are idempotent; only state transitions write.
- Temporal cluster outage → workflow definitions are deterministic; resume from last checkpoint is automatic.
- Concurrency: >50 concurrent question subgraphs → backpressure via Temporal task queue concurrency limits.

**Acceptance criteria.**
1. Kill the orchestrator pod mid-run; on restart, the run resumes and completes with identical output.
2. SME wait of 7 days: run state intact, on decision submit run progresses normally.
3. P95 end-to-end latency for a 100-question DDQ < 2 hours wall-clock with auto-pass rate at target.

---

### L08 · Client & SME Interface

**Responsibility.** Question intake from any source, SME approval queues segmented by risk tier, client portal for self-service question coverage, review surfaces for legal/security/regulatory sign-off.

**Surfaces.**
- **SME Console** — queues by domain (infosec, ops, regulatory, ESG, cyber, legal). Each item: question, draft, evidence, validation report, action buttons (approve, edit, reject, escalate).
- **Client Portal** — clients submit DDQs, track progress, retrieve sealed responses with citations.
- **Admin** — taxonomy editing, library curation, framework mapping.
- **Audit Viewer** — read-only journal explorer with replay button.

**Stack.** React + TypeScript + Tailwind. Auth via Okta OIDC. Backend: FastAPI gateway with per-route OPA authorization.

**Ingest.**
- Email → Microsoft Graph subscription on a shared inbox (`ddq@bny.com`); attachments parsed by Unstructured.io, questions extracted, Run created.
- SharePoint → connector polls a designated library.
- Portal upload → presigned S3 PUT, then ingest worker handles.
- API → JSON-or-XLSX endpoint for partner integrations.

**Sign-off.** Final outbound packet signed via DocuSign for client-required formal sign-off; signature event journaled.

**Interfaces (representative endpoints).**
```
POST   /api/v1/ddqs                       # create from upload
GET    /api/v1/ddqs/{id}
GET    /api/v1/ddqs/{id}/questions
POST   /api/v1/questions/{id}/approve
POST   /api/v1/questions/{id}/edit
POST   /api/v1/questions/{id}/escalate
GET    /api/v1/runs/{id}/audit            # journal view
POST   /api/v1/runs/{id}/replay           # admin only
```

**Risks.**
- SME queue overload → tier-aware routing + load shedding (auto-batching low-tier items).
- UI showing stale state → all reads go through gateway with run-version etags; UI re-fetches on conflict.
- Client portal data isolation → tenancy enforced at gateway via OPA, never trust client-supplied tenant IDs.

**Acceptance criteria.**
1. SME can approve, edit, reject, escalate any question in their domain queue with < 800ms P95 perceived latency.
2. Email-ingested DDQ shows up in the run list within 60s of inbox arrival.
3. Audit Viewer can replay any run end-to-end and show diff between original and replayed output (should be empty).

---

## 5. The data spine — three domains, three engines

| Domain | Mutability | Mongo | S3 | DuckDB |
|---|---|---|---|---|
| **Knowledge** (policies, SOC, audits, filings) | Mutable, version-tracked | (metadata index) | Raw + Parquet | Analytical reads, freshness reports |
| **Canonical** (taxonomy, mappings, library, do-not-answer) | Versioned releases | Live entries | Sealed snapshots | Reuse analytics, coverage reports |
| **Audit** (journal, retrieval log, approvals, response register, drift events) | Immutable | Hot 30d window | Object Lock (system of record) | Full-history queries |

**Sealing cadence (open decision flagged in cover doc):** start at 24h with a feature flag for 6h; tune based on Mongo storage growth.

**Iceberg vs raw Parquet (open decision):** start raw + Hive partitioning (`by=year/month/day`); plan Iceberg migration in Q2 if/when schema evolution becomes painful.

---

## 6. Request flow (graph node = audit event)

```
01 INTAKE      Email / portal / file → questions parsed → Run created      [audit: intake]
02 CLASSIFY    Framework Q → canonical_id (taxonomy v pinned)              [audit: classify.match]
03 RETRIEVE    Library lookup OR evidence retrieval OR escalate            [audit: retrieve.*]
04 DRAFT       Tiered model routing by canonical tier + complexity         [audit: llm.*]
05 VALIDATE    Citations · PII · freshness · consistency                   [audit: validate.*]
06 APPROVE     Risk-tiered SME queue OR auto-pass                          [audit: approval.*]
07 RESPOND     Sealed · signed · journaled · delivered                     [audit: seal]
```

Each step emits at least one audit event. Any step can route to SME with a typed reason.

---

## 7. Operating levers (non-negotiable practices)

1. **Library as product (60% of effort).** Target: 92% library hit rate. Curation tools are first-class.
2. **Separate retrieve from draft.** Hard architectural boundary. Hallucination rate < 0.5%.
3. **Confidence-tier everything.** Auto-pass target ~70% for tier-2/3, near 0 for tier-1.
4. **Extractive over generative for facts.** Citation resolution 100%.
5. **Version everything that ships.** Bit-exact reproducibility.
6. **Evals on real history.** 500-question regression set in `evals/`. Every prompt/model/retrieval change runs the regression before promotion. CI gate.

---

## 8. The four guardrails (recap, normative)

```
guardrail.01_citation_resolution     → every claim resolves to span+hash, or HALT
guardrail.02_evidence_freshness      → all referenced evidence within validity, or ESCALATE
guardrail.03_cross_ddq_consistency   → no factual divergence vs in-flight or shipped, or HALT
guardrail.04_confidentiality_scrub   → PII / internal-only / client-commercials stripped, or HALT
```

Encoded as Rego policies in `infra/opa-policies/guardrails/`. Validator service evaluates against OPA. Override path requires `legal.review` actor and writes a `do_not_answer` exception or a one-off named override (journaled, time-boxed).

---

## 9. Cross-cutting concerns

### 9.1 Security
- mTLS service-to-service.
- All secrets in AWS Secrets Manager; no env-var secrets in prod.
- KMS-encrypted at rest for Mongo, Qdrant, OpenSearch, Redis, S3.
- Per-entity access scoping enforced via OPA at the gateway and in retrieval/library services.

### 9.2 Observability
- OpenTelemetry traces with `run_id` propagated.
- Langfuse for LLM calls (prompt, response, params, latency, cost).
- Splunk SIEM for security events.
- Dashboards (mandatory, not aspirational): library hit rate, hallucination rate (eval), citation resolution rate, auto-pass rate, P95 latencies per layer, cost per DDQ, freshness-expiry forecast.

### 9.3 Testing
- Unit: pure logic in `core/`, no I/O.
- Integration: testcontainers for Mongo, Qdrant, OpenSearch, Redis. LocalStack for S3. Temporal dev server.
- Contract: every adapter has a contract test that the in-memory and real adapters both pass.
- E2E: 10 representative DDQs through the full pipeline, asserted against gold outputs.
- Eval: 500-question regression. Required pass rate per metric in `evals/thresholds.yaml`. CI blocks promotion on regression.

### 9.4 Versioning & deployment
- Semver per service.
- Blue/green via Helm. Database migrations via Atlas (Mongo) and versioned schemas in `packages/schemas/`.
- Prompt versions deploy independently from code, gated by eval.
- Taxonomy versions cut on schedule (monthly) or on-demand by Compliance.

---

## 10. Build sequencing — milestones for Claude Code

### M1 · Foundations (week 1–2)
- Repo skeleton, CI, IaC stubs.
- `core/domain` and `core/ports` definitions.
- Audit journal MVP (L01): event schema, hash chain, Mongo hot store, S3 seal job, replay shell.
- LLM SDK with Bedrock + Anthropic adapters.
- Eval harness skeleton.

### M2 · The spine (week 3–5)
- Taxonomy service (L05) with classify-by-embedding.
- Library service (L04) with proposal/approval workflow.
- Validator service (L02) with all four guardrails as Rego policies.
- Retrieval service (L03) hybrid pipeline; corpus ingestion worker.

### M3 · Agents and orchestration (week 6–8)
- Agent roster (L06) — implement all 8, prompt registry, model routing.
- Orchestrator (L07) — LangGraph topology + Temporal worker.
- End-to-end happy path on 1 DDQ in dev.

### M4 · Surface and ops (week 9–10)
- API gateway, SME console, client portal, audit viewer (L08).
- Email/SharePoint ingestion.
- Dashboards, runbooks, on-call.
- Eval regression in CI as a hard gate.

### M5 · Hardening (week 11–12)
- Load test to 50 concurrent runs, 200 questions/run.
- Chaos: kill orchestrator, Mongo failover, S3 read-only window, Bedrock throttle.
- Security review: tenancy probes, override audit walk-through.
- Cut taxonomy v1.0, library baseline of approved entries from existing corpus.

---

## 11. Open decisions (track in `docs/decisions/`)

1. **Bedrock vs direct Anthropic API** — model hosting. Default Bedrock for VPC + IAM integration; track latency and cost vs direct.
2. **MongoDB Atlas vs self-managed on EKS** — operational cost vs control. Default Atlas.
3. **S3 table format** — Iceberg vs raw Parquet. Default raw, plan Iceberg.
4. **Mongo→S3 sealing cadence** — 6h vs 24h. Default 24h with feature flag for 6h.
5. **Taxonomy ownership boundary with Compliance** — who can cut versions, what changes need legal sign-off. Draft RACI in `docs/decisions/0001-taxonomy-governance.md`.

---

## 12. Glossary

- **Canonical ID** — taxonomy-stable identifier for a concept-level question (e.g., `canon.is.access_control.privileged_access_review`).
- **Library entry** — the SME-approved, citation-verified answer for a canonical ID, scoped to entity/product.
- **Sealed run** — an immutable, S3-Object-Lock-stored bundle containing every event and artifact needed to reproduce a response bit-exact.
- **Run journal** — the append-only event chain for one run, hash-linked, signed.
- **Tier** — risk classification (1=high, 2=std, 3=low) driving model routing, approver chain, and auto-pass eligibility.
- **Do-not-answer register** — canonical IDs flagged by legal as never-auto-served.

---

## 13. Reading order for an engineer joining the project

1. Section 1 (invariants) — the contract.
2. Section 4 (eight layers) — what to build.
3. Section 9.3 (testing) — how it's verified.
4. Section 10 (build sequencing) — what to do this week.
5. The relevant ADR(s) in `docs/decisions/` for any open decision touching your work.

---

*End of spec. Update via PR; tag `@architecture-board` for changes to invariants or schemas.*

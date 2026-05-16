# QuantumCache Design Specification

**Context substrate for agentic analysis of fund services complexity, surfaced to Eliza-hosted agents via MCP.**

Version 0.1 — Design draft for task breakdown.

---

## 1. Problem Statement and Goals

### 1.1 The Problem

Fund services analysis requires reasoning across heterogeneous, voluminous, and bitemporally evolving artifacts: prospectuses, SAS70/SSAE reports, operating memoranda, system extracts (Eagle, Geneva, InvestOne, Investran), regulatory filings (CBI MMIF, Form PF), client-specific field mappings, and code/DSL artifacts (ACCEL-DSL, ElectronDSL). The "complexity matrix" — the multi-dimensional space of how clients, funds, share classes, service models, source systems, and regulatory regimes intersect — cannot fit into a single LLM context window, cannot be flattened to vector similarity alone, and cannot be expressed as a static schema.

A Windsurf-class experience is needed: scan a corpus, build durable understanding, and answer arbitrarily deep follow-up questions without re-scanning.

### 1.2 The Eliza Constraint

BNY's Eliza platform owns the LLM API key and exposes only chat-session-based agent construction. Agents inside Eliza can call external tools (HTTP APIs, MCP servers) but cannot run privileged multi-step orchestration with full prompt control. QuantumCache must therefore:

- Push all retrieval, ranking, and memory **outside** the model loop, into the tool layer.
- Expose a **small, semantically rich MCP tool surface** that lets a thin Eliza agent answer complex questions in 2–4 tool calls.
- Support **out-of-band batch analysis** (using direct API keys outside Eliza) that materializes findings into a queryable substrate, so the Eliza-facing experience is mostly read-side.

### 1.3 Goals

1. Index a heterogeneous corpus (10⁴–10⁶ documents) with incremental re-indexing.
2. Build and maintain a bitemporal knowledge graph aligned to the canonical fund data model (260+ fields, 13 entity domains).
3. Serve hybrid retrieval (vector + graph + structured) through a stable MCP facade.
4. Persist multi-turn session state so Eliza agents can run extended investigations.
5. Enable pre-computed findings from offline agentic pipelines to be queryable as graph facts.

### 1.4 Non-Goals

- Replacing Eliza as an agent runtime.
- Generic-purpose code intelligence (this is fund-services-domain-specific).
- Real-time streaming ingestion (batch + scheduled is sufficient for v1).

---

## 2. Architectural Overview

### 2.1 Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Eliza Chat Session                       │
│                  (BNY-owned, thin agent)                    │
└─────────────────────────────┬───────────────────────────────┘
                              │ MCP / HTTPS
┌─────────────────────────────▼───────────────────────────────┐
│                  Facade Layer (MCP Server)                  │
│   12 tools: search, graph, mapping, compare, session, write │
└──┬────────────┬──────────────┬──────────────┬───────────────┘
   │            │              │              │
┌──▼───┐  ┌─────▼─────┐  ┌─────▼──────┐  ┌────▼─────────┐
│Vector│  │  Graph    │  │  Session   │  │ Materialized │
│ pgvec│  │ Apache AGE│  │  MongoDB   │  │   Findings   │
└──┬───┘  └─────┬─────┘  └────────────┘  └──────┬───────┘
   │            │                                │
   └────────────┴────────────────────────────────┘
                       │
        ┌──────────────▼───────────────┐
        │   Ingestion & Analysis       │
        │  (offline, direct API keys)  │
        │  - fund-onboarding-analyzer  │
        │  - ACCEL-DSL validation      │
        │  - canonical field mapping   │
        └──────────────────────────────┘
                       │
        ┌──────────────▼───────────────┐
        │  Source Corpus (S3 + Mongo)  │
        └──────────────────────────────┘
```

### 2.2 Three Substrates, One Facade

**Vector substrate** — semantic recall over chunked content. pgvector in Postgres, colocated with the graph for join-friendly queries.

**Graph substrate** — Apache AGE on Postgres. Bitemporal edges. Canonical 260-field model as schema. This is where the complexity matrix lives.

**Session substrate** — MongoDB. Per-Eliza-session working memory, findings, open questions, and tool-call history.

**Materialized findings** — pre-computed analysis outputs (from offline agentic runs with direct API keys) flow into the graph as first-class facts with provenance.

### 2.3 Why This Survives the Eliza Constraint

The Eliza agent is reduced to a **router**: pick the right tool, pass natural language, return rich structured results to the user. All "agentic" intelligence — multi-step retrieval, ranking, graph traversal, cross-document synthesis — happens behind the facade where you have full control. If Eliza changes, the facade is unaffected. If you later run agents externally, they use the same facade.

---

## 3. Component Specifications

### 3.1 Ingestion Pipeline

#### 3.1.1 Inputs

- **S3 buckets** with Object Lock for immutable client document drops.
- **MongoDB collections** from ACE platform output (already-parsed extracts).
- **Direct uploads** through an admin endpoint (manual additions).
- **Scheduled pulls** from connected systems (Eagle, Geneva, etc. — phase 2).

#### 3.1.2 Stages

1. **Discover** — manifest scan, dedupe by content hash, detect file type.
2. **Extract** — type-specific parsers:
   - PDFs → text + layout-aware chunks (preserve tables)
   - DOCX → text + structure
   - XLSX → table-per-sheet + cell metadata
   - JSON/XML → structural parse
   - Code/DSL → AST + tokenization
3. **Classify** — Haiku-tier classifier assigns document type (prospectus, SSAE, ops memo, field map, code, filing) and routes to type-specific downstream handlers.
4. **Chunk** — context-aware splitting (semantic chunks, not fixed-size). Preserve heading hierarchy as metadata.
5. **Embed** — batch through embedding model, write vectors + chunk metadata to pgvector.
6. **Entity-extract** — Sonnet-tier extraction of canonical entities (Fund, ShareClass, Manager, etc.) using the 260-field model as schema. Write as graph nodes with provenance edges back to source chunks.
7. **Relate** — Opus-tier synthesis pass identifies relationships between newly extracted entities and existing graph entities. Writes graph edges with confidence scores.

#### 3.1.3 Tiered Model Routing

Mirrors your DDQ architecture: Haiku for classification and simple extraction, Sonnet for structured entity extraction, Opus for cross-document synthesis and relationship inference. All offline, with direct API keys.

#### 3.1.4 Idempotency

- Content-hash keyed. Re-ingesting the same file is a no-op.
- Re-extraction triggered by parser version bump (stored alongside chunk).
- Graph entities have stable IDs derived from canonical key fields; re-ingestion updates, doesn't duplicate.

### 3.2 Vector Substrate

#### 3.2.1 Schema (Postgres + pgvector)

```sql
CREATE TABLE documents (
  doc_id UUID PRIMARY KEY,
  content_hash TEXT UNIQUE NOT NULL,
  source_uri TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  client_id TEXT,
  fund_id TEXT,
  as_of_date DATE,
  ingested_at TIMESTAMPTZ NOT NULL,
  parser_version TEXT NOT NULL,
  metadata JSONB
);

CREATE TABLE chunks (
  chunk_id UUID PRIMARY KEY,
  doc_id UUID REFERENCES documents(doc_id),
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  heading_path TEXT[],
  embedding vector(1024),
  token_count INT,
  metadata JSONB
);

CREATE INDEX idx_chunks_embedding ON chunks
  USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_doc ON chunks(doc_id);
CREATE INDEX idx_documents_client_fund ON documents(client_id, fund_id);
```

#### 3.2.2 Retrieval

- Cosine similarity with `hnsw` index.
- Metadata pre-filtering (client, fund, doc_type, date range) applied before vector search to keep recall focused.
- Top-k with k=20 default, re-ranked downstream.

### 3.3 Graph Substrate (Apache AGE)

#### 3.3.1 Node Types

Aligned to the canonical 13 entity domains:

- `Client` — top-level fund manager / sponsor
- `Fund` — legal entity
- `ShareClass` — class of a fund
- `Manager` — investment manager (may differ from Client)
- `Custodian`
- `Auditor`
- `Administrator` — typically BNY itself
- `PricingSource`
- `Counterparty`
- `RegulatoryRegime` — e.g. UCITS, '40 Act, CBI MMIF
- `RegulatoryFiling` — instance of a filing
- `Field` — canonical field from the 260-field model
- `SourceSystem` — Eagle, Geneva, InvestOne, Investran instance
- `Document` — back-reference to vector layer
- `Finding` — materialized analysis result

#### 3.3.2 Edge Types

Domain-meaningful relationships:

- `(Client)-[:SPONSORS]->(Fund)`
- `(Fund)-[:HAS_CLASS]->(ShareClass)`
- `(Fund)-[:MANAGED_BY]->(Manager)`
- `(Fund)-[:CUSTODIED_BY]->(Custodian)`
- `(Fund)-[:AUDITED_BY]->(Auditor)`
- `(Fund)-[:PRICED_BY]->(PricingSource)`
- `(Fund)-[:SUBJECT_TO]->(RegulatoryRegime)`
- `(Fund)-[:FILES]->(RegulatoryFiling)`
- `(Fund)-[:SOURCED_FROM]->(SourceSystem)`
- `(SourceSystem)-[:MAPS_FIELD]->(Field)` — with mapping expression as property
- `(Document)-[:EVIDENCES]->(anything)` — provenance
- `(Finding)-[:ABOUT]->(anything)` — analysis output
- `(Finding)-[:DERIVED_FROM]->(Document|Finding)` — citation chain

#### 3.3.3 Bitemporal Properties

Every edge and every mutable node property carries four timestamps:

- `valid_from`, `valid_to` — when the fact is true in the real world
- `recorded_from`, `recorded_to` — when QuantumCache believed it

This lets you answer "what did we think the custody arrangement was as of Q2, given what we knew by July 1?" — essential for audit, dispute resolution, and analyzing how understanding evolved.

Default open intervals: `valid_to = infinity`, `recorded_to = infinity` for current facts. Corrections set `recorded_to` on the old version and insert a new edge.

#### 3.3.4 Provenance

Every fact-bearing edge has properties:

- `source_doc_id` — which document supported this
- `source_chunk_id` — which chunk specifically
- `extractor_version` — which model + prompt produced it
- `confidence` — 0.0 to 1.0
- `reviewed_by` — null until human-reviewed, then user id
- `reviewed_at`

#### 3.3.5 Query Examples

```cypher
-- All funds for a client sharing a pricing source, as of a date
MATCH (c:Client {id: $client_id})-[:SPONSORS]->(f:Fund)
      -[r:PRICED_BY]->(p:PricingSource)
WHERE r.valid_from <= $as_of AND r.valid_to > $as_of
  AND r.recorded_from <= $as_of_recorded AND r.recorded_to > $as_of_recorded
RETURN f, p

-- The complexity matrix slice: dimensions per fund
MATCH (f:Fund)
OPTIONAL MATCH (f)-[:CUSTODIED_BY]->(cu:Custodian)
OPTIONAL MATCH (f)-[:PRICED_BY]->(p:PricingSource)
OPTIONAL MATCH (f)-[:SUBJECT_TO]->(rr:RegulatoryRegime)
OPTIONAL MATCH (f)-[:SOURCED_FROM]->(ss:SourceSystem)
WHERE f.client_id = $client_id
RETURN f.name, collect(DISTINCT cu.name), collect(DISTINCT p.name),
       collect(DISTINCT rr.code), collect(DISTINCT ss.name)
```

### 3.4 Session Substrate (MongoDB)

#### 3.4.1 Why MongoDB

You already run it. Session documents are deeply nested, evolve fast, and don't need transactional integrity with the graph. Soft-delete patterns you've already established apply.

#### 3.4.2 Schema

```javascript
// Collection: qc_sessions
{
  _id: ObjectId,
  session_id: "qc_sess_...",         // Stable, opaque
  eliza_session_id: "...",            // FK to Eliza if known
  user_id: "...",
  created_at: ISODate,
  updated_at: ISODate,
  state: "active" | "archived",
  scope: {                            // What this session is investigating
    client_ids: [...],
    fund_ids: [...],
    topics: [...]
  },
  findings: [                         // Accumulated conclusions
    {
      finding_id: "...",
      content: "...",                 // Natural language
      structured: {...},              // Optional graph-ready facts
      confidence: 0.85,
      evidence: [chunk_id, chunk_id], // Citations
      created_at: ISODate,
      promoted_to_graph: false        // Whether persisted as Finding node
    }
  ],
  open_questions: [...],
  tool_call_history: [                // Last N tool calls for context
    {
      tool: "find_relevant_documents",
      args: {...},
      result_summary: "...",
      timestamp: ISODate
    }
  ],
  pinned_docs: [doc_id, ...],         // Always available in retrieval
  notes: "..."
}
```

#### 3.4.3 Lifecycle

- Sessions auto-create on first tool call referencing a new `session_id`.
- Findings promoted to graph on user command or session close (if confidence ≥ threshold).
- Sessions archived (soft-deleted with tombstone) after 90 days of inactivity.

### 3.5 Facade Layer (MCP Server)

The contract Eliza agents (and external agents) call. Twelve tools. Each returns structured JSON with consistent envelope.

#### 3.5.1 Response Envelope

```json
{
  "ok": true,
  "data": { ... },
  "session_id": "...",
  "tool_call_id": "...",
  "facts_used": [...],         // Graph fact IDs supporting the result
  "documents_used": [...],     // Document IDs supporting the result
  "next_suggested_tools": [...] // Hint to the agent
}
```

#### 3.5.2 Tool Catalog

**Retrieval tools**

1. `find_relevant_documents`
   - `query: string` — natural language
   - `filters: { client_id?, fund_id?, doc_type?, date_range? }`
   - `top_k: int = 10`
   - Returns: ranked chunks with parent doc context, scores, metadata.
   - Behavior: vector search, optionally expanded via graph (if entity in query matches a node, pull docs evidencing connected facts).

2. `read_document_section`
   - `doc_id: string`
   - `chunk_ids: string[]` or `heading_path: string[]`
   - Returns: full content of requested sections plus adjacent chunks for context.

3. `semantic_search_within`
   - `doc_ids: string[]`
   - `query: string`
   - Returns: ranked chunks restricted to specified documents. For drilling into a known doc set.

**Graph tools**

4. `get_entity_graph`
   - `entity_id: string` or `entity_lookup: { type, key_fields }`
   - `depth: int = 2`
   - `as_of_valid: date?` (default: now)
   - `as_of_recorded: date?` (default: now)
   - `edge_types: string[]?` (filter)
   - Returns: subgraph as nodes + edges with provenance.

5. `compare_entities`
   - `entity_ids: string[]` (typically funds or clients)
   - `dimensions: string[]?` (which relationships to compare; default: all)
   - Returns: matrix of entities × dimensions showing where they align and diverge. This is the complexity matrix view.

6. `find_path`
   - `from_id: string`
   - `to_id: string`
   - `max_depth: int = 4`
   - Returns: paths through the graph connecting two entities (e.g. "how is this filing connected to that pricing source").

**Field mapping tools**

7. `get_field_mapping`
   - `client_id: string`
   - `source_field: string` or `canonical_field: string`
   - `source_system: string?`
   - Returns: mapping expression, evidence documents, confidence.

8. `list_canonical_fields`
   - `domain: string?` (one of the 13 entity domains)
   - Returns: canonical field definitions with descriptions.

**Session tools**

9. `get_session_state`
   - `session_id: string`
   - Returns: full session document (findings, open questions, pinned docs).

10. `write_finding`
    - `session_id: string`
    - `content: string`
    - `structured: object?`
    - `evidence: chunk_id[]`
    - `confidence: float`
    - Returns: finding_id. Appends to session.

11. `pin_document`
    - `session_id: string`
    - `doc_id: string`
    - Future retrievals in this session boost pinned docs.

**Write-back tool**

12. `promote_finding_to_graph`
    - `finding_id: string`
    - `target_node_type: string?`
    - `target_edges: [...]?`
    - Returns: created graph node + edge IDs. Marks finding as promoted. Requires confidence above threshold or explicit override.

#### 3.5.3 Authentication and Authorization

- mTLS between Eliza and the facade (or BNY-standard service auth).
- Per-tool authorization: read tools require analyst role, `promote_finding_to_graph` requires reviewer role.
- All calls logged with session_id, user_id, tool, args (sanitized), result size.

### 3.6 Offline Analysis Pipelines

The "agentic" work happens here, outside Eliza, with direct API keys.

#### 3.6.1 Fund Onboarding Analyzer (existing)

Already maps client files to canonical model. Modified to write outputs as graph facts with provenance, not just JSON.

#### 3.6.2 Complexity Matrix Builder

Scheduled job that, for every active client:

1. Pulls all current graph facts.
2. Computes the matrix slice (funds × dimensions).
3. Identifies anomalies (e.g. one fund in a family with a different custodian — usually meaningful).
4. Writes anomalies as `Finding` nodes for analyst review.

#### 3.6.3 Cross-Client Pattern Detector

Periodic Opus-tier pass that looks for patterns across clients (e.g. "five clients with similar fund structures all use the same audit firm — is this a referral pattern, regulatory requirement, or coincidence?"). Findings written to graph, never auto-promoted; surface to analysts.

---

## 4. Hybrid Retrieval Strategy

### 4.1 The Question of Vector vs. Graph vs. Both

For any analyst question, the orchestration is:

1. **Parse intent** — does the question name entities, mention dimensions, or ask conceptually?
2. **Resolve entities** — fuzzy-match named entities to graph nodes; cache the resolutions in session.
3. **Choose path:**
   - Pure conceptual ("explain expense waivers") → vector only.
   - Entity-anchored ("how does Fund X price its book") → graph traversal to find docs evidencing pricing, then vector within those.
   - Comparative ("how do these three funds differ") → graph slice + targeted vector for narrative explanations.
4. **Assemble result** — graph facts give structure; vector chunks give explanation; combine in response.

### 4.2 Re-ranking

First-pass vector recall is high but noisy. Re-rank using:

- Entity match (chunks mentioning resolved entities boosted).
- Recency (newer doc versions boosted, unless query specifies historical).
- Document type prior (regulatory filings boosted for compliance queries; ops memos for operational queries).
- Pinned doc boost from session.

A small cross-encoder model can do this if needed, but rule-based re-ranking is sufficient for v1.

---

## 5. Bitemporal Model in Detail

### 5.1 Why Bitemporal

A single timeline cannot answer: "We told the regulator on April 1 that Fund X used Custodian A. We later learned it had switched to Custodian B on March 15. What was our position as filed?" Two clocks resolve this.

### 5.2 The Four Timestamps

| Timestamp | Meaning |
|---|---|
| `valid_from` | When the fact became true in the real world. |
| `valid_to` | When the fact stopped being true in the real world (or ∞). |
| `recorded_from` | When QuantumCache started believing this fact. |
| `recorded_to` | When QuantumCache stopped believing this version (or ∞). |

### 5.3 Operations

**Insert a new fact:**
```
valid_from = effective date in reality
valid_to = ∞
recorded_from = now()
recorded_to = ∞
```

**Correct a fact (we were wrong):**
```
Old version: recorded_to = now()
New version: same valid_from, recorded_from = now(), recorded_to = ∞
```

**End a fact (reality changed):**
```
Old version: valid_to = end date, recorded_to = now()
New version of old fact: valid_to = end date, recorded_from = now(), recorded_to = ∞
[New successor fact inserted with valid_from = end date]
```

### 5.4 Query Idioms

- **As of now, current understanding:** `valid_to = ∞ AND recorded_to = ∞`
- **As of historical date, current understanding:** `valid_from <= D AND valid_to > D AND recorded_to = ∞`
- **As-was (what we believed at time T):** `valid_from <= D AND valid_to > D AND recorded_from <= T AND recorded_to > T`

### 5.5 Storage Note

Apache AGE stores edges as rows; bitemporal columns are properties. Indexing `(valid_from, valid_to)` and `(recorded_from, recorded_to)` is necessary for performant point-in-time queries. Postgres BRIN or GIST indexes work well on time ranges.

---

## 6. Tech Stack Summary

| Layer | Technology | Rationale |
|---|---|---|
| Vector store | pgvector | Co-located with graph; you know Postgres. |
| Graph store | Apache AGE on Postgres | Your established choice; openCypher; transactional with vector. |
| Session store | MongoDB | Existing infrastructure; nested documents fit. |
| Object store | S3 with Object Lock | Existing; immutable source-of-truth for documents. |
| Embeddings | Voyage or OpenAI | Pluggable; choose per cost/quality. |
| LLM (offline) | Opus / Sonnet / Haiku tiered | Mirrors DDQ architecture. |
| LLM (online via Eliza) | Whatever Eliza routes to | Out of scope; treat as black box. |
| Facade | MCP server (TypeScript) | Standardized tool protocol; works with Eliza and external. |
| Orchestration | ACE platform | Existing ETL/workflow runtime. |
| Observability | OpenTelemetry → existing BNY stack | Standard. |

---

## 7. Phased Delivery Plan

### Phase 0 — Foundation (weeks 1–2)

Set up Postgres with pgvector and AGE, MongoDB collections, S3 buckets, MCP server scaffold. Define the response envelope and tool stubs returning mock data. Goal: an Eliza agent can call all 12 tools and get well-formed responses, even if empty.

### Phase 1 — Vector Path (weeks 3–5)

Build ingestion stages 1–5 (discover → embed). Implement `find_relevant_documents`, `read_document_section`, `semantic_search_within`. Ingest a starter corpus (one client's full document set). Validate retrieval quality with analyst Q&A.

### Phase 2 — Graph Path (weeks 6–9)

Build ingestion stages 6–7 (entity extraction, relation synthesis). Wire canonical 260-field model as graph schema. Implement bitemporal columns and operations. Implement `get_entity_graph`, `compare_entities`, `find_path`, `get_field_mapping`, `list_canonical_fields`. Backfill graph from the Phase 1 corpus.

### Phase 3 — Session and Hybrid (weeks 10–12)

Implement session substrate and tools (`get_session_state`, `write_finding`, `pin_document`). Build hybrid retrieval orchestration (entity resolution + graph expansion + re-ranking). End-to-end test with Eliza-hosted agent running real analyst workflows.

### Phase 4 — Offline Pipelines (weeks 13–16)

Wire fund-onboarding-analyzer to write graph facts. Build complexity matrix builder. Build cross-client pattern detector. Implement `promote_finding_to_graph` with review workflow.

### Phase 5 — Scale and Harden (weeks 17–20)

Performance tuning (index strategy, query plans, embedding batch sizes). Incremental re-indexing on source changes. Multi-client onboarding. Observability dashboards. Documentation for analysts.

---

## 8. Task Breakdown (Initial)

These are sized for individual sprint tickets. Phase 0 and 1 fully decomposed; later phases sketched.

### Phase 0

- QC-001 — Postgres instance provisioning with pgvector and AGE extensions.
- QC-002 — MongoDB collections and indexes for sessions.
- QC-003 — S3 bucket with Object Lock and IAM policies.
- QC-004 — MCP server scaffold (TypeScript, stdio + HTTP transport).
- QC-005 — Response envelope schema and validation library.
- QC-006 — Tool stubs for all 12 tools returning fixture data.
- QC-007 — Eliza connectivity test harness.

### Phase 1

- QC-010 — Document discovery service (S3 manifest scan, content hash).
- QC-011 — PDF extractor with layout-aware chunking.
- QC-012 — DOCX extractor with structure preservation.
- QC-013 — XLSX extractor (table-per-sheet).
- QC-014 — JSON/XML structural parser.
- QC-015 — Document classifier (Haiku tier).
- QC-016 — Semantic chunker with heading path metadata.
- QC-017 — Embedding batch service with retry and rate limiting.
- QC-018 — Documents and chunks schema migration.
- QC-019 — `find_relevant_documents` implementation with metadata pre-filtering.
- QC-020 — `read_document_section` implementation.
- QC-021 — `semantic_search_within` implementation.
- QC-022 — Starter corpus ingestion (one pilot client).
- QC-023 — Retrieval quality eval harness.

### Phase 2

- QC-030 — Canonical model schema as graph node/edge types.
- QC-031 — Entity extractor (Sonnet tier) with structured output.
- QC-032 — Relation synthesizer (Opus tier) with confidence scoring.
- QC-033 — Bitemporal edge schema and operations library.
- QC-034 — Graph indexes for point-in-time queries.
- QC-035 — `get_entity_graph` implementation.
- QC-036 — `compare_entities` (complexity matrix view).
- QC-037 — `find_path` implementation.
- QC-038 — `get_field_mapping` implementation.
- QC-039 — `list_canonical_fields` implementation.
- QC-040 — Backfill from Phase 1 corpus.
- QC-041 — Graph quality eval (entity coverage, relation precision).

### Phase 3

- QC-050 — Session document schema and lifecycle.
- QC-051 — `get_session_state`, `write_finding`, `pin_document`.
- QC-052 — Entity resolution service (fuzzy match + cache).
- QC-053 — Hybrid retrieval orchestrator.
- QC-054 — Re-ranking rules engine.
- QC-055 — End-to-end analyst workflow tests.

### Phase 4

- QC-060 — Refactor fund-onboarding-analyzer to write graph facts.
- QC-061 — Complexity matrix builder job.
- QC-062 — Cross-client pattern detector.
- QC-063 — `promote_finding_to_graph` with reviewer workflow.

### Phase 5

- QC-070 — Performance baseline and tuning.
- QC-071 — Incremental re-indexing on source change events.
- QC-072 — Multi-client onboarding automation.
- QC-073 — Observability dashboards.
- QC-074 — Analyst documentation and runbooks.

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Eliza changes its agent runtime and breaks the calling pattern. | Facade is transport-agnostic; expose HTTP + MCP. External agents can use the same surface. |
| Entity extraction precision insufficient. | Confidence scores + reviewer workflow; never auto-promote low-confidence findings. |
| Bitemporal complexity slows queries. | Aggressive indexing; materialized views for the "current" slice. |
| Vector store grows unbounded. | TTL on old document versions; archive to cold storage with summary stubs in graph. |
| Cross-client pattern detection raises confidentiality concerns. | All cross-client analysis stays internal; findings never surface client A's specifics to client B's analysts. Access control at graph traversal layer. |
| Cost of offline Opus-tier passes. | Batch and cache aggressively; trigger only on material document changes. |

---

## 10. Open Questions

1. **Eliza session correlation:** can we get a stable session ID from Eliza, or must we mint our own `qc_session_id` and have the agent pass it explicitly on every call?
2. **Review workflow UI:** where do reviewers approve findings for graph promotion? New surface in ACE, or a lightweight web app?
3. **Embedding model choice:** Voyage 3 large vs. OpenAI text-embedding-3-large vs. self-hosted (your Qwen3.5-35B setup) — needs benchmark on domain text.
4. **Cypher vs. SQL for graph queries:** AGE supports both; pick one as primary for code consistency.
5. **Source system integration:** Phase 2 graph backfill from documents only, or also direct pulls from Eagle/Geneva/etc.?

---

## 11. Appendix: Example End-to-End Flow

**Analyst question (in Eliza):** *"For Client ACME, which funds have a different custodian than the rest of the family, and what does the documentation say about why?"*

**Eliza agent's actions:**

1. Calls `compare_entities` with all ACME funds, dimensions=["custodian"].
   - QuantumCache executes graph query against current bitemporal slice.
   - Returns matrix: 12 funds, 11 use Custodian A, 1 uses Custodian B.
2. Calls `find_relevant_documents` with query="custodian change rationale", filters={client_id: "ACME", fund_id: "<outlier>"}.
   - Vector search restricted to outlier fund's docs.
   - Returns 4 chunks from a 2024 ops memo and the fund's latest prospectus.
3. Calls `read_document_section` to get full context around the top-ranked chunk.
   - Returns the relevant section: regulatory requirement specific to this fund's strategy.
4. Calls `write_finding` to record: "Fund X uses Custodian B due to [regulatory requirement]; evidence in [doc/chunk]."
5. Composes natural-language answer to the analyst, citing the documents.

The Eliza agent made four tool calls. All retrieval, ranking, and graph reasoning happened in QuantumCache. The agent's LLM only had to choose tools and compose the final answer.

---

*End of specification draft. Open for review and iteration.*

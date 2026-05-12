# AutoGen Lite — multi-agent configuration

In-product configuration UI for the 8-agent L06 roster. Inspired by
Microsoft's AutoGen Studio, scoped to what fits our domain (single
deterministic pipeline, single tenant, journaled writes).

## Why

Today, every part of an agent's behaviour is checked-in code. To change
a system prompt, tier (model), temperature, or the toolset it can call,
an engineer edits `services/<svc>/agent.py` or the prompt `.md`, commits,
redeploys. That works for engineers; it doesn't work for the SMEs who
actually own the answer quality.

This milestone makes the agent stack **configurable from the UI** while
keeping the L01 audit invariants intact. Every change is a new immutable
version pinned to whoever made it; the orchestrator loads the *active*
version on each run; sealed runs reference the version that ran so they
can be replayed exactly.

## Feature inventory (AutoGen Studio mapping)

| AutoGen Studio | QuantumCache equivalent | Status |
|---|---|---|
| Agent Builder | Edit prompt, model, temperature, max_tokens, description, tools | shipped |
| Skill Builder | Skills are code-defined; UI is read-only registry | shipped (read-only) |
| Model Builder | Static registry of Claude tiers; UI is read-only | shipped (read-only) |
| Workflow Builder | L07 pipeline is fixed; UI shows the existing 12-stage strip | reuse Pipeline route |
| Playground | Submit a single question; orchestrator runs it; watch per-agent I/O | shipped |
| Gallery | Two preset configs apply-able to any LLM agent | shipped |
| History | Sealed runs index + per-run walkthrough | reuse Runs route |

## Data model

### Agent

```jsonc
{
  "id": "drafter",
  "name": "DraftComposer",
  "kind": "llm",            // or "rule"
  "description": "Drafts the response from evidence + library entry; cites every claim.",
  "model": "claude-sonnet-4-6",
  "temperature": 0.2,
  "maxTokens": 2048,
  "tools": ["llm.complete", "prompt.registry"],
  "activeVersion": "1.0.0",
  "versionCount": 1,
  "lastEditedAt": null
}
```

Model, temperature, maxTokens, and the toolset are stored alongside the
prompt in the same versioned `.md` frontmatter — bumping the prompt
captures every part of the config atomically.

### Model

Static registry — Claude tiers we have access to.

```jsonc
{
  "id": "claude-opus-4-7",
  "displayName": "Claude Opus 4.7",
  "provider": "Anthropic",
  "tier": "tier1",
  "contextWindow": 1000000,
  "supportsTools": true,
  "supportsThinking": true,
  "pricing": { "inputPerMTok": 15.0, "outputPerMTok": 75.0 }
}
```

### Skill

Tool agents can call. Code-defined today; the UI is a read-only catalog.

```jsonc
{
  "id": "retrieval.hybrid",
  "name": "Retrieval.hybrid",
  "category": "retrieval",
  "description": "BM25 + dense + RRF over the BNY corpus.",
  "ownedBy": "L03",
  "usedBy": ["EvidenceSourcer"],
  "signature": "hybrid(question, k=10) → list[EvidenceSpan]"
}
```

### Playground Run

```jsonc
{
  "runId": "pg_20260512T...",
  "question": "Are audit policies established?",
  "framework": "CAIQ",
  "status": "queued" | "running" | "succeeded" | "failed",
  "submittedAt": "...",
  "completedAt": "...",
  "sealedRunId": "run_20260512T...",  // present once orchestrator finishes
  "error": null
}
```

### Template

Pre-built config bundle that can be applied to an agent.

```jsonc
{
  "id": "conservative-compliance",
  "name": "Conservative compliance",
  "description": "Lower temperature, tighter instruction footprint, max citations.",
  "patch": {
    "temperature": 0,
    "maxTokens": 1024,
    "systemSuffix": "\n\nReject any draft that is not fully supported by the evidence bundle."
  }
}
```

## API contract

All under `/api/v1/`.

### Agents (extends prompt-editor surface)

```
GET    /agents                                 → AgentSummary[]
GET    /agents/{id}                            → AgentDetail (includes active config)
GET    /agents/{id}/versions                   → VersionSummary[]
GET    /agents/{id}/versions/{version}         → PromptDocument
POST   /agents/{id}/versions                   → PromptDocument          (create + optional activate)
PUT    /agents/{id}/active                     → AgentDetail             (activate existing)
GET    /agents/{id}/audit                      → AuditEntry[]
POST   /agents/{id}/apply-template             → PromptDocument          (apply template patch + create new version)
```

### Models

```
GET    /models                                 → Model[]
```

### Skills

```
GET    /skills                                 → SkillSummary[]
```

(`/skills/{id}` for the rich detail view already exists.)

### Playground

```
POST   /playground/runs                        → { runId: "pg_..." }
GET    /playground/runs/{run_id}               → PlaygroundRun
```

### Templates

```
GET    /templates                              → Template[]
```

## UI flows

Five new routes, all under the same shell:

- `/agents` — table: name, kind, model, active version, tools count, last edited.
- `/agents/$agentId` — three tabs:
  - **Config** — system + user template editors, model dropdown,
    temperature slider, maxTokens input, tools multi-select,
    description editor. Save creates a new version (patch bump default,
    activate-immediately toggle).
  - **Versions** — table of versions; activate any row.
  - **History** — audit log (create / activate / template-apply).
- `/models` — read-only cards: provider, tier, context window, pricing.
- `/skills` — read-only table: id, category, owners, agents using it.
- `/playground` — form (question text + framework dropdown), Submit
  → polls status, renders agent-by-agent input/output as each stage
  lands. On success, "Open sealed run →" link.

Sidebar:
```
Home
Pipeline
Run · …
Aria · console
Aria · Q1 review
Skill · Retrieval.hybrid
─────
Agents             ← new
Models             ← new
Skills             ← new
Playground         ← new
```

## Test matrix

### Backend (pytest)

| ID | Asserts |
|---|---|
| AG-01 | `GET /agents` returns 8 entries (6 LLM + 2 rule); LLM ones carry model, tools, params, activeVersion. |
| AG-02 | `GET /agents/drafter` returns full config including `tools[]` and `description`. |
| AG-03 | Rule agents return `kind=rule`, `active=null`. |
| AG-04 | Version create bumps SemVer + writes audit; with `activate=true`, also flips active.txt. |
| AG-05 | Stale baseVersion → 409 with current active version returned. |
| AG-06 | Activate-current is no-op; activate-unknown → 404. |
| AG-07 | `POST /agents/drafter/apply-template` creates a new version with the template's patch merged. |
| AG-08 | Audit entries are newest-first, contain `create` + `activate` + `apply-template`. |
| AG-09 | Bad agent id → 404 across all endpoints. |
| AG-10 | Concurrent activates produce no half-written active.txt (atomic rename). |
| MD-01 | `GET /models` returns Opus 4.7, Sonnet 4.6, Haiku 4.5 with context windows. |
| SK-01 | `GET /skills` returns the L03/L04/L06/etc. skill catalog; each skill lists its owning agent(s). |
| PG-01 | `POST /playground/runs` queues a run, returns playground runId. |
| PG-02 | `GET /playground/runs/{id}` while running returns `status=running`; on completion returns `sealedRunId`. |
| TM-01 | `GET /templates` returns at least the two shipped presets. |

### UI (Playwright + screenshots)

| ID | Flow |
|---|---|
| UI-AG-01 | Sidebar → Agents; assert 8 rows; screenshot. |
| UI-AG-02 | Click DraftComposer; Config tab loaded; screenshot. |
| UI-AG-03 | Change temperature slider, edit system prompt, click Save; new version appears in Versions tab; screenshot. |
| UI-AG-04 | Activate the new version; active badge moves; screenshot. |
| UI-AG-05 | Open History tab; assert 2+ entries (create + activate); screenshot. |
| UI-MD-01 | Visit /models; 3 cards render; screenshot. |
| UI-SK-01 | Visit /skills; rows render; screenshot. |
| UI-PG-01 | Visit /playground; submit a CAIQ question; status flips to running; screenshot. |
| UI-PG-02 | Wait for completion; render shows the agent-by-agent breakdown; screenshot; click "Open sealed run" → navigates to /runs/$runId. |
| E2E-01 | After UI-AG-04 (activated new prompt), run orchestrator end-to-end; assert the latest sealed run's drafter event carries `prompt_version` matching the active version. |

## Security & invariants

- Writes use atomic temp+rename so readers (the orchestrator) never see
  a half-written `active.txt` or version file.
- The audit log is append-only by design. No endpoint deletes lines.
- Playground runs use the same orchestrator binary as the production
  pipeline; there is no separate "test mode" code path that could
  diverge.
- Template application is not magic: it's a deterministic
  string-substitution + numeric override applied at version-create
  time. The result is still a normal version file the user can edit.
- No prompt content is `eval`-ed or interpolated beyond the existing
  `{{var}}` placeholders. Prompt text goes verbatim to Anthropic.
- Auth: still trusts the network boundary in M1. `actor` is a free-text
  field; M3 replaces it with the Okta `sub` claim and gates writes
  through OPA (`agent_editor` role).

## Failure modes the UI must surface

- 409 on save → "Someone else activated version X.Y.Z; reload to see
  their changes" with a Reload button.
- Playground orchestrator subprocess crash → red banner with stderr
  excerpt, link to docker/services state.
- `active.txt` points to a missing file (manual filesystem edit) → fall
  back to highest existing version; UI shows an amber banner.

## What's intentionally out (future)

- **Visual workflow editor** — the L07 graph is fixed in
  `apps/orchestrator/main.py`; AutoGen Studio's drag-and-drop graph
  needs a dynamic LangGraph builder that's a separate piece of work.
- **Multi-turn agent conversations** — our agents are single-turn
  callables in a pipeline; chat-style threads aren't applicable.
- **External tools as skills** — today every skill is one of L03/L04/L05
  ports; binding arbitrary MCP servers / HTTP endpoints needs the
  M2 LangGraph tool-call layer.
- **Per-tenant configs** — single-tenant for M1.

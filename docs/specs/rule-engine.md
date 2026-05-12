# Rule Engine — FreshnessAuditor & ApprovalRouter

**Status:** Implemented (2026-05-12)
**Spec owner:** platform
**Related:** `docs/ddq.md §L06` (rule-based agents), `docs/specs/dataset-management.md` (reference pattern)
**Evidence pack:** `docs/evidence/rule-engine/`

## 1. Goal

Replace the hardcoded thresholds, queue maps and condition trees in
`services/freshness/agent.py` and `services/router/agent.py` with a
configurable rule engine. Operators tune rules through `/rules` in the
UI; SMEs review and approve via `/rules/queue`. Every transition is
captured in the audit journal.

This is the OPA stand-in promised in ddq.md §L06 — a small in-process
DSL persisted as JSON, ready to be re-targeted to real Rego when the
infra adapter lands.

**Non-goals:**
- Real Rego/OPA — deferred to M3.
- Rule-driving any agent beyond Freshness/Approval — deferred.
- Mutating sealed snapshots — they stay immutable per ddq.md invariant 2.

## 2. URL surface

### API (FastAPI)

All under `/api/v1/rules`. camelCase response keys.

```
GET    /api/v1/rules                          → RuleSummary[]   (filter: ?engine=&status=)
GET    /api/v1/rules/queue                    → RuleSummary[]   (status=pending_review)
GET    /api/v1/rules/{rule_id}                → RuleDetail
POST   /api/v1/rules                          → RuleDetail      (creates as status=draft)
PUT    /api/v1/rules/{rule_id}                → RuleDetail      (draft|pending_review only; bumps version; drops pending back to draft)
DELETE /api/v1/rules/{rule_id}                → {deleted:true}  (force=true for bootstrap)
POST   /api/v1/rules/{rule_id}/submit         → RuleDetail      (draft → pending_review)
POST   /api/v1/rules/{rule_id}/approve        → RuleDetail      (pending_review → active; archives logical siblings)
POST   /api/v1/rules/{rule_id}/reject         → RuleDetail      (pending_review → draft; SME rationale captured)
POST   /api/v1/rules/{rule_id}/evaluate       → {ruleId, fired, verdict}    (dry-run vs caller-supplied context)
POST   /api/v1/rules/validate                 → {ok, errors:[{path,msg}]}   (DSL syntax check)
```

**Errors:** `404` unknown id, `409` create-with-existing-id, `422`
validation, `400` lifecycle violation (e.g. approving a draft) or
bootstrap-protected delete without `?force=true`.

### UI (React + TanStack Router)

```
/rules                      RulesListRoute    — table + filters + "+ New rule" button
/rules/queue                RuleQueueRoute    — SME pending-review board
/rules/$ruleId              RuleDetailRoute   — read view + Edit/Submit/Approve/Reject + live evaluation
```

A "Rule engine" section appears in the left nav below "Datasets".

## 3. Wire shapes

### `Rule` (domain)

```python
@dataclass
class Rule:
    rule_id: str                    # ^[A-Za-z0-9._-]+$
    engine: "freshness" | "approval"
    title: str
    description: str
    priority: int                   # lower = evaluated first
    status: "draft" | "pending_review" | "active" | "archived"
    version: str                    # semver; bumped on every edit
    when: Condition                 # see §4
    then: dict                      # engine-specific verdict (see §5)
    review_queue: str               # SME queue ("ops" | "regulatory" | …)
    tags: list[str]
    created_at: str
    updated_at: str
    approved_at: str | None
    approved_by: str | None
    submitted_by: str | None
    rationale: str | None
```

### `RuleSummary` (wire)

```ts
{ ruleId, engine, title, priority, status, version,
  reviewQueue, tags, updatedAt }
```

### `RuleDetail` (wire)

```ts
RuleSummary & {
  description, when, then,
  createdAt, approvedAt, approvedBy, submittedBy, rationale
}
```

## 4. DSL — `when` condition

A condition is a JSON tree of leaves and composites.

**Leaf:**

```json
{ "field": "library_entry.tags", "op": "contains", "value": "bootstrap" }
```

`field` is a dotted path resolved against the agent's flattened context
(see §5). `value` is operator-specific.

**Composite:**

```json
{ "all": [c1, c2, ...] }       // logical AND
{ "any": [c1, c2, ...] }       // logical OR
{ "not": c }                   // negation
```

Empty object `{}` is **vacuously true** — useful for fallthrough rules
(the default-active `approval.auto.clean` ships with `when: {}`).

### Operators

| Op            | Semantics                                              |
|---------------|--------------------------------------------------------|
| `eq` / `ne`   | Python equality / inequality                           |
| `lt`/`lte`/`gt`/`gte` | Numeric (auto-coerce strings; bool rejected)   |
| `in` / `not_in` | Membership in a list/string                          |
| `contains`    | Substring (string) or element (list)                   |
| `matches`     | `re.search(value, str(actual))`                        |
| `startswith` / `endswith` | String prefix / suffix                     |
| `age_days_gt` | `(today − ISO-date(actual)).days > value`              |
| `exists`      | `actual is not None`                                   |
| `truthy`      | `bool(actual)`                                         |

Field paths support list indexing (`evidence.0.form`) and attribute
fallback (`obj.x`).

## 5. DSL — `then` verdict (engine-specific)

### Freshness

```json
{ "stale": true,
  "reason": "library entry {library_entry.id} is bootstrap-tagged",
  "tags": ["library", "bootstrap-guard"] }
```

`reason` supports `{dotted.path}` interpolation; missing paths render `?`.

The agent OR-reduces `stale` across all firing rules and accumulates
`reasons` in priority order.

### Approval

```json
{ "route": "halt", "queue": "legal",
  "rationale": "PiiScrubber raised halt — legal must review." }
```

`route` ∈ `auto_approve | sme_queue | halt | legal_review`. `queue` is
optional — if omitted, the agent uses the canonical-domain mapping
(`canon.is → infosec`, `canon.cyber → cyber`, etc.). Approval rules use
**first-match-wins** semantics (ordered by priority), so the
fallthrough `approval.auto.clean` (priority=999, `when={}`) only fires
when no earlier rule matched.

### Agent context (input → flattened dict)

The agents build a small context dict for the DSL:

**FreshnessAuditor context:**
```python
{
  "library_entry": <dict | {}>,
  "evidence": [<EvidenceSpan dump>...],
  "evidence_oldest": { "pillar3_date": "YYYY-MM-DD" | None },
  "today": "YYYY-MM-DD",
}
```

`evidence_oldest.pillar3_date` is pre-computed (DSL has no list-iteration
primitive yet) and only set when the oldest pillar3 filing exceeds
`PILLAR3_MAX_DAYS`.

**ApprovalRouter context:**
```python
{
  "canonical_id": str | None,
  "classify_confidence": float,
  "validate_verdict": "pass" | "halt" | "escalate",
  "pii_halt": bool,
  "freshness_stale": bool,
  "consistency_drift": bool,
}
```

## 6. Lifecycle FSM

```
                ┌──────────── reject (with rationale)
                ▼
draft ── submit ──▶ pending_review ── approve ──▶ active ── (newer version approved) ──▶ archived
  ▲                       │
  └───── edit (any edit on pending_review drops back to draft;
              version bumps)
```

Permitted transitions:
- POST `/submit`: only on `draft`.
- POST `/approve`: only on `pending_review`. Archives any other `active`
  rule for the same `engine` sharing the first two `.`-segments of the
  rule_id (the "logical sibling" heuristic — keeps the engine deterministic).
- POST `/reject`: only on `pending_review`. Bounces back to `draft`,
  preserving the SME's rationale in `rationale`.
- PUT (edit): only on `draft` or `pending_review`. Bumps minor version.
  Drops pending back to draft (SME must re-submit).
- DELETE: any status. Bootstrap-tagged rules need `?force=true`.

Only `active` rules are evaluated by the agents at runtime.

## 7. Storage

- **Mongo** (`DDQ_USE_MONGO=1`): `ddq.rules` collection, `_id = rule_id`.
  Composite index `(engine, status)`; single-field index on `priority`.
  Adapter at `infra/adapters/mongo_rules.py`.
- **Filesystem** (`DDQ_USE_MONGO=0`, default in CI): one file per rule
  at `data/manifests/rules/<rule_id>.json`. Atomic-write via
  `tempfile.mkstemp` + `os.replace`. Adapter at `infra/adapters/fs_rules.py`.
- **Bootstrap seed**: `data/bootstrap/seed_rules.py` ships 11 rules
  (`bootstrap`-tagged) representing the *current* hardcoded behaviour
  of both agents. Idempotent — re-running upserts.
- **Sealed snapshots** (optional, M3): `MongoRules.snapshot(engine)`
  builds a Merkle-rooted unsigned snapshot; the caller signs (ed25519)
  and writes to `s3://bny-ddq-rules-sealed/{engine}/v{N}/`. Not called
  from the live approve path — keeps tests S3-free.

## 8. Bootstrap rules

These 11 rules ship `status=active`, `tags=["bootstrap", …]`:

| Rule ID                              | Engine     | Priority | Summary                                              |
|--------------------------------------|------------|----------|------------------------------------------------------|
| `freshness.library.expired`          | freshness  | 10       | `expiry_date` < today                                |
| `freshness.library.review_overdue`   | freshness  | 20       | `review_due` < today                                 |
| `freshness.library.bootstrap_tag`    | freshness  | 30       | Library entry carries the `bootstrap` tag            |
| `freshness.evidence.pillar3.age_12mo` | freshness | 40       | Pillar 3 evidence > 12 months                         |
| `approval.halt.pii`                  | approval   | 10       | PiiScrubber raised halt → legal review                |
| `approval.halt.validate`             | approval   | 20       | Validate verdict == halt → legal review               |
| `approval.sme.freshness_stale`       | approval   | 30       | Freshness flagged stale → SME queue                   |
| `approval.sme.consistency_drift`     | approval   | 40       | Drift vs prior shipped responses → SME queue          |
| `approval.sme.low_confidence`        | approval   | 50       | classify_confidence < 0.70 → SME queue                |
| `approval.sme.tier1`                 | approval   | 60       | Tier-1 canonical (reg/cyber/is) → SME queue           |
| `approval.auto.clean`                | approval   | 999      | Fallthrough: auto-approve                             |

## 9. SME queue routing on submit

The `review_queue` for a submitted rule is keyed off the rule's engine:

| Engine    | Default queue | Reasoning                                                  |
|-----------|---------------|------------------------------------------------------------|
| freshness | `ops`         | Date thresholds are operational tuning                     |
| approval  | `regulatory`  | Approval-tree changes have compliance impact               |

This map lives in `_rule_review_queue(engine)` in
`apps/api_gateway/routers/rules.py`. Future work (M3) lifts it into the
rule engine itself (dogfood path — a `rule_review` engine type).

## 10. Verification

| Suite                                                          | Pass count |
|----------------------------------------------------------------|-----------:|
| `tests/unit/test_rule_dsl.py`                                  | 30/30      |
| `apps/api_gateway/tests/test_rules.py`                         | 21/21      |
| `tests/integration/test_rule_engine_end_to_end.py`             | 8/8        |
| `apps/ui/tests/e2e/rules.spec.ts` (Playwright + screenshots)   | 10/10      |

Evidence pack at `docs/evidence/rule-engine/` carries the 10 PNG
screenshots, the integration-test stdout (showing before/after verdict
changes when a rule is edited), and a snapshot of the seeded rules at
evidence-capture time.

Run locally:

```bash
# 1. Unit + API tests
.venv/bin/python -m pytest tests/unit/test_rule_dsl.py apps/api_gateway/tests/test_rules.py tests/integration/test_rule_engine_end_to_end.py -v

# 2. Bring up the API gateway (fs-mode)
DDQ_RUNS_BACKEND=fs DDQ_USE_MONGO=0 .venv/bin/uvicorn apps.api_gateway.main:app --host 127.0.0.1 --port 8001

# 3. Run Playwright (separate shell)
cd apps/ui && npx playwright test --config=playwright.rules.config.ts
```

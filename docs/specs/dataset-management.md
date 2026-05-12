# Dataset Management Feature

**Status:** Implemented (2026-05-12)
**Spec owner:** platform
**Related:** `docs/ddq.md` §L01 (Audit), §L03 (Knowledge), §L05 (Canonical)

## 1. Goal

Give a DDQ operator a single place — `/datasets` — to inspect and manage the three datasets that define the platform's behavior:

| Dataset    | What it is                                                     | Source of truth                                               | CRUD allowed                                |
|------------|----------------------------------------------------------------|---------------------------------------------------------------|---------------------------------------------|
| Knowledge  | Source documents the platform retrieves from (filings, framework docs) | `data/manifests/knowledge-documents.json` + S3 `bny-ddq-knowledge-raw` | List, view, create, update metadata, delete |
| Canonical  | Taxonomy of canonical question IDs (`canon.is.iam.iam_04_q1`)  | `data/manifests/canonical/<id>.json` (fs) or Mongo `taxonomy.questions` | List, view, create, update, delete          |
| Audit      | Sealed L01 run journals (immutable, hash-chained)              | `data/manifests/runs/*.json` (fs) or S3 `bny-ddq-runs-sealed` | List, view, verify-integrity, redact (append-only) |

Audit is **immutable** by contract (ddq.md invariant 2: "no edits to sealed records"). The UI must enforce this — no edit/delete buttons. The only writes allowed are **redaction records** (PII removal under legal hold), which are themselves auditable events appended to a side log.

## 2. URL surface

### API (FastAPI)

All under `/api/v1/datasets`. Camelcase response keys; snake_case path segments.

```
GET    /api/v1/datasets                          → DatasetSummary[]  (3 entries: knowledge|canonical|audit, with counts)

GET    /api/v1/datasets/knowledge                → KnowledgeDoc[]
GET    /api/v1/datasets/knowledge/{doc_id}       → KnowledgeDoc
POST   /api/v1/datasets/knowledge                → KnowledgeDoc          (create)
PUT    /api/v1/datasets/knowledge/{doc_id}       → KnowledgeDoc          (update tags/desc/effective_date)
DELETE /api/v1/datasets/knowledge/{doc_id}       → {deleted: true}

GET    /api/v1/datasets/canonical                → CanonicalSummary[]
GET    /api/v1/datasets/canonical/{canonical_id} → CanonicalDetail
POST   /api/v1/datasets/canonical                → CanonicalDetail       (create)
PUT    /api/v1/datasets/canonical/{canonical_id} → CanonicalDetail       (update)
DELETE /api/v1/datasets/canonical/{canonical_id} → {deleted: true}

GET    /api/v1/datasets/audit                    → AuditRunSummary[]
GET    /api/v1/datasets/audit/{run_id}           → AuditRunDetail
POST   /api/v1/datasets/audit/{run_id}/verify    → AuditVerifyResult     (re-verify chain + Merkle)
POST   /api/v1/datasets/audit/{run_id}/redactions → AuditRedaction        (append a redaction record)
GET    /api/v1/datasets/audit/{run_id}/redactions → AuditRedaction[]
```

Errors: `404` for unknown id; `409` for create-with-existing-id; `422` for body validation; `400` for editing/deleting bootstrap-tagged canonicals (must be force-flagged).

### UI (React + TanStack Router)

```
/datasets                          DatasetsIndex      — three cards with counts + last-updated
/datasets/knowledge                KnowledgeList      — table + filter + "Add document" button
/datasets/knowledge/$docId         KnowledgeDetail    — read-only view of fields + edit/delete actions
/datasets/canonical                CanonicalList      — table + filter + "Add canonical" button
/datasets/canonical/$canonicalId   CanonicalDetail    — fields + framework mappings + edit/delete
/datasets/audit                    AuditList          — table + filter + "Verify" button per row
/datasets/audit/$runId             AuditDetail        — event chain + Merkle root + redact button
```

`/datasets` appears in the left nav under a new section header **"Datasets"**.

## 3. Wire shapes

### `DatasetSummary`
```ts
{ id: "knowledge" | "canonical" | "audit",
  label: string, count: number, lastUpdatedAt: string | null,
  description: string }
```

### `KnowledgeDoc`
Mirrors `data/manifests/knowledge-documents.json` entries, plus a derived `displayTitle`:
```ts
{ docId: string, source: string, entity: string, kind: string | null,
  effectiveDate: string | null, primaryDesc: string,
  docHash: string, contentType: string, bytes: number,
  url: string | null, s3Uri: string, tags: string[],
  ingestedAt: string, updatedAt: string | null,
  displayTitle: string }
```

### `CanonicalDetail`
Mirrors `core.domain.taxonomy.CanonicalQuestion`:
```ts
{ canonicalId: string, label: string, description: string,
  parentId: string | null, tier: 1|2|3, doNotAnswer: boolean,
  owners: string[], tags: string[],
  frameworkMappings: { framework: string, version: string, questionRef: string }[],
  createdAt: string, updatedAt: string }
```

### `AuditRunSummary`
Lifted from existing `RunIndexEntry` shape plus chain stats:
```ts
{ runId: string, ddqId: string, client: string, framework: string,
  verdict: string, sealedAt: string, eventCount: number, merkleRoot: string }
```

### `AuditRunDetail`
```ts
{ runId: string, sealedAt: string, platformVersion: string,
  taxonomyVersion: string, libraryVersion: string,
  input: { questionId, framework, text },
  verdict: string, route: string,
  events: AuditEvent[],          // event_id, kind, agent, ts, payload_hash, prev_hash, chain_hash
  merkleRoot: string,
  redactionCount: number,
  agents: Record<string, any> }
```

### `AuditVerifyResult`
```ts
{ chainOk: boolean, merkleOk: boolean,
  expectedMerkle: string, recomputedMerkle: string,
  brokenAt: string | null, verifiedAt: string }
```

### `AuditRedaction`
```ts
{ redactionId: string, runId: string, eventId: string, field: string,
  reason: string, actor: string, ts: string }
```

## 4. Storage model (filesystem-mode)

* **Knowledge** — `data/manifests/knowledge-documents.json` is rewritten atomically on every mutation (tmpfile + rename). Adding a doc adds an entry without uploading to S3 (metadata-only; ingestion of bytes is out of scope for the management UI).
* **Canonical** — `data/manifests/canonical/<canonical_id>.json` (one file per entry, mtime = updatedAt). Index built lazily.
* **Audit** — `data/manifests/runs/` is **never** written by this feature except for redactions, which land at `data/manifests/audit-redactions/<run_id>.json` (append-only array).

S3 / Mongo backends are unchanged; the API picks the adapter via existing env-var conventions (`DDQ_USE_MONGO=1` → MongoTaxonomy, `DDQ_RUNS_BACKEND=s3` → S3SealedRuns).

## 5. Invariants

1. **Audit immutability** — no PUT or DELETE on sealed runs. Verified by test `DS-AU-IMMUT`.
2. **Bootstrap protection** — canonical entries tagged `"bootstrap"` cannot be deleted without `?force=true`. Verified by `DS-CN-BOOTSTRAP`.
3. **Hash stability** — editing knowledge metadata never recomputes `doc_hash` (it's content-addressed; metadata-only edits leave the hash untouched). Verified by `DS-KN-HASH-STABLE`.
4. **Atomic writes** — every mutation writes via `tmp + os.replace` so a crash mid-write leaves the previous file intact.
5. **Merkle re-verify is read-only** — verifying an audit run reads sealed JSON; never writes. Verified by `DS-AU-VERIFY-RO`.

## 6. Acceptance criteria

| ID            | Description                                                                                       |
|---------------|---------------------------------------------------------------------------------------------------|
| DS-IDX        | `GET /api/v1/datasets` returns three summaries with `count > 0` after seeding                     |
| DS-KN-CRUD    | Knowledge create → list → get → update → delete cycle returns 200 / 200 / 200 / 200 / 200; final list omits the deleted id |
| DS-KN-HASH-STABLE | Update of `tags` does not change `docHash`                                                    |
| DS-CN-CRUD    | Canonical create → list → get → update → delete cycle works; delete blocked on `bootstrap` tag without `?force=true` (returns 400) |
| DS-CN-BOOTSTRAP | Delete a bootstrap-tagged canonical without force flag → 400; with `?force=true` → 200          |
| DS-AU-LIST    | `GET /api/v1/datasets/audit` lists all sealed runs with merkle_root + eventCount                  |
| DS-AU-IMMUT   | `PUT` and `DELETE` on `/api/v1/datasets/audit/{run_id}` return 405                                |
| DS-AU-VERIFY  | `POST /api/v1/datasets/audit/{run_id}/verify` returns `chainOk:true, merkleOk:true` for sealed runs |
| DS-AU-REDACT  | `POST /api/v1/datasets/audit/{run_id}/redactions` creates a redaction; `GET` retrieves it; the original sealed file is unchanged |
| UI-DS-INDEX   | `/datasets` renders three cards with counts                                                       |
| UI-DS-KN-CREATE | "Add document" opens modal; submit appends row to table                                         |
| UI-DS-KN-EDIT | Edit modal updates tags; row reflects new tags after submit                                       |
| UI-DS-KN-DELETE | Delete confirmation removes row from table                                                      |
| UI-DS-CN-CRUD | Canonical create/edit/delete flows mirror knowledge                                               |
| UI-DS-AU-NO-EDIT | Audit detail page has no edit/delete buttons; verify button shows result inline                |
| UI-A11Y      | Axe scan on `/datasets`, `/datasets/knowledge`, `/datasets/canonical`, `/datasets/audit` reports 0 serious/critical violations |

## 7. Pagination

All three list views (`/datasets/knowledge`, `/datasets/canonical`, `/datasets/audit`) paginate client-side **after** filtering. Approach + rationale:

* **Filter, then paginate.** Search/source/tier/framework filters are applied first; the paginator only sees the filtered set. Page counts therefore reflect the user's current view, not the underlying dataset.
* **Reset on filter change.** Typing in search or changing a filter resets to page 1. Staying on page 7 while the filter only yields 3 rows is bad UX.
* **Reset on page-size change.** Bumping rows-per-page also resets to page 1 — otherwise "show me more" can land the user on a phantom page past the new page count.
* **Hidden when not needed.** The paginator returns `null` if the filtered total fits in the smallest page-size option (10). Filters that narrow results into that range silently hide the controls.
* **Page-size options:** 10, 25, 50, 100. Default 25.
* **Client-side, not server-side.** The fs-mode datasets here are < 1k records each (126 knowledge, ~550 canonical, ~hundreds of runs eventually). Client-side pagination keeps interactions instant and lets the existing array-returning endpoints stay unchanged. Server-side pagination (`?limit`/`?offset`/`X-Total-Count`) becomes the right move once any one dataset crosses ~10k records; the port-level repos already iterate lazily.

### Acceptance criteria (pagination)

| ID                | Description                                                                                       |
|-------------------|---------------------------------------------------------------------------------------------------|
| UI-DS-PAGE        | With > 25 rows: paginator visible; default page-size 25; Next advances range; Last disables Next; size-50 shows up to 50 rows starting at row 1 |
| UI-DS-PAGE-FILTER | Changing the search input while on page 3 resets the paginator to page 1                          |
| UI-DS-PAGE-HIDE   | When the filtered total ≤ 10 the paginator is not rendered                                        |

## 8. Non-goals

* Bulk import — single-doc create only.
* S3 object upload — knowledge create only registers metadata; bytes ingestion stays in `data/bootstrap/`.
* Live Mongo writes from the UI — fs-mode is canonical for this feature; Mongo wiring is the M1 task.
* Sealed-run re-signing — verify is read-only.
* Cohere-rerank-aware canonical merging — canonical create here is a plain upsert; embedding sync remains in `09_build_taxonomy.py`.

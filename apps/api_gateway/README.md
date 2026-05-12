# apps/api_gateway — QuantumCache API

FastAPI surface that backs `apps/ui/`. Implements the endpoint contract the
UI already declares in `apps/ui/src/api/`:

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/healthz` | `{status, runs, ddqs, runs_dir, inbox_dir}` |
| GET | `/api/v1/runs` | `RunIndexEntry[]` |
| GET | `/api/v1/runs/{run_id}` | `RunView` |
| GET | `/api/v1/pipelines` | `PipelineIndexEntry[]` |
| GET | `/api/v1/pipelines/{ddq_id}` | `Pipeline` |
| GET | `/api/v1/employees/{employee_id}` | `EmployeeConsole` (`aria` only today) |
| GET | `/api/v1/employees/{employee_id}/reviews/{period}` | `PerformanceReview` (`aria`/`q1-2026` only) |
| GET | `/api/v1/skills/{skill_id}` | `SkillDetail` (`retrieval-hybrid` only) |

## How it works

The orchestrator (`apps/orchestrator/main.py`) writes hash-chained, Merkle-rooted
sealed runs to **two** locations:

- `data/manifests/runs/run_*.json` + `data/manifests/inbox/ddq_*.json` (local FS)
- `s3://bny-ddq-runs-sealed/<run_id>/sealed.json` (LocalStack with Object Lock)

This API reads the **filesystem mirror** through:

- `core/ports/sealed_runs.py` → `infra/adapters/fs_sealed_runs.py`
- `core/ports/manifests.py`  → `infra/adapters/fs_manifests.py`

…then projects the raw sealed JSON into the UI shape using the exact same
`build_*` functions that `data/bootstrap/12_build_ui_fixtures.py` and
`data/bootstrap/13_build_pipeline_fixtures.py` already use to generate the
on-disk UI fixtures. No duplication, no drift — the existing fixture-based
UI tests pin the wire shape to the same code path.

When the M1 audit service (L01) lands, swap the FS adapter for an S3 adapter
without touching call sites.

## Run it

```bash
# from repo root
.venv/bin/pip install 'fastapi>=0.110,<1' 'uvicorn[standard]>=0.27,<1' httpx pytest
.venv/bin/uvicorn apps.api_gateway.main:app --reload --port 8000
```

Sanity check:

```bash
curl -s http://localhost:8000/healthz | jq
curl -s http://localhost:8000/api/v1/runs | jq '.[0]'
curl -s http://localhost:8000/api/v1/pipelines | jq
```

Interactive docs at <http://localhost:8000/docs>.

## Point the UI at it

Edit `apps/ui/.env.local` (or export at shell):

```
VITE_API_MODE=http
VITE_API_BASE_URL=http://localhost:8000
```

Default CORS allows the Vite dev server (`http://localhost:5173`).

## Env vars

| Var | Default | Purpose |
| --- | --- | --- |
| `DDQ_REPO_ROOT` | inferred | absolute repo root |
| `DDQ_RUNS_DIR` | `$REPO/data/manifests/runs` | sealed-run JSON dir |
| `DDQ_INBOX_DIR` | `$REPO/data/manifests/inbox` | sealed-packet JSON dir |
| `DDQ_MANIFESTS_DIR` | `$REPO/data/manifests` | aggregate manifest dir |
| `DDQ_EVALS_REPORTS_DIR` | `$REPO/evals/reports` | eval reports dir |
| `DDQ_CORS_ORIGINS` | `http://localhost:5173` | comma-separated CORS allowlist |

## Tests

```bash
.venv/bin/python -m pytest apps/api_gateway/tests/ -v
```

The smoke test asserts:

- **Per-run, per-pipeline, per-skill** responses round-trip *bit-exact* against
  the on-disk UI fixtures (`apps/ui/src/mocks/fixtures/`).
- **Aggregate** responses (`/employees`, `/reviews`) match the fixture
  *structurally* — they aggregate over every sealed run on disk, so absolute
  values grow as the orchestrator runs more questions.

## What's not in scope here

- Writes / agent triggering. The UI is read-only today; orchestrator runs are
  triggered by `apps.orchestrator.main` (.eml-driven). M1 will add
  `POST /api/v1/ddqs` (or equivalent) that enqueues an intake.
- Auth. Okta + OPA per ddq.md §L08 lands when the real services do.
- Live S3 / Mongo. Adapters exist for filesystem only; the ports are stable
  so a `S3SealedRuns` adapter is a drop-in when LocalStack parity is verified.

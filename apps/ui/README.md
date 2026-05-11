# DDQ UI

Operator-facing console for the BNY Aria DDQ digital employee. Implements the
four mockups under `docs/ux/`:

| Route                                       | Mockup                                       |
| ------------------------------------------- | -------------------------------------------- |
| `/runs/:runId`                              | `ddq_workflow_user_perspective_data_layer`   |
| `/employees/:de`                            | `ddq_digital_employee_console`               |
| `/employees/:de/review/:period`             | `aria_q1_performance_review`                 |
| `/skills/:skillId`                          | `skill_detail_retrieval_hybrid`              |

## Stack

- Vite + React 18 + TypeScript
- TanStack Router (typed routes, search params) + TanStack Query
- Tailwind 3 + design tokens lifted from the mockups (`tailwind.config.ts`)
- Chart.js 4 (lazy loaded, only on the review route)
- Vitest + RTL + MSW for unit/integration; Playwright + `@axe-core/playwright` for e2e

## Develop

```bash
cd apps/ui
npm install
npm run dev          # http://localhost:5173
npm run typecheck
npm run lint
npm test             # vitest run
npm run e2e          # playwright (auto-starts dev server)
```

## Where the data comes from

`src/mocks/fixtures/` is **generated**, not hand-written. Source of truth is
the bootstrap pipeline under `data/manifests/`:

| Generated fixture                       | Built from                                                          |
| --------------------------------------- | ------------------------------------------------------------------- |
| `runs/<run_id>.json`                    | `data/manifests/runs/<run_id>.json` (5 sealed runs)                 |
| `runs-index.json`                       | aggregate of the per-run journals                                   |
| `employee.json`                         | `wire-up-report.json` + `taxonomy-v0.1-report.json` + `library-v0.1-report.json` |
| `review-q1.json`                        | `evals/reports/v0-baseline.json` + the run journals                 |
| `skill-retrieval.json`                  | `hybrid-smoke-report.json` + `opensearch-index-report.json` + `qdrant-index-report.json` |

Regenerate after any bootstrap step refreshes a manifest:

```bash
.venv/bin/python data/bootstrap/12_build_ui_fixtures.py
```

The script is the production type contract: the eventual backend should emit
the same shapes against the same endpoint paths.

## Wiring to a real backend

To switch from fixtures to live HTTP:

```sh
VITE_API_MODE=http VITE_API_BASE_URL=https://api.example.com npm run dev
```

The proposed endpoints are documented in the JSDoc on `src/api/runs.ts`,
`src/api/employees.ts`, `src/api/skills.ts` — the server should populate the
same shape and the UI is wired through unchanged.

## Structured tokens

Rich text in fixtures (anywhere a "code chip" or `<strong>` would appear) is
expressed as a `Token[]` from `src/types/tokens.ts`:

```jsonc
[
  { "kind": "text", "value": "Run records the active " },
  { "kind": "code", "value": "taxonomy_version_id" },
  { "kind": "text", "value": " for reproducibility" }
]
```

Rendered through `src/components/shell/Tokens.tsx`. No `dangerouslySetInnerHTML`
anywhere — the token vocabulary is the contract.

# Rule Engine — Evidence Pack

**Captured:** 2026-05-12
**Spec:** [`docs/specs/rule-engine.md`](../../specs/rule-engine.md)
**Builds against:** services/freshness/agent.py @ v1.1.0, services/router/agent.py @ v1.1.0

This folder is the proof-of-correctness pack for the rule engine
feature. It bundles the rule snapshot at capture time, the
end-to-end integration test transcript, and the 10 Playwright
screenshots covering create → adjust → approve → live-evaluate.

## Contents

- `seed-rules.json` — full JSON dump of the 11 bootstrap rules from
  `data/manifests/rules/*.json` at evidence-capture time. Provenance
  for the screenshots below.
- `seed-rules-summary.json` — the camelCase API projection (`RuleSummary[]`)
  used to seed UI fixtures (`apps/ui/src/mocks/fixtures/rules/index.json`).
- `integration-test-output.txt` — captured stdout of `pytest -v -s`
  on `tests/integration/test_rule_engine_end_to_end.py`. Critical: it
  shows the **before-edit** and **after-edit** verdicts for both
  agents, proving the rule engine drives the agent verdict (not just
  decoration).
- `screenshots/` — 10 PNGs from `apps/ui/tests/e2e/rules.spec.ts`.

## Test results summary

| Suite                                                          | Result   |
|----------------------------------------------------------------|----------|
| `tests/unit/test_rule_dsl.py`                                  | 30/30 ✓  |
| `apps/api_gateway/tests/test_rules.py`                         | 21/21 ✓  |
| `tests/integration/test_rule_engine_end_to_end.py`             |  8/8  ✓  |
| `apps/ui/tests/e2e/rules.spec.ts` (Playwright)                 | 10/10 ✓  |
| **Total**                                                      | **69/69** ✓ |

## Screenshot index

The Playwright suite drives a single rule (`test.freshness.e2e_<rand>`)
end-to-end through the full lifecycle, capturing a screenshot at every
state transition:

| File                              | What it shows                                                  |
|-----------------------------------|----------------------------------------------------------------|
| `rules_01_index.png`              | `/rules` list view, 11 seeded bootstrap rules                  |
| `rules_02_create_modal.png`       | "New rule" modal, structured-mode form filled                  |
| `rules_03_detail_draft.png`       | Just-created rule, status=Draft, version=1.0.0                 |
| `rules_04_edit_modal.png`         | Edit modal, priority changed from 75 → 25                      |
| `rules_05_detail_after_edit.png`  | Detail post-edit, version=1.1.0 (semver minor bump)            |
| `rules_06_submit_pending.png`     | Status flipped to "Pending review" via Submit modal            |
| `rules_07_queue_view.png`         | `/rules/queue` SME board listing the submission                |
| `rules_08_approve_modal.png`      | Approval modal capturing approver + rationale                  |
| `rules_09_detail_active.png`      | Final state: status=Active, approvedBy populated               |
| `rules_10_engine_proof.png`       | Live evaluation panel: rule fires against sample input, returning the interpolated verdict |

## The integration proof

`integration-test-output.txt` captures the load-bearing evidence: that
the rule engine actually drives agent behaviour. Excerpts:

```
test_freshness_rule_edit_changes_verdict
  [BEFORE EDIT] stale=True reasons=['library entry is bootstrap-tagged — needs SME re-approval before client packet']
  [AFTER EDIT]  stale=False reasons=[]

test_approval_lower_confidence_threshold
  [BEFORE THRESHOLD EDIT] route=auto_approve queue=ops rationale=All guardrails pass; tier-2/3 domain auto-approves.
  [AFTER THRESHOLD EDIT]  route=sme_queue queue=ops rationale=Classify confidence below 0.70 SME threshold — SME confirmation required.

test_approval_inactive_rule_does_not_fire
  [BEFORE ARCHIVE] route=halt queue=legal
  [AFTER ARCHIVE]  route=auto_approve queue=ops rationale=All guardrails pass; tier-2/3 domain auto-approves.
```

Same agent code, same input → different verdict, exactly because a
rule's `when`/`status`/`then` changed. That's the contract the rule
engine ships.

## Reproducing

```bash
# Backend tests
.venv/bin/python -m pytest \
  tests/unit/test_rule_dsl.py \
  apps/api_gateway/tests/test_rules.py \
  tests/integration/test_rule_engine_end_to_end.py -v -s

# UI tests — needs the API gateway running:
DDQ_RUNS_BACKEND=fs DDQ_USE_MONGO=0 \
  .venv/bin/uvicorn apps.api_gateway.main:app --host 127.0.0.1 --port 8001 &
cd apps/ui && npx playwright test --config=playwright.rules.config.ts
```

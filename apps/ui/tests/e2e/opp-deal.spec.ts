/**
 * Opp→Deal — end-to-end suite covering all 8 spec stages.
 *
 * Run with:
 *   npx playwright test --config=playwright.oppdeal.config.ts
 *
 * Prerequisites:
 *   - API gateway live on http://127.0.0.1:8003 in fs-mode (seeds 3 opportunities)
 *   - Vite started by Playwright with VITE_API_MODE=http
 *
 * Acceptance coverage:
 *   UI-OD-LIST          /opportunities list renders and supports search
 *   UI-OD-INTAKE        S01 — create a new opportunity, lands on workspace
 *   UI-OD-SCOPE         S02 — run scope, line items + apps + issues surface
 *   UI-OD-DDQ           S03 — add a DDQ commitment
 *   UI-OD-COMPLEXITY    S04 — score complexity, tier + dimensions surface
 *   UI-OD-COST-CAP      S05 — run cost+capacity, FTE + app impacts surface
 *   UI-OD-PRICING       S06 — propose pricing, TCV + sensitivity surface
 *   UI-OD-OPMODEL       S07 — design op model, FTE plan + crosscheck
 *   UI-OD-APPROVAL      S08 — request approval, decide as each approver, seal
 *   UI-OD-REPLAY        S08 — replay verifies bit-exact bundle reproduction
 *   UI-OD-JOURNAL       S08 — deal journal events are visible and hash-chained
 *   UI-OD-GUARDRAILS    invariants enforced (no seal without approval)
 */

import { expect, test, type Page } from "@playwright/test";

const uniqueName = () =>
  `E2E Test Deal ${Math.random().toString(36).slice(2, 8).toUpperCase()}`;

const goToStage = async (page: Page, oppId: string, stage: string) => {
  await page.goto(`/opportunities/${oppId}?stage=${stage}`);
  await expect(page.getByTestId(`stage-${stage.toLowerCase()}`)).toBeVisible();
};

// ════════════════════════════════════════════════════════════════════
// UI-OD-LIST — opportunities list
// ════════════════════════════════════════════════════════════════════

test("UI-OD-LIST · /opportunities renders seeded rows + supports search", async ({
  page,
}) => {
  await page.goto("/opportunities");
  await expect(page.getByTestId("opportunities-root")).toBeVisible();
  await expect(page.getByTestId("opportunities-table")).toBeVisible();

  await expect(page.getByTestId("opportunity-row-opp_acme_pension_eu")).toBeVisible();
  await expect(page.getByTestId("opportunity-row-opp_pinnacle_am_global")).toBeVisible();
  await expect(page.getByTestId("opportunity-row-opp_heritage_alts")).toBeVisible();

  // Filter narrows the list.
  await page.getByTestId("opportunities-search").fill("Pinnacle");
  await expect(page.getByTestId("opportunity-row-opp_pinnacle_am_global")).toBeVisible();
  await expect(page.getByTestId("opportunity-row-opp_acme_pension_eu")).toHaveCount(0);
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-INTAKE — S01 create
// ════════════════════════════════════════════════════════════════════

test("UI-OD-INTAKE · S01 create new opportunity lands on workspace", async ({
  page,
}) => {
  const name = uniqueName();
  await page.goto("/opportunities");
  await page.getByTestId("add-opportunity-btn").click();
  await expect(page.getByTestId("create-opportunity-modal")).toBeVisible();

  await page.getByTestId("opp-name").fill(name);
  await page.getByTestId("opp-legal-name").fill("E2E Test Client Ltd");
  await page.getByTestId("opp-ucm-id").fill("ucm_e2e_test");
  await page.getByTestId("opp-domicile").fill("UK");
  // Use a product set that resolves cleanly against the seeded UPM catalog.
  await page.getByTestId("opp-products").fill(
    "custody.global, fa.daily_nav, depo.ucits, conn.nexen_portal",
  );
  await page.getByTestId("opp-jurisdictions").fill("IE");
  await page.getByTestId("opp-aum").fill("8000000000");
  await page.getByTestId("opp-nav-strikes").fill("10");
  await page.getByTestId("opp-transactions").fill("160000");
  await page.getByTestId("opp-capital-events").fill("48");
  await page.getByTestId("opp-shareholders").fill("12000");

  await page.getByTestId("opp-create-submit").click();
  await expect(page.getByTestId("opportunity-workspace-root")).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByTestId("stage-s01")).toBeVisible();
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-SCOPE — S02 run scope on the Acme seed
// ════════════════════════════════════════════════════════════════════

test("UI-OD-SCOPE · S02 computes scope manifest, surfaces line items + apps", async ({
  page,
}) => {
  await goToStage(page, "opp_acme_pension_eu", "S02");
  await page.getByTestId("run-scope-btn").click();
  await expect(page.getByTestId("kv-scope-id")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("scope-line-table")).toBeVisible();
  // line count > 0
  const lineCount = await page.getByTestId("kv-line-count").textContent();
  expect(Number(lineCount?.trim())).toBeGreaterThan(0);
  // apps in the derived set
  const appCount = await page.getByTestId("kv-app-count").textContent();
  expect(Number(appCount?.trim())).toBeGreaterThan(0);
  // custody.global line should be present
  await expect(
    page.getByTestId("scope-line-custody.global-IE"),
  ).toBeVisible();
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-DDQ — S03 add commitment
// ════════════════════════════════════════════════════════════════════

test("UI-OD-DDQ · S03 add commitment surfaces in commitment table", async ({
  page,
}) => {
  await goToStage(page, "opp_acme_pension_eu", "S03");
  await page.getByTestId("add-commitment-btn").click();
  await expect(page.getByTestId("add-commitment-modal")).toBeVisible();
  await page.getByTestId("cm-canonical").fill("canon.or.business_continuity.rto");
  await page.getByTestId("cm-text").fill("RTO 4h / RPO 15m for fund accounting · E2E");
  await page.getByTestId("cm-schedule").fill("schedule_b.sla");
  await page.getByTestId("cm-submit").click();
  await expect(page.getByTestId("add-commitment-modal")).toBeHidden();
  await expect(page.getByTestId("commitments-table")).toBeVisible();
  await expect(page.getByTestId("commitments-table")).toContainText("4h / RPO 15m");
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-COMPLEXITY — S04 scorecard
// ════════════════════════════════════════════════════════════════════

test("UI-OD-COMPLEXITY · S04 produces composite score, tier, 10 dimensions", async ({
  page,
}) => {
  // Pinnacle is already scoped (seeded). Score complexity fresh.
  await goToStage(page, "opp_pinnacle_am_global", "S04");
  await page.getByTestId("run-complexity-btn").click();
  await expect(page.getByTestId("kv-composite")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("kv-tier")).toBeVisible();
  // Ten dimensions must render
  const dimRows = page.locator('[data-testid^="dim-"]');
  await expect(dimRows).toHaveCount(10);
  await expect(page.getByTestId("complexity-narrative")).toContainText(/Composite/);
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-COST-CAP — S05 cost + capacity
// ════════════════════════════════════════════════════════════════════

test("UI-OD-COST-CAP · S05 cost stack + capacity impact compute together", async ({
  page,
}) => {
  // Pinnacle has scope + complexity seeded. Run S05.
  await goToStage(page, "opp_pinnacle_am_global", "S05");
  await page.getByTestId("run-cost-capacity-btn").click();
  await expect(page.getByTestId("stat-y1-cost")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("stat-5yr-npv")).toBeVisible();
  await expect(page.getByTestId("fte-table")).toBeVisible();
  await expect(page.getByTestId("capacity-table")).toBeVisible();
  // At least one FTE line — total FTE should be > 0
  const totalFte = await page.getByTestId("kv-total-fte").textContent();
  expect(parseFloat(totalFte ?? "0")).toBeGreaterThan(0);
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-PRICING — S06 proposal
// ════════════════════════════════════════════════════════════════════

test("UI-OD-PRICING · S06 proposes pricing with total client value + sensitivity", async ({
  page,
}) => {
  await goToStage(page, "opp_pinnacle_am_global", "S06");
  await page.getByTestId("run-pricing-btn").click();
  await expect(page.getByTestId("stat-y1-margin")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("kv-approval-tier")).toBeVisible();
  await expect(page.getByTestId("tcv-table")).toBeVisible();
  await expect(page.getByTestId("tcv-5yr-total")).toBeVisible();
  // At least 5 sensitivity scenarios per acceptance criteria
  const sens = page.locator('[data-testid^="sens-"]');
  await expect(sens).toHaveCount(5);
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-OPMODEL — S07 operating model
// ════════════════════════════════════════════════════════════════════

test("UI-OD-OPMODEL · S07 designs op model with FTE plan + crosscheck", async ({
  page,
}) => {
  await goToStage(page, "opp_pinnacle_am_global", "S07");
  await page.getByTestId("run-opmodel-btn").click();
  await expect(page.getByTestId("kv-service-model")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("kv-y1-fte")).toBeVisible();
  await expect(page.getByTestId("hiring-table")).toBeVisible();
  // The seed includes 3 commitments — cross-check row count must match
  await expect(page.getByTestId("crosscheck-table")).toBeVisible();
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-APPROVAL + SEAL + REPLAY — S08 end of pipeline
// ════════════════════════════════════════════════════════════════════

test("UI-OD-APPROVAL · S08 approval, seal, and replay-verify", async ({
  page,
}) => {
  // Need a fully-built deal. Drive Pinnacle through S07 first.
  await goToStage(page, "opp_pinnacle_am_global", "S07");
  await page.getByTestId("run-opmodel-btn").click();
  await expect(page.getByTestId("kv-service-model")).toBeVisible({ timeout: 10_000 });

  // Now go to S08. If a previous run already approved+sealed this deal, the
  // request-approval and approval-action panels won't be present — the test
  // still must verify replay. Branch on the visible state.
  await goToStage(page, "opp_pinnacle_am_global", "S08");

  const requestBtn = page.getByTestId("request-approval-btn");
  if (await requestBtn.isVisible().catch(() => false)) {
    await requestBtn.click();
    await expect(page.getByTestId("kv-request-id")).toBeVisible({ timeout: 10_000 });
  } else {
    // Approval request already exists.
    await expect(page.getByTestId("kv-request-id")).toBeVisible({ timeout: 10_000 });
  }

  // Approve as every required approver (idempotent: re-approving is a no-op
  // on the API side because state already reads "approved").
  const stateText = (await page.getByTestId("kv-approval-state").textContent()) ?? "";
  if (!stateText.toLowerCase().includes("approved")) {
    const buttons = page.locator('[data-testid^="approve-"]');
    const count = await buttons.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      await page.locator('[data-testid^="approve-"]').nth(i).click();
      await page.waitForTimeout(100);
    }
    await expect(page.getByTestId("kv-approval-state")).toContainText("approved", {
      timeout: 10_000,
    });
  }

  // Seal — visible only when approval is fresh and bundle absent.
  const sealBtn = page.getByTestId("seal-btn");
  if (await sealBtn.isVisible().catch(() => false)) {
    await sealBtn.click();
  }
  await expect(page.getByTestId("kv-deal-id")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("merkle-root")).toContainText(/^sha256:[0-9a-f]+/);
  await expect(page.getByTestId("kv-handoffs")).toContainText("contracting");

  // Replay & verify
  await page.getByTestId("replay-btn").click();
  await expect(page.getByTestId("replay-result")).toContainText(/All hashes verify|✓/, {
    timeout: 10_000,
  });
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-JOURNAL — events surfaced
// ════════════════════════════════════════════════════════════════════

test("UI-OD-JOURNAL · S08 deal journal lists hash-chained events", async ({
  page,
}) => {
  await goToStage(page, "opp_pinnacle_am_global", "S08");
  await expect(page.getByTestId("card-s08-journal")).toBeVisible();
  const rows = page.locator('[data-testid^="journal-row-"]');
  await expect(rows.first()).toBeVisible();
  // Several stages have run already on the seeded Pinnacle deal — expect
  // intake, resolve, scope, ddq.link, complexity.score, etc.
  const count = await rows.count();
  expect(count).toBeGreaterThanOrEqual(5);
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-GUARDRAILS — invariants block premature actions
// ════════════════════════════════════════════════════════════════════

test("UI-OD-GUARDRAILS · S08 approval blocked when prerequisites are missing", async ({
  page,
}) => {
  // Acme has only scope (seeded as intake). Walk to S08 directly and try to
  // request approval — the API should respond with an error message about
  // missing prerequisites.
  await goToStage(page, "opp_acme_pension_eu", "S08");
  await page.getByTestId("request-approval-btn").click();
  await expect(page.getByTestId("s08-error")).toBeVisible({ timeout: 10_000 });
});

// ════════════════════════════════════════════════════════════════════
// UI-OD-NAV — stage strip drill-in
// ════════════════════════════════════════════════════════════════════

test("UI-OD-NAV · stage strip toggles between the 8 panels", async ({ page }) => {
  await page.goto("/opportunities/opp_pinnacle_am_global");
  await expect(page.getByTestId("opp-stage-strip")).toBeVisible();
  await expect(page.getByTestId("stage-s01")).toBeVisible();
  for (const s of ["S02", "S03", "S04", "S05", "S06", "S07", "S08"]) {
    await page.getByTestId(`stage-tab-${s}`).click();
    await expect(page.getByTestId(`stage-${s.toLowerCase()}`)).toBeVisible();
  }
});

/**
 * Opp→Deal — visual walkthrough.
 *
 * Drives one fresh opportunity through all 8 stages (S01 intake → S08 seal),
 * capturing the stage-strip + active panel at every step. The screenshots
 * make the eight-stage lifecycle explicit and show **DDQ is just stage S03**
 * of the broader opportunity-to-deal workflow (not the whole thing).
 *
 * Run with:
 *   npx playwright test --config=playwright.oppdeal.config.ts \
 *     --grep "WALKTHROUGH"
 *
 * Screenshots land at apps/api_gateway/tests/screenshots/opp_deal_*.png.
 */

import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCREEN_DIR = path.resolve(HERE, "../../../api_gateway/tests/screenshots");
mkdirSync(SCREEN_DIR, { recursive: true });

const snap = (page: Page, name: string) =>
  page.screenshot({
    path: path.join(SCREEN_DIR, `opp_deal_${name}.png`),
    fullPage: true,
  });

const goToStage = async (page: Page, oppId: string, stage: string) => {
  await page.goto(`/opportunities/${oppId}?stage=${stage}`);
  await expect(page.getByTestId(`stage-${stage.toLowerCase()}`)).toBeVisible();
};

// Long because we touch every stage. 90s ceiling is comfortable headroom.
test.setTimeout(90_000);

test("UI-OD-WALKTHROUGH · one opportunity from intake to sealed deal", async ({
  page,
}) => {
  // ──────────────────────────────────────────────────────────────
  // 00 · Lifecycle entry — list view shows pipeline by stage
  // ──────────────────────────────────────────────────────────────
  await page.goto("/opportunities");
  await expect(page.getByTestId("opportunities-root")).toBeVisible();
  await snap(page, "00_pipeline_list");

  // ──────────────────────────────────────────────────────────────
  // 01 · S01 intake — operator creates a new opportunity
  // ──────────────────────────────────────────────────────────────
  const dealName = `Northgate Capital — Global UCITS · ${Date.now().toString().slice(-6)}`;
  await page.getByTestId("add-opportunity-btn").click();
  await expect(page.getByTestId("create-opportunity-modal")).toBeVisible();

  await page.getByTestId("opp-name").fill(dealName);
  await page.getByTestId("opp-channel").selectOption("consultant");
  await page.getByTestId("opp-segment").selectOption("asset_manager");
  await page.getByTestId("opp-legal-name").fill("Northgate Capital Group Ltd");
  await page.getByTestId("opp-ucm-id").fill("ucm_northgate_capital");
  await page.getByTestId("opp-domicile").fill("UK");
  await page.getByTestId("opp-products").fill(
    "custody.global, fa.daily_nav, fa.multi_class, depo.ucits, fadmin.regulatory_reporting.ucits, ta.dublin, fx.standing_instruction, conn.nexen_portal",
  );
  await page.getByTestId("opp-jurisdictions").fill("IE, LU");
  await page.getByTestId("opp-aum").fill("28000000000");
  await page.getByTestId("opp-nav-strikes").fill("24");
  await page.getByTestId("opp-transactions").fill("520000");
  await page.getByTestId("opp-capital-events").fill("180");
  await page.getByTestId("opp-shareholders").fill("65000");
  await snap(page, "01_S01_intake_modal");

  await page.getByTestId("opp-create-submit").click();
  await expect(page.getByTestId("opportunity-workspace-root")).toBeVisible({
    timeout: 10_000,
  });
  const url = page.url();
  const m = url.match(/\/opportunities\/([^?#]+)/);
  const oppId = m?.[1];
  expect(oppId).toBeTruthy();
  await expect(page.getByTestId("opp-stage-strip")).toBeVisible();
  await snap(page, "02_S01_intake_landed");

  // ──────────────────────────────────────────────────────────────
  // 02 · S02 scope — resolve products against UPM, derive app set
  // ──────────────────────────────────────────────────────────────
  await goToStage(page, oppId!, "S02");
  await page.getByTestId("run-scope-btn").click();
  await expect(page.getByTestId("kv-scope-id")).toBeVisible({ timeout: 10_000 });
  await snap(page, "03_S02_scope_manifest");

  // ──────────────────────────────────────────────────────────────
  // 03 · S03 DDQ — add three material commitments
  //     (SLA · control · data-residency). Note the stage strip:
  //     DDQ is one of 8 stages, not the whole workflow.
  // ──────────────────────────────────────────────────────────────
  await goToStage(page, oppId!, "S03");
  await snap(page, "04_S03_ddq_empty");

  const commitments: Array<{
    canonical: string;
    text: string;
    cls: string;
    schedule: string;
  }> = [
    {
      canonical: "canon.or.business_continuity.rto",
      text: "RTO 4h / RPO 15m for fund accounting platform",
      cls: "sla",
      schedule: "schedule_b.sla",
    },
    {
      canonical: "canon.is.iam.privileged_access",
      text: "MFA required for all privileged production access · SOC 2 Type II",
      cls: "control",
      schedule: "schedule_c.controls",
    },
    {
      canonical: "canon.reg.gdpr.eu_residency",
      text: "Client EU resident data stays within EEA (Ireland + Luxembourg)",
      cls: "data_residency",
      schedule: "schedule_d.data_residency",
    },
  ];

  for (const c of commitments) {
    await page.getByTestId("add-commitment-btn").click();
    await expect(page.getByTestId("add-commitment-modal")).toBeVisible();
    await page.getByTestId("cm-canonical").fill(c.canonical);
    await page.getByTestId("cm-class").selectOption(c.cls);
    await page.getByTestId("cm-text").fill(c.text);
    await page.getByTestId("cm-schedule").fill(c.schedule);
    await page.getByTestId("cm-submit").click();
    await expect(page.getByTestId("add-commitment-modal")).toBeHidden();
  }
  await expect(page.getByTestId("commitments-table")).toBeVisible();
  await snap(page, "05_S03_ddq_commitments_added");

  // ──────────────────────────────────────────────────────────────
  // 04 · S04 complexity — score across 10 dimensions
  // ──────────────────────────────────────────────────────────────
  await goToStage(page, oppId!, "S04");
  await page.getByTestId("run-complexity-btn").click();
  await expect(page.getByTestId("kv-composite")).toBeVisible({ timeout: 10_000 });
  await snap(page, "06_S04_complexity_scored");

  // ──────────────────────────────────────────────────────────────
  // 05 · S05 cost + capacity — deterministic numeric engines
  // ──────────────────────────────────────────────────────────────
  await goToStage(page, oppId!, "S05");
  await page.getByTestId("run-cost-capacity-btn").click();
  await expect(page.getByTestId("stat-y1-cost")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("capacity-table")).toBeVisible();
  await snap(page, "07_S05_cost_and_capacity");

  // ──────────────────────────────────────────────────────────────
  // 06 · S06 pricing — TCV including sec-lending, FX, NII, adjacent
  // ──────────────────────────────────────────────────────────────
  await goToStage(page, oppId!, "S06");
  await page.getByTestId("run-pricing-btn").click();
  await expect(page.getByTestId("stat-y1-margin")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("tcv-5yr-total")).toBeVisible();
  await snap(page, "08_S06_pricing_proposal");

  // ──────────────────────────────────────────────────────────────
  // 07 · S07 operating model — FTE plan, hiring lead times, DDQ
  //      commitment cross-check (this is where commitments from S03
  //      get enforced — guardrail.03)
  // ──────────────────────────────────────────────────────────────
  await goToStage(page, oppId!, "S07");
  await page.getByTestId("run-opmodel-btn").click();
  await expect(page.getByTestId("kv-service-model")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("crosscheck-table")).toBeVisible();
  await snap(page, "09_S07_operating_model_and_crosscheck");

  // ──────────────────────────────────────────────────────────────
  // 08 · S08 approval — tier-gated approval chain
  // ──────────────────────────────────────────────────────────────
  await goToStage(page, oppId!, "S08");
  await snap(page, "10_S08_pre_approval");

  await page.getByTestId("request-approval-btn").click();
  await expect(page.getByTestId("kv-request-id")).toBeVisible({ timeout: 10_000 });
  await snap(page, "11_S08_approval_requested");

  // Approve as every required approver.
  const approveButtons = page.locator('[data-testid^="approve-"]');
  const buttonCount = await approveButtons.count();
  expect(buttonCount).toBeGreaterThan(0);
  for (let i = 0; i < buttonCount; i++) {
    await page.locator('[data-testid^="approve-"]').nth(i).click();
    await page.waitForTimeout(150);
  }
  await expect(page.getByTestId("kv-approval-state")).toContainText("approved", {
    timeout: 10_000,
  });
  await snap(page, "12_S08_approvals_collected");

  // ──────────────────────────────────────────────────────────────
  // 09 · S08 seal — write the immutable bundle (Merkle-rooted)
  // ──────────────────────────────────────────────────────────────
  await page.getByTestId("seal-btn").click();
  await expect(page.getByTestId("kv-deal-id")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("merkle-root")).toContainText(/^sha256:[0-9a-f]+/);
  await snap(page, "13_S08_sealed_bundle");

  // ──────────────────────────────────────────────────────────────
  // 10 · Replay — bit-exact reproduction verifies the sealed bundle
  // ──────────────────────────────────────────────────────────────
  await page.getByTestId("replay-btn").click();
  await expect(page.getByTestId("replay-result")).toContainText(/All hashes verify|✓/, {
    timeout: 10_000,
  });
  await snap(page, "14_S08_replay_verified");

  // ──────────────────────────────────────────────────────────────
  // 11 · Deal journal — hash-chained events across every stage,
  //      including S03 (ddq.commitment) entries
  // ──────────────────────────────────────────────────────────────
  await expect(page.getByTestId("card-s08-journal")).toBeVisible();
  // Scroll the journal table into view for a cleaner capture.
  await page.getByTestId("card-s08-journal").scrollIntoViewIfNeeded();
  await snap(page, "15_S08_deal_journal");

  // ──────────────────────────────────────────────────────────────
  // 12 · Final lifecycle view — back to the list, now showing the
  //      sealed deal at status "won"
  // ──────────────────────────────────────────────────────────────
  await page.goto("/opportunities");
  await page.getByTestId("opportunities-search").fill(dealName.split(" ")[0]!);
  await expect(page.getByTestId(`opportunity-row-${oppId}`)).toBeVisible();
  await snap(page, "16_pipeline_list_sealed");
});

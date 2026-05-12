/**
 * Rule engine — end-to-end suite + screenshot capture.
 *
 * Run with:
 *   npx playwright test --config=playwright.rules.config.ts
 *
 * Prerequisites:
 *   - API gateway live on http://127.0.0.1:8001 in fs-mode
 *   - Vite started by Playwright with VITE_API_MODE=http
 *
 * Screenshots land in docs/evidence/rule-engine/screenshots/.
 * The suite covers:
 *   - UI-RE-LIST     /rules renders the seeded rule set
 *   - UI-RE-CREATE   create a draft via the modal
 *   - UI-RE-DETAIL   detail view renders status + when/then JSON
 *   - UI-RE-EDIT     edit modal bumps version + values
 *   - UI-RE-SUBMIT   submit moves rule to pending_review
 *   - UI-RE-QUEUE    /rules/queue shows the pending rule
 *   - UI-RE-APPROVE  approve flips status to active
 *   - UI-RE-EVAL     live evaluation panel confirms the rule drives the engine
 *   - UI-RE-A11Y     axe scan: no serious/critical violations on /rules + /queue
 */

import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCREEN_DIR = path.resolve(HERE, "../../../../docs/evidence/rule-engine/screenshots");
mkdirSync(SCREEN_DIR, { recursive: true });

const snap = (page: Page, name: string) =>
  page.screenshot({
    path: path.join(SCREEN_DIR, `${name}.png`),
    fullPage: true,
  });

// Unique per run so successive Playwright invocations don't collide.
const uniq = () => Math.random().toString(36).slice(2, 7);
const RULE_ID = `test.freshness.e2e_${uniq()}`;

// ════════════════════════════════════════════════════════════════════
// UI-RE-LIST · /rules shows the seeded rules
// ════════════════════════════════════════════════════════════════════

test("UI-RE-LIST · /rules renders the seeded rule set", async ({ page }) => {
  await page.goto("/rules");
  await expect(page.getByTestId("rules-list-root")).toBeVisible();
  await expect(page.getByTestId("rules-table")).toBeVisible();
  // At least the 11 bootstrap rules should be visible.
  await expect(page.locator('[data-testid^="rule-row-"]')).toHaveCount(11, { timeout: 5_000 });
  await snap(page, "rules_01_index");
});

// ════════════════════════════════════════════════════════════════════
// UI-RE-CREATE · create a new draft rule
// ════════════════════════════════════════════════════════════════════

test("UI-RE-CREATE · create a freshness rule and land on its detail page", async ({ page }) => {
  await page.goto("/rules");
  await page.getByTestId("create-rule-btn").click();
  await expect(page.getByTestId("rule-create-modal")).toBeVisible();

  // Fill structured form fields
  await page.getByTestId("rc-id").fill(RULE_ID);
  await page.getByTestId("rc-engine").selectOption("freshness");
  await page.getByTestId("rc-title").fill("E2E confidential gate");
  await page.getByTestId("rc-description").fill("Flag library entries tagged 'confidential' until SME reviews.");
  await page.getByTestId("rc-priority").fill("75");
  await page.getByTestId("rc-tags").fill("e2e, test");
  await page.getByTestId("rc-when-field").fill("library_entry.tags");
  await page.getByTestId("rc-when-op").selectOption("contains");
  await page.getByTestId("rc-when-value").fill('"confidential"');
  await page.getByTestId("rc-then-reason").fill("entry {library_entry.id} is confidential — needs SME review");

  await snap(page, "rules_02_create_modal");

  await page.getByTestId("rule-create-submit").click();
  await expect(page.getByTestId("rule-create-modal")).toBeHidden();

  // The new rule should appear in the table
  await page.getByTestId("rules-search").fill(RULE_ID);
  await expect(page.getByTestId(`rule-row-${RULE_ID}`)).toBeVisible();
});

// ════════════════════════════════════════════════════════════════════
// UI-RE-DETAIL · status=draft, when/then visible
// ════════════════════════════════════════════════════════════════════

test("UI-RE-DETAIL · detail page shows draft status + when/then JSON", async ({ page }) => {
  await page.goto(`/rules/${RULE_ID}`);
  await expect(page.getByTestId("rule-detail-root")).toBeVisible();
  await expect(page.getByTestId("rule-status-badge")).toContainText("Draft");
  await expect(page.getByTestId("detail-rule-id")).toContainText(RULE_ID);
  await expect(page.getByTestId("detail-priority")).toContainText("75");
  await expect(page.getByTestId("detail-version")).toContainText("1.0.0");
  await expect(page.getByTestId("detail-when")).toContainText("library_entry.tags");
  await expect(page.getByTestId("detail-then")).toContainText("confidential");

  await snap(page, "rules_03_detail_draft");
});

// ════════════════════════════════════════════════════════════════════
// UI-RE-EDIT · edit the priority + bump version
// ════════════════════════════════════════════════════════════════════

test("UI-RE-EDIT · edit modal saves a new value and bumps version", async ({ page }) => {
  await page.goto(`/rules/${RULE_ID}`);
  await expect(page.getByTestId("rule-detail-root")).toBeVisible();

  await page.getByTestId("edit-rule-btn").click();
  await expect(page.getByTestId("rule-edit-modal")).toBeVisible();
  await page.getByTestId("re-priority").fill("25");
  await page.getByTestId("re-title").fill("E2E confidential gate (priority bumped)");

  await snap(page, "rules_04_edit_modal");

  await page.getByTestId("rule-edit-submit").click();
  await expect(page.getByTestId("rule-edit-modal")).toBeHidden();
  await expect(page.getByTestId("detail-priority")).toContainText("25");
  await expect(page.getByTestId("detail-version")).toContainText("1.1.0");

  await snap(page, "rules_05_detail_after_edit");
});

// ════════════════════════════════════════════════════════════════════
// UI-RE-SUBMIT · submit moves to pending_review
// ════════════════════════════════════════════════════════════════════

test("UI-RE-SUBMIT · submit for review flips status to pending", async ({ page }) => {
  await page.goto(`/rules/${RULE_ID}`);
  await page.getByTestId("submit-rule-btn").click();
  await expect(page.getByTestId("submit-modal")).toBeVisible();
  await page.getByTestId("submit-name").fill("alice.e2e");
  await page.getByTestId("submit-confirm").click();
  await expect(page.getByTestId("submit-modal")).toBeHidden();
  await expect(page.getByTestId("rule-status-badge")).toContainText("Pending review");

  await snap(page, "rules_06_submit_pending");
});

// ════════════════════════════════════════════════════════════════════
// UI-RE-QUEUE · the rule appears in the SME review queue
// ════════════════════════════════════════════════════════════════════

test("UI-RE-QUEUE · /rules/queue surfaces the pending rule", async ({ page }) => {
  await page.goto("/rules/queue");
  await expect(page.getByTestId("rule-queue-root")).toBeVisible();
  await expect(page.getByTestId(`queue-row-${RULE_ID}`)).toBeVisible();

  await snap(page, "rules_07_queue_view");
});

// ════════════════════════════════════════════════════════════════════
// UI-RE-APPROVE · approval flips status to active
// ════════════════════════════════════════════════════════════════════

test("UI-RE-APPROVE · approve modal records SME decision + flips to active", async ({ page }) => {
  await page.goto(`/rules/${RULE_ID}`);
  await page.getByTestId("approve-rule-btn").click();
  await expect(page.getByTestId("approve-modal")).toBeVisible();
  await page.getByTestId("approve-approver").fill("bob.sme");
  await page.getByTestId("approve-rationale").fill("Confidential-tag policy aligns with §L04 review cadence; activating.");

  await snap(page, "rules_08_approve_modal");

  await page.getByTestId("approve-submit").click();
  await expect(page.getByTestId("approve-modal")).toBeHidden();
  await expect(page.getByTestId("rule-status-badge")).toContainText("Active");
  await expect(page.getByTestId("detail-approved-by")).toContainText("bob.sme");

  await snap(page, "rules_09_detail_active");
});

// ════════════════════════════════════════════════════════════════════
// UI-RE-EVAL · live evaluation panel proves the rule drives the engine
// ════════════════════════════════════════════════════════════════════

test("UI-RE-EVAL · live evaluation panel fires the active rule", async ({ page }) => {
  await page.goto(`/rules/${RULE_ID}`);
  // Replace the default sample input with one that matches our confidential rule.
  const sample = JSON.stringify({
    library_entry: { id: "lib_demo", tags: ["confidential", "ops"] },
    evidence: [],
  }, null, 2);
  const input = page.getByTestId("eval-input");
  await input.click();
  await input.fill(sample);
  await page.getByTestId("eval-run").click();
  await expect(page.getByTestId("eval-result")).toBeVisible();
  await expect(page.getByTestId("eval-result")).toContainText("Rule fired", { timeout: 5_000 });
  await expect(page.getByTestId("eval-verdict")).toContainText("confidential");

  await snap(page, "rules_10_engine_proof");
});

// ════════════════════════════════════════════════════════════════════
// UI-RE-A11Y · axe scan
// ════════════════════════════════════════════════════════════════════

test("UI-RE-A11Y · /rules has no serious/critical accessibility violations", async ({ page }) => {
  await page.goto("/rules");
  await page.getByTestId("rules-list-root").waitFor();
  const results = await new AxeBuilder({ page })
    .include('[data-testid="rules-list-root"]')
    .withTags(["wcag2a", "wcag2aa"])
    .disableRules(["color-contrast"])
    .analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

test("UI-RE-A11Y · /rules/queue has no serious/critical accessibility violations", async ({ page }) => {
  await page.goto("/rules/queue");
  await page.getByTestId("rule-queue-root").waitFor();
  const results = await new AxeBuilder({ page })
    .include('[data-testid="rule-queue-root"]')
    .withTags(["wcag2a", "wcag2aa"])
    .disableRules(["color-contrast"])
    .analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

// ════════════════════════════════════════════════════════════════════
// Cleanup — leave the data/manifests/rules/ directory in its bootstrap
// state for subsequent test runs.
// ════════════════════════════════════════════════════════════════════

test.afterAll(async ({ request }) => {
  await request.delete(`http://127.0.0.1:8001/api/v1/rules/${encodeURIComponent(RULE_ID)}?force=true`);
});

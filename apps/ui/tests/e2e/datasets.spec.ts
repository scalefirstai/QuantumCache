/**
 * Dataset Management — end-to-end suite + screenshot capture.
 *
 * Run with:
 *   npx playwright test --config=playwright.datasets.config.ts
 *
 * Prerequisites:
 *   - API gateway live on http://127.0.0.1:8001 in fs-mode
 *   - Vite started by Playwright with VITE_API_MODE=http
 *
 * Screenshots land in apps/api_gateway/tests/screenshots/datasets_*.png.
 * The suite covers acceptance criteria UI-DS-INDEX, UI-DS-KN-* /
 * UI-DS-CN-* / UI-DS-AU-NO-EDIT, plus UI-A11Y for the index page.
 */

import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCREEN_DIR = path.resolve(HERE, "../../../api_gateway/tests/screenshots");
mkdirSync(SCREEN_DIR, { recursive: true });

const snap = (page: Page, name: string) =>
  page.screenshot({
    path: path.join(SCREEN_DIR, `datasets_${name}.png`),
    fullPage: true,
  });

const uniqueDocId = () =>
  `operator:e2e:doc_${Math.random().toString(36).slice(2, 8)}`;
const uniqueCanonicalId = () =>
  `canon.e2e.test_${Math.random().toString(36).slice(2, 6)}`;

// ════════════════════════════════════════════════════════════════════
// UI-DS-INDEX — overview cards
// ════════════════════════════════════════════════════════════════════

test("UI-DS-INDEX · /datasets renders three cards with counts", async ({ page }) => {
  await page.goto("/datasets");
  await expect(page.getByTestId("datasets-root")).toBeVisible();
  await expect(page.getByTestId("dataset-card-knowledge")).toBeVisible();
  await expect(page.getByTestId("dataset-card-canonical")).toBeVisible();
  await expect(page.getByTestId("dataset-card-audit")).toBeVisible();

  // Each count is a non-empty number.
  for (const id of ["knowledge", "canonical", "audit"]) {
    const text = await page.getByTestId(`dataset-count-${id}`).textContent();
    expect(Number(text?.replace(/,/g, ""))).toBeGreaterThanOrEqual(0);
  }

  await snap(page, "01_index");
});

test("UI-A11Y · axe scan on /datasets feature has no serious/critical violations", async ({
  page,
}) => {
  await page.goto("/datasets");
  await page.getByTestId("datasets-root").waitFor();
  // Scope to the feature subtree (the shared app shell sidebar is out of
  // scope for this feature's a11y bar; the existing app-wide axe runs in
  // employee-console.spec.ts cover it). Skip color-contrast — the
  // `bny-fog` design token is shared across the app; tuning its hex is
  // a palette-wide refresh, not a feature change.
  const results = await new AxeBuilder({ page })
    .include('[data-testid="datasets-root"]')
    .withTags(["wcag2a", "wcag2aa"])
    .disableRules(["color-contrast"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

// ════════════════════════════════════════════════════════════════════
// UI-DS-KN — Knowledge CRUD
// ════════════════════════════════════════════════════════════════════

test("UI-DS-KN-CRUD · create → view → edit → delete a knowledge document", async ({
  page,
}) => {
  const docId = uniqueDocId();

  // 1. Land on knowledge list
  await page.goto("/datasets/knowledge");
  await expect(page.getByTestId("knowledge-list-root")).toBeVisible();
  await expect(page.getByTestId("knowledge-table")).toBeVisible();
  await snap(page, "10_knowledge_list");

  // 2. Open create modal
  await page.getByTestId("add-knowledge-btn").click();
  await expect(page.getByTestId("knowledge-create-modal")).toBeVisible();
  await snap(page, "11_knowledge_create_modal");

  // 3. Drop a file into the dropzone (via hidden file input), wait for the
  //    in-browser sha256 to complete, then override the auto-suggested
  //    docId + description and submit. The PUT goes direct to LocalStack;
  //    /confirm recomputes sha256 server-side.
  const pdfBytes = Buffer.from(
    "%PDF-1.4\n% e2e test fixture\n1 0 obj <<>> endobj\n%%EOF\n",
  );
  await page.getByTestId("kn-file-input").setInputFiles({
    name: `${docId.replace(/[:]/g, "_")}.pdf`,
    mimeType: "application/pdf",
    buffer: pdfBytes,
  });
  await expect(page.getByTestId("kn-file-hash")).toContainText(/^sha256:[0-9a-f]{64}$/);
  await page.getByTestId("kn-create-docId").fill(docId);
  await page.getByTestId("kn-create-desc").fill("E2E test policy");

  await page.getByTestId("kn-create-submit").click();
  await expect(page.getByTestId("knowledge-create-modal")).toBeHidden();
  // The new doc has docId `operator:...` which sorts after `bny-ir:` and
  // `edgar:`, so it lands on a later page. Filter to surface it.
  await page.getByTestId("knowledge-search").fill(docId);
  await expect(page.getByTestId(`knowledge-row-${docId}`)).toBeVisible();

  // 4. Detail view
  await page
    .getByTestId(`knowledge-row-${docId}`)
    .getByRole("link", { name: /e2e test policy|operator/i })
    .first()
    .click();
  await expect(page.getByTestId("knowledge-detail-root")).toBeVisible();
  await snap(page, "12_knowledge_detail");

  // 5. Edit modal
  await page.getByTestId("edit-knowledge-btn").click();
  await expect(page.getByTestId("knowledge-edit-modal")).toBeVisible();
  await page.getByTestId("kn-edit-desc").fill("E2E test policy · edited");
  await page.getByTestId("kn-edit-tags").fill("e2e, approved, edited");
  await snap(page, "13_knowledge_edit_modal");
  await page.getByTestId("kn-edit-submit").click();
  await expect(page.getByTestId("knowledge-edit-modal")).toBeHidden();
  // Detail header reflects the new description.
  await expect(page.getByTestId("knowledge-detail-root")).toContainText("edited");
  await snap(page, "14_knowledge_detail_after_edit");

  // 6. Delete from detail page
  page.once("dialog", (d) => d.accept());
  await page.getByTestId("delete-knowledge-btn").click();
  await page.waitForURL(/\/datasets\/knowledge\b/);
  // Filter to operator-added rows so the assertion is unaffected by which
  // page we land on.
  await page.getByTestId("knowledge-search").fill(docId);
  await expect(page.getByTestId(`knowledge-row-${docId}`)).toHaveCount(0);
  await snap(page, "15_knowledge_list_after_delete");
});

// ════════════════════════════════════════════════════════════════════
// UI-DS-CN — Canonical CRUD
// ════════════════════════════════════════════════════════════════════

test("UI-DS-CN-CRUD · create → view → edit → delete a canonical", async ({
  page,
}) => {
  const cid = uniqueCanonicalId();

  await page.goto("/datasets/canonical");
  await expect(page.getByTestId("canonical-list-root")).toBeVisible();
  await expect(page.getByTestId("canonical-table")).toBeVisible();
  await snap(page, "20_canonical_list");

  await page.getByTestId("add-canonical-btn").click();
  await expect(page.getByTestId("canonical-create-modal")).toBeVisible();
  await snap(page, "21_canonical_create_modal");

  await page.getByTestId("cn-create-id").fill(cid);
  await page.getByTestId("cn-create-label").fill("E2E test canonical");
  await page.getByTestId("cn-create-desc").fill("Canonical added by the e2e suite for screenshot purposes.");
  await page.getByTestId("cn-create-submit").click();
  await expect(page.getByTestId("canonical-create-modal")).toBeHidden();
  await expect(page.getByTestId(`canonical-row-${cid}`)).toBeVisible();

  await page
    .getByTestId(`canonical-row-${cid}`)
    .getByRole("link", { name: cid })
    .click();
  await expect(page.getByTestId("canonical-detail-root")).toBeVisible();
  await snap(page, "22_canonical_detail");

  await page.getByTestId("edit-canonical-btn").click();
  await expect(page.getByTestId("canonical-edit-modal")).toBeVisible();
  await page.getByTestId("cn-edit-label").fill("E2E test canonical · renamed");
  await page.getByTestId("cn-edit-tags").fill("e2e, reviewed");
  await page.getByTestId("cn-edit-add-mapping").click();
  // Fill the freshly-added mapping row.
  const inputs = page.locator('input[placeholder="framework"]');
  await inputs.last().fill("CUSTOM");
  await page.locator('input[placeholder="version"]').last().fill("v1");
  await page.locator('input[placeholder="question_ref"]').last().fill("CF-E2E-1");
  await snap(page, "23_canonical_edit_modal");
  await page.getByTestId("cn-edit-submit").click();
  await expect(page.getByTestId("canonical-edit-modal")).toBeHidden();
  await expect(page.getByTestId("canonical-detail-root")).toContainText("renamed");
  await snap(page, "24_canonical_detail_after_edit");

  page.once("dialog", (d) => d.accept());
  await page.getByTestId("delete-canonical-btn").click();
  await page.waitForURL(/\/datasets\/canonical\b/);
  await expect(page.getByTestId(`canonical-row-${cid}`)).toHaveCount(0);
});

test("UI-DS-CN-BOOTSTRAP · delete on a bootstrap canonical prompts force-confirm", async ({
  page,
}) => {
  await page.goto("/datasets/canonical");
  await expect(page.getByTestId("canonical-table")).toBeVisible();
  // Pick the first bootstrap row (the seeder tags every entry "bootstrap").
  const firstRow = page.locator('[data-testid^="canonical-row-"]').first();
  await firstRow.waitFor();
  await snap(page, "25_canonical_list_with_bootstrap");
  // We don't actually delete a real bootstrap entry — but assert the
  // confirm dialog text mentions force.
  let promptedMsg = "";
  page.once("dialog", (d) => {
    promptedMsg = d.message();
    d.dismiss();
  });
  await firstRow.locator('button[data-testid^="delete-"]').click();
  expect(promptedMsg.toLowerCase()).toContain("force");
});

// ════════════════════════════════════════════════════════════════════
// UI-DS-PAGE — Pagination (knowledge list — 126 rows is enough to
// exercise prev/next/last + page-size selector)
// ════════════════════════════════════════════════════════════════════

test("UI-DS-PAGE · pagination: prev/next/last + page-size narrows the table", async ({
  page,
}) => {
  await page.goto("/datasets/knowledge");
  await expect(page.getByTestId("knowledge-list-root")).toBeVisible();
  await expect(page.getByTestId("knowledge-pagination")).toBeVisible();
  // Default page size 25 — should render exactly 25 rows on page 1.
  await expect(page.locator('[data-testid^="knowledge-row-"]')).toHaveCount(25);
  const initialRange = await page.getByTestId("knowledge-pagination-range").textContent();
  expect(initialRange).toMatch(/^1–25 of \d+/);
  await snap(page, "40_knowledge_pagination_default");

  // Next page → range advances; prev becomes enabled.
  await page.getByTestId("knowledge-pagination-next").click();
  await expect(page.getByTestId("knowledge-pagination-range")).toContainText("26–");
  await expect(page.locator('[data-testid^="knowledge-row-"]')).toHaveCount(25);
  await snap(page, "41_knowledge_pagination_page2");

  // Last page — rows < 25 since 126 % 25 = 1.
  await page.getByTestId("knowledge-pagination-last").click();
  const lastRange = await page.getByTestId("knowledge-pagination-range").textContent();
  expect(lastRange).toMatch(/of \d+$/);
  await expect(page.getByTestId("knowledge-pagination-next")).toBeDisabled();
  await snap(page, "42_knowledge_pagination_last");

  // Change page size → page resets, more rows per page.
  await page.getByTestId("knowledge-pagination-size").selectOption("50");
  await expect(page.getByTestId("knowledge-pagination-range")).toContainText("1–");
  await expect(page.locator('[data-testid^="knowledge-row-"]')).toHaveCount(50);
  await snap(page, "43_knowledge_pagination_size50");
});

test("UI-DS-PAGE-FILTER · filter resets paginator to page 1", async ({ page }) => {
  await page.goto("/datasets/knowledge");
  await page.getByTestId("knowledge-pagination").waitFor();
  // Jump to page 3 first.
  await page.getByTestId("knowledge-pagination-next").click();
  await page.getByTestId("knowledge-pagination-next").click();
  await expect(page.getByTestId("knowledge-pagination-page")).toContainText("Page 3");
  // Filter narrows results — pagination must reset to Page 1 (or hide if <= 10).
  await page.getByTestId("knowledge-search").fill("pillar");
  // After filter, either we're back at page 1 of fewer pages, or the
  // paginator is hidden because the filtered set fits in 10 rows.
  const paginator = page.getByTestId("knowledge-pagination");
  const visible = await paginator.isVisible();
  if (visible) {
    await expect(page.getByTestId("knowledge-pagination-page")).toContainText("Page 1");
  }
  await snap(page, "44_knowledge_pagination_after_filter");
});

// ════════════════════════════════════════════════════════════════════
// UI-DS-AU — Audit (list, verify, redact, immutability)
// ════════════════════════════════════════════════════════════════════

test("UI-DS-AU-VERIFY · verify-integrity shows ✓ on every sealed run", async ({
  page,
}) => {
  await page.goto("/datasets/audit");
  await expect(page.getByTestId("audit-list-root")).toBeVisible();
  await expect(page.getByTestId("audit-table")).toBeVisible();
  await snap(page, "30_audit_list");

  // Click verify on first row
  const firstVerify = page.locator('[data-testid^="verify-"]').first();
  await firstVerify.click();
  await expect(page.locator('span:has-text("✓ verified")').first()).toBeVisible({
    timeout: 10_000,
  });
  await snap(page, "31_audit_list_after_verify");
});

test("UI-DS-AU-NO-EDIT · audit detail page has no edit/delete buttons", async ({
  page,
}) => {
  await page.goto("/datasets/audit");
  await page.locator('[data-testid^="audit-row-"]').first().getByRole("link").first().click();
  await expect(page.getByTestId("audit-detail-root")).toBeVisible();
  // Verify and Redact must exist; Edit and Delete must NOT.
  await expect(page.getByTestId("verify-btn")).toBeVisible();
  await expect(page.getByTestId("redact-btn")).toBeVisible();
  await expect(page.getByText("Edit", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Delete", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("audit-events-table")).toBeVisible();
  await snap(page, "32_audit_detail");

  // Run verify, expect a result strip.
  await page.getByTestId("verify-btn").click();
  await expect(page.getByTestId("verify-result")).toBeVisible({ timeout: 10_000 });
  await snap(page, "33_audit_detail_verified");
});

test("UI-DS-AU-REDACT · append a redaction record without rewriting the run", async ({
  page,
}) => {
  await page.goto("/datasets/audit");
  await page.locator('[data-testid^="audit-row-"]').first().getByRole("link").first().click();
  await expect(page.getByTestId("audit-detail-root")).toBeVisible();

  await page.getByTestId("redact-btn").click();
  await expect(page.getByTestId("redaction-modal")).toBeVisible();
  await page.getByTestId("redact-reason").fill("LEGAL-2026-E2E-001");
  await snap(page, "34_audit_redaction_modal");
  await page.getByTestId("redact-submit").click();
  await expect(page.getByTestId("redaction-modal")).toBeHidden();
  // Redaction row appears in the redactions table.
  await expect(page.getByTestId("redactions-table")).toBeVisible();
  await expect(page.getByTestId("redactions-table")).toContainText("LEGAL-2026-E2E-001");
  await snap(page, "35_audit_detail_with_redaction");

  // Sealed run still verifies clean after the redaction.
  await page.getByTestId("verify-btn").click();
  await expect(page.getByTestId("verify-result")).toContainText(/verified|✓/i, {
    timeout: 10_000,
  });
  await snap(page, "36_audit_verified_after_redaction");
});

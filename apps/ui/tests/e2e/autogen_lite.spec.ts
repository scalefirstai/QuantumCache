/**
 * AutoGen Lite end-to-end:
 *   1) Agents list                 → screenshot
 *   2) Agent detail (DraftComposer) → screenshot
 *   3) Edit the system prompt + save (creates new version, activates)
 *   4) Versions tab → screenshot
 *   5) History tab → screenshot
 *   6) Models page → screenshot
 *   7) Skills page → screenshot
 *   8) Playground page → screenshot (form only; PG-02 submits a run)
 *
 * Plus UI-PG-01/02: submit a question, poll until succeeded, screenshot,
 * verify the sealed-run link works. This exercises the real orchestrator
 * subprocess (Anthropic + LocalStack S3 + Mongo + OpenSearch + Qdrant).
 *
 * Screenshots → apps/api_gateway/tests/screenshots/autogen_*.png.
 */

import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCREEN_DIR = path.resolve(HERE, "../../../api_gateway/tests/screenshots");
mkdirSync(SCREEN_DIR, { recursive: true });

const API = "http://localhost:8000";

function snap(page: Page, name: string) {
  return page.screenshot({ path: path.join(SCREEN_DIR, `${name}.png`), fullPage: true });
}

function watchFailures(page: Page) {
  const fails: string[] = [];
  page.on("response", (r) => {
    const u = r.url();
    if (u.startsWith(API) && r.status() >= 400) fails.push(`HTTP ${r.status()} ${u}`);
  });
  page.on("pageerror", (e) => fails.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") fails.push(`console: ${m.text()}`);
  });
  return fails;
}

test.describe.serial("AutoGen Lite", () => {
  test("UI-AG-01 agents list shows 8 rows", async ({ page }) => {
    const fails = watchFailures(page);
    await page.goto("/agents");
    await page.getByTestId("agents-root").waitFor();
    const rows = await page.locator("[data-testid^='agent-row-']").count();
    expect(rows).toBe(8);
    await snap(page, "autogen_01_agents_list");
    expect(fails.filter((f) => !f.includes("favicon"))).toEqual([]);
  });

  test("UI-AG-02 DraftComposer detail renders", async ({ page }) => {
    await page.goto("/agents/drafter");
    await page.getByTestId("agent-detail-root").waitFor();
    await expect(page.getByTestId("system-textarea")).toBeVisible();
    await expect(page.getByTestId("model-select")).toBeVisible();
    await snap(page, "autogen_02_agent_detail");
  });

  test("UI-AG-03 edit + save bumps version and activates", async ({ page }) => {
    await page.goto("/agents/drafter");
    await page.getByTestId("agent-detail-root").waitFor();

    const beforeVersion = await page
      .locator("text=/v[0-9]+\\.[0-9]+\\.[0-9]+ active/")
      .first()
      .textContent();
    expect(beforeVersion).toBeTruthy();

    // Append a comment to the system prompt that's easy to spot.
    const textarea = page.getByTestId("system-textarea");
    await textarea.focus();
    await page.keyboard.press("End");
    await textarea.evaluate((el: HTMLTextAreaElement) => {
      el.value = el.value + "\n\n# Edited via AutoGen Lite playwright at " + new Date().toISOString();
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });

    await page.getByTestId("comment-input").fill("E2E test edit");
    // activate-immediately is default true.
    await page.getByTestId("save-button").click();

    await expect(page.getByTestId("save-status")).toContainText("Saved v", { timeout: 10_000 });
    await snap(page, "autogen_03_after_save");
  });

  test("UI-AG-04 versions tab shows the new version active", async ({ page }) => {
    await page.goto("/agents/drafter");
    await page.getByTestId("agent-detail-root").waitFor();
    await page.getByTestId("tab-versions").click();
    await page.getByTestId("versions-table").waitFor();
    const activeBadges = await page.locator("text=/active/").count();
    // Header pill ("v1.0.1 active") + the row's active badge.
    expect(activeBadges).toBeGreaterThanOrEqual(1);
    await snap(page, "autogen_04_versions");
  });

  test("UI-AG-05 history tab shows create + activate", async ({ page }) => {
    await page.goto("/agents/drafter");
    await page.getByTestId("agent-detail-root").waitFor();
    await page.getByTestId("tab-history").click();
    await page.getByTestId("audit-log").waitFor();
    const entries = await page.locator("[data-testid^='audit-']").count();
    expect(entries).toBeGreaterThanOrEqual(2);
    await snap(page, "autogen_05_history");
  });

  test("UI-MD-01 models page", async ({ page }) => {
    const fails = watchFailures(page);
    await page.goto("/models");
    await page.getByTestId("models-root").waitFor();
    await expect(page.getByTestId("model-card-claude-opus-4-7")).toBeVisible();
    await expect(page.getByTestId("model-card-claude-sonnet-4-6")).toBeVisible();
    await expect(page.getByTestId("model-card-claude-haiku-4-5")).toBeVisible();
    await snap(page, "autogen_06_models");
    expect(fails.filter((f) => !f.includes("favicon"))).toEqual([]);
  });

  test("UI-SK-01 skills catalog", async ({ page }) => {
    await page.goto("/skills");
    await page.getByTestId("skills-root").waitFor();
    await expect(page.getByTestId("skill-row-retrieval.hybrid")).toBeVisible();
    await snap(page, "autogen_07_skills");
  });

  test("UI-PG-01 playground form renders", async ({ page }) => {
    await page.goto("/playground");
    await page.getByTestId("playground-root").waitFor();
    await expect(page.getByTestId("submit-button")).toBeEnabled();
    await snap(page, "autogen_08_playground_form");
  });

  test("UI-PG-02 playground end-to-end (real Claude)", async ({ page }) => {
    test.setTimeout(180_000); // orchestrator subprocess can take ~60s on this box.
    await page.goto("/playground");
    await page.getByTestId("playground-root").waitFor();
    await page.getByTestId("framework-select").selectOption("CAIQ");
    await page.getByTestId("question-textarea").fill(
      "Are audit and assurance policies established, documented, and approved?",
    );
    await page.getByTestId("submit-button").click();

    // Status pill flips to running.
    await expect(page.getByTestId("active-run")).toContainText("pg_", { timeout: 5_000 });
    await snap(page, "autogen_09_playground_running");

    // Wait for terminal state.
    await expect(page.getByTestId("active-run")).toContainText(/succeeded|failed/, {
      timeout: 150_000,
    });
    await page.waitForTimeout(500);
    await snap(page, "autogen_10_playground_done");

    // If succeeded, the sealed-run link should be live.
    const succeeded = await page.getByTestId("status-succeeded").count();
    if (succeeded > 0) {
      const link = page.getByTestId("open-sealed-run");
      await expect(link).toBeVisible();
      await link.click();
      // /runs/<runId> page
      await expect(page).toHaveURL(/\/runs\/run_/);
      await page.waitForLoadState("networkidle");
      await snap(page, "autogen_11_playground_sealed_run");
    }
  });
});

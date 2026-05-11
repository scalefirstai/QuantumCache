import { test, expect } from "@playwright/test";

test("pipeline view shows top stages and bottom data inspector", async ({ page }) => {
  await page.goto("http://localhost:5174/pipeline/ddq_8db64d9cb6c5");

  await expect(page.getByTestId("pipeline-view")).toBeVisible();
  await expect(page.getByTestId("pipeline-email-header")).toContainText("Acme Pension");

  // 5 questions in the picker
  const qButtons = page.getByTestId("pipeline-question-picker").locator("button");
  await expect(qButtons).toHaveCount(5);

  // 12 stages in the strip
  const stageButtons = page.getByTestId("pipeline-stage-strip").locator("button");
  await expect(stageButtons).toHaveCount(12);

  // Bottom inspector — defaults to intake
  const inspector = page.getByTestId("pipeline-data-inspector");
  await expect(inspector).toBeVisible();
  await expect(inspector).toContainText("Email intake");

  // Click DraftComposer stage
  await page.locator('[data-stage="drafter"]').click();
  await expect(inspector).toContainText("DraftComposer");
  // Q1 has a library hit + Opus draft, so we should see draft characters / citations
  await expect(inspector).toContainText("citations");

  // Switch to a halted question (Q5 adversarial)
  await page.locator('[data-question="Q5"]').click();
  // Adversarial question routes to halt → router stage should show halt
  await page.locator('[data-stage="router"]').click();
  await expect(inspector).toContainText("Routing decision");
});

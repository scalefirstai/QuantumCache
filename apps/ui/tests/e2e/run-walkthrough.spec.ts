import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe("Run walkthrough · /runs/run_01HQK4M9", () => {
  test("T-E2E2 stage walkthrough click-through updates URL each step", async ({
    page,
  }) => {
    await page.goto("/runs/run_01HQK4M9");
    await expect(page.getByTestId("run-walkthrough")).toBeVisible();

    const expected = [
      "intake",
      "classify",
      "retrieve",
      "draft",
      "validate",
      "approve",
      "respond",
    ];
    for (let i = 0; i < expected.length; i++) {
      const panel = page.getByRole("tabpanel");
      await expect(panel).toHaveAttribute("data-stage", expected[i]!);
      if (i < expected.length - 1) {
        await page.getByRole("button", { name: /Next/ }).click();
        await expect(page).toHaveURL(new RegExp(`stage=${expected[i + 1]}`));
      }
    }
  });

  test("T-E2E5 axe a11y scan finds no serious violations", async ({ page }) => {
    await page.goto("/runs/run_01HQK4M9");
    await page.getByTestId("run-walkthrough").waitFor();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  });
});

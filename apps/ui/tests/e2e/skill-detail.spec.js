import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("T-E2E4 skill detail renders pipeline SVG with all stage groups", async ({ page, }) => {
    await page.goto("/skills/retrieval-hybrid");
    await expect(page.getByTestId("skill-detail")).toBeVisible();
    const svg = page.getByTestId("pipeline-diagram");
    await expect(svg).toBeVisible();
    for (const id of [
        "query",
        "bm25",
        "dense",
        "merge",
        "filter",
        "rerank",
        "output",
    ]) {
        await expect(svg.locator(`[data-stage-id="${id}"]`)).toHaveCount(1);
    }
});
test("axe a11y scan on skill detail", async ({ page }) => {
    await page.goto("/skills/retrieval-hybrid");
    await page.getByTestId("skill-detail").waitFor();
    const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

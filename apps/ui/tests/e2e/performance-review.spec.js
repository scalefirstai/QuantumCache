import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("T-E2E3 performance review renders all three Chart.js canvases", async ({ page, }) => {
    await page.goto("/employees/aria/review/q1-2026");
    await expect(page.getByTestId("performance-review")).toBeVisible();
    await page.waitForLoadState("networkidle");
    const canvases = page.locator("canvas");
    await expect(canvases).toHaveCount(3);
    for (let i = 0; i < 3; i++) {
        const box = await canvases.nth(i).boundingBox();
        expect(box?.width ?? 0).toBeGreaterThan(0);
        expect(box?.height ?? 0).toBeGreaterThan(0);
    }
});
test("axe a11y scan on performance review", async ({ page }) => {
    await page.goto("/employees/aria/review/q1-2026");
    await page.getByTestId("performance-review").waitFor();
    const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

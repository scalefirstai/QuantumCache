import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("Employee console renders identity card, KPIs, agent roster, queue", async ({
  page,
}) => {
  await page.goto("/employees/aria");
  await expect(page.getByTestId("employee-console")).toBeVisible();
  await expect(page.getByTestId("kpi-strip")).toBeVisible();
  await expect(page.getByTestId("agent-roster")).toBeVisible();
  await expect(page.getByTestId("human-queue")).toBeVisible();
  await expect(page.getByTestId("question-timeline")).toBeVisible();
});

test("axe a11y scan on employee console", async ({ page }) => {
  await page.goto("/employees/aria");
  await page.getByTestId("employee-console").waitFor();
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

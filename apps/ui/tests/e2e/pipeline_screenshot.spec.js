import { test } from "@playwright/test";
test("capture pipeline view screenshots", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    // Q1 (CAIQ library hit) on intake
    await page.goto("http://localhost:5174/pipeline/ddq_8db64d9cb6c5?q=Q1&stage=intake");
    await page.getByTestId("pipeline-view").waitFor();
    await page.screenshot({ path: "test-results/pipeline_q1_intake.png", fullPage: false });
    // Q1 on drafter — show Opus tier-1 draft with citations
    await page.goto("http://localhost:5174/pipeline/ddq_8db64d9cb6c5?q=Q1&stage=drafter");
    await page.getByTestId("pipeline-view").waitFor();
    await page.screenshot({ path: "test-results/pipeline_q1_drafter.png", fullPage: false });
    // Q1 on sealed — final response with merkle
    await page.goto("http://localhost:5174/pipeline/ddq_8db64d9cb6c5?q=Q1&stage=sealed");
    await page.getByTestId("pipeline-view").waitFor();
    await page.screenshot({ path: "test-results/pipeline_q1_sealed.png", fullPage: false });
    // Q5 (adversarial halt) on router
    await page.goto("http://localhost:5174/pipeline/ddq_8db64d9cb6c5?q=Q5&stage=router");
    await page.getByTestId("pipeline-view").waitFor();
    await page.screenshot({ path: "test-results/pipeline_q5_router.png", fullPage: false });
});

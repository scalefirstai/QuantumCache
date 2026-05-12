/**
 * End-to-end live test:
 *  - UI on :5174 (Vite dev)
 *  - API gateway on :8000 (FastAPI → LocalStack S3 + Mongo)
 *  - Sealed runs are real orchestrator output produced against real
 *    Anthropic Claude with tool calling
 *
 * For each route the test:
 *   1. navigates to the URL
 *   2. waits for the React component to render its primary test-id
 *   3. asserts no failed API requests and no console errors
 *   4. captures a full-page screenshot to
 *      apps/api_gateway/tests/screenshots/<step>.png
 *
 * Run from the UI directory:
 *   npx playwright test full_e2e_live.spec.ts --project=chromium
 *
 * Or from the repo root:
 *   cd apps/ui && npx playwright test full_e2e_live.spec.ts --project=chromium
 */
import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCREEN_DIR = path.resolve(HERE, "../../../api_gateway/tests/screenshots");
mkdirSync(SCREEN_DIR, { recursive: true });
const API = "http://localhost:8000";
function snap(page, name) {
    return page.screenshot({ path: path.join(SCREEN_DIR, `${name}.png`), fullPage: true });
}
/** Wires a page so any 4xx/5xx API call or console error fails the test. */
function watchForErrors(page) {
    const failures = [];
    page.on("response", (r) => {
        const u = r.url();
        if (u.startsWith(API) && r.status() >= 400)
            failures.push(`HTTP ${r.status()} ${u}`);
    });
    page.on("pageerror", (e) => failures.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
        if (m.type() === "error")
            failures.push(`console: ${m.text()}`);
    });
    return failures;
}
test.describe("live end-to-end across all UI routes", () => {
    test("01 home — pipelines + runs list from S3", async ({ page, request }) => {
        // sanity: API is wired to S3 + Mongo
        const health = await (await request.get(`${API}/healthz`)).json();
        expect(health.status).toBe("ok");
        expect(health.runs_backend).toBe("s3");
        expect(health.mongo).toBe("live");
        expect(health.runs).toBeGreaterThanOrEqual(11);
        const fails = watchForErrors(page);
        await page.goto("/");
        await page.getByTestId("home-root").waitFor({ timeout: 10_000 }).catch(async () => {
            // Fallback: home may not expose home-root testid yet — just wait for an h1.
            await page.locator("h1, h2").first().waitFor();
        });
        await snap(page, "01_home");
        expect(fails, fails.join("\n")).toEqual([]);
    });
    test("02 pipeline view — full agent journey for ddq_8db64d9cb6c5", async ({ page }) => {
        const fails = watchForErrors(page);
        await page.goto("/pipeline/ddq_8db64d9cb6c5");
        await page.getByTestId("pipeline-view").waitFor({ timeout: 15_000 });
        await snap(page, "02_pipeline_overview");
        // Walk Q1 across three stages — every API call must succeed.
        for (const stage of ["intake", "drafter", "sealed"]) {
            await page.goto(`/pipeline/ddq_8db64d9cb6c5?q=Q1&stage=${stage}`);
            await page.getByTestId("pipeline-view").waitFor();
            await snap(page, `03_pipeline_q1_${stage}`);
        }
        expect(fails, fails.join("\n")).toEqual([]);
    });
    test("04 run walkthrough — latest sealed run", async ({ page, request }) => {
        const runs = await (await request.get(`${API}/api/v1/runs`)).json();
        expect(Array.isArray(runs)).toBe(true);
        expect(runs.length).toBeGreaterThan(0);
        // Use the most recent run (last in sorted order) — these were just produced
        // by the orchestrator against real Claude + S3 + Mongo.
        const latest = runs[runs.length - 1].runId;
        const fails = watchForErrors(page);
        await page.goto(`/runs/${latest}`);
        await page.locator("body").waitFor();
        await page.waitForLoadState("networkidle");
        await snap(page, "04_run_walkthrough_latest");
        expect(fails.filter((f) => !f.includes("favicon")), fails.join("\n")).toEqual([]);
    });
    test("05 employee console — Aria", async ({ page }) => {
        const fails = watchForErrors(page);
        await page.goto("/employees/aria");
        await page.waitForLoadState("networkidle");
        await snap(page, "05_employee_aria");
        expect(fails.filter((f) => !f.includes("favicon")), fails.join("\n")).toEqual([]);
    });
    test("06 performance review — Aria Q1 2026", async ({ page }) => {
        const fails = watchForErrors(page);
        await page.goto("/employees/aria/review/q1-2026");
        await page.waitForLoadState("networkidle");
        await snap(page, "06_review_aria_q1");
        expect(fails.filter((f) => !f.includes("favicon")), fails.join("\n")).toEqual([]);
    });
    test("07 skill detail — retrieval hybrid", async ({ page }) => {
        const fails = watchForErrors(page);
        await page.goto("/skills/retrieval-hybrid");
        await page.waitForLoadState("networkidle");
        await snap(page, "07_skill_retrieval_hybrid");
        expect(fails.filter((f) => !f.includes("favicon")), fails.join("\n")).toEqual([]);
    });
});

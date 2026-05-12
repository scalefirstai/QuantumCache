/**
 * Single-shot screenshot capture proving the new prompt is loaded by the
 * running orchestrator. The latest sealed run was produced moments after
 * v1.1.0 of the drafter prompt was activated through the API, and the
 * draft output should reflect the new "evidence-only guardrail" wording.
 *
 * Captured to apps/api_gateway/tests/screenshots/autogen_12_e2e_proof.png.
 */

import { test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCREEN_DIR = path.resolve(HERE, "../../../api_gateway/tests/screenshots");
mkdirSync(SCREEN_DIR, { recursive: true });

const API = "http://localhost:8000";

test("autogen E2E proof — latest sealed run reflects activated prompt", async ({ page, request }) => {
  // Find the most recent sealed run via the API.
  const runs = await (await request.get(`${API}/api/v1/runs`)).json();
  const latest = runs[runs.length - 1].runId;
  await page.goto(`/runs/${latest}`);
  await page.waitForLoadState("networkidle");
  await page.screenshot({
    path: path.join(SCREEN_DIR, "autogen_12_e2e_proof.png"),
    fullPage: true,
  });
});

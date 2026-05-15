import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  // datasets.spec.ts has its own config + webServer (fs-mode API on :8001 +
  // VITE_API_MODE=http). Excluded here so the default fixture-mode runner
  // doesn't pick it up.
  // datasets.spec.ts and rules.spec.ts have their own configs + webServer
  // (fs-mode API on :8001 + VITE_API_MODE=http). Excluded here so the
  // default fixture-mode runner doesn't pick them up.
  testIgnore: [/datasets\.spec\.ts/, /rules\.spec\.ts/, /opp-deal(-walkthrough)?\.spec\.ts/],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5174 --strictPort",
    url: "http://127.0.0.1:5174",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});

// Dedicated Playwright config for the rule-engine e2e suite.
//
// The API gateway is expected to be running already (fs-mode) on :8001:
//   cd <repo>
//   DDQ_RUNS_BACKEND=fs DDQ_USE_MONGO=0 \
//     .venv/bin/uvicorn apps.api_gateway.main:app --host 127.0.0.1 --port 8001
//
// Screenshots land in docs/evidence/rule-engine/screenshots/.

import { defineConfig, devices } from "@playwright/test";

const PORT = 5176;

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /rules\.spec\.ts/,
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      VITE_API_BASE_URL: "http://127.0.0.1:8001",
      VITE_API_MODE: "http",
    },
  },
});

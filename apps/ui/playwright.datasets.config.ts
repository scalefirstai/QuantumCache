// Dedicated Playwright config for the dataset-management e2e suite.
//
// Differs from playwright.config.ts in two ways:
//   1. Webserver is started with VITE_API_BASE_URL + VITE_API_MODE=http
//      so the React app talks to the live API gateway (on :8001).
//   2. The test directory is narrowed to a single spec file.
//
// The API gateway is expected to be running already (fs-mode) on :8001:
//   cd <repo>
//   DDQ_RUNS_BACKEND=fs DDQ_USE_MONGO=0 \
//     .venv/bin/uvicorn apps.api_gateway.main:app --host 127.0.0.1 --port 8001

import { defineConfig, devices } from "@playwright/test";

const PORT = 5175;

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /datasets\.spec\.ts/,
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

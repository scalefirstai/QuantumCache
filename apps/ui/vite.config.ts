import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Forward /api/* to the FastAPI gateway when VITE_API_BASE_URL isn't
      // set. Override target via DDQ_API_PROXY=http://host:port if you're
      // running the gateway elsewhere. Fixture-mode features short-circuit
      // before fetch, so the proxy is a no-op for them.
      "/api": {
        target: process.env.DDQ_API_PROXY ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    css: true,
    include: ["src/**/*.test.{ts,tsx}", "tests/unit/**/*.test.{ts,tsx}"],
  },
});

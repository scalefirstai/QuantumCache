import "@testing-library/jest-dom/vitest";
import { afterEach, beforeAll, afterAll } from "vitest";
import { cleanup } from "@testing-library/react";
import { server } from "./mocks/server";

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  // jsdom doesn't implement scrollTo; TanStack Router's scroll restoration calls it.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).scrollTo = () => undefined;
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

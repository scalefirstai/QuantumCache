// Pluggable transport — swap `mode` or VITE_API_BASE_URL to wire a real backend.
// Endpoints live in api/runs.ts, api/employees.ts, api/skills.ts and reference
// these helpers; nothing else in the app should import fetch or fs directly.

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const mode = (import.meta.env.VITE_API_MODE ?? "fixture") as
  | "fixture"
  | "http";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public path: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function get<T>(
  path: string,
  fixtureLoader: () => Promise<{ default: T }>,
): Promise<T> {
  if (mode === "fixture") {
    const mod = await fixtureLoader();
    return mod.default;
  }
  const res = await fetch(`${baseUrl}${path}`);
  if (!res.ok) {
    throw new ApiError(`GET ${path} failed`, res.status, path);
  }
  return (await res.json()) as T;
}

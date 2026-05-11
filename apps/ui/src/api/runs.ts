import type { RunView } from "@/types/run";
import { ApiError, get } from "./client";

export interface RunIndexEntry {
  runId: string;
  client: string;
  framework: string;
  verdict: string;
  sealedAt: string;
  questionPreview: string;
}

/**
 * Production endpoint shapes (proposed):
 *   GET /api/v1/runs              → RunIndexEntry[]
 *   GET /api/v1/runs/:run_id      → RunView
 *
 * Today, both forms read from `apps/ui/src/mocks/fixtures/`, which is generated
 * by `data/bootstrap/12_build_ui_fixtures.py` from the real sealed-run
 * manifests under `data/manifests/runs/`. The shape on the wire matches the
 * fixtures verbatim — no transformation is needed when the backend lands.
 */
export async function listRuns(): Promise<RunIndexEntry[]> {
  return get<RunIndexEntry[]>(
    `/api/v1/runs`,
    () =>
      import("@/mocks/fixtures/runs-index.json").then((m) => ({
        default: m.default as unknown as RunIndexEntry[],
      })),
  );
}

const runModules = import.meta.glob<{ default: RunView }>(
  "@/mocks/fixtures/runs/*.json",
);

export async function getRun(runId: string): Promise<RunView> {
  // Match by path suffix; falls through to 404 if no fixture exists.
  const entry = Object.entries(runModules).find(([path]) =>
    path.endsWith(`/${runId}.json`),
  );
  if (!entry) {
    throw new ApiError("Run not found", 404, `/api/v1/runs/${runId}`);
  }
  const [, loader] = entry;
  return get<RunView>(`/api/v1/runs/${runId}`, () =>
    loader().then((m) => ({ default: m.default as unknown as RunView })),
  );
}

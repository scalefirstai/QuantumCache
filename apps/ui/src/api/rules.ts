// Rule-engine client.
//
// Mirrors apps/ui/src/api/datasets.ts. Reads (list/get) fall back to
// static fixtures under apps/ui/src/mocks/fixtures/rules/ when
// `VITE_API_MODE=fixture`; writes always hit HTTP.

import type {
  RuleCreateBody,
  RuleDecisionBody,
  RuleDetail,
  RuleEvaluateResult,
  RuleStatus,
  RuleSubmitBody,
  RuleSummary,
  RuleUpdateBody,
  RuleValidateResult,
  Condition,
} from "@/types/rule";
import { ApiError, get } from "./client";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

async function send<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${baseUrl}${path}`, {
    headers: { "content-type": "application/json", ...(init.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(
      `${init.method ?? "GET"} ${path} ${res.status}: ${body}`,
      res.status,
      path,
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Reads ---

export const listRules = (
  filters: { engine?: string; status?: RuleStatus } = {},
): Promise<RuleSummary[]> => {
  const qs = new URLSearchParams();
  if (filters.engine) qs.set("engine", filters.engine);
  if (filters.status) qs.set("status", filters.status);
  const q = qs.toString();
  return get<RuleSummary[]>(
    `/api/v1/rules${q ? "?" + q : ""}`,
    () =>
      import("@/mocks/fixtures/rules/index.json").then((m) => ({
        default: (m.default as unknown as RuleSummary[]).filter((r) => {
          if (filters.engine && r.engine !== filters.engine) return false;
          if (filters.status && r.status !== filters.status) return false;
          return true;
        }),
      })),
  );
};

export const listReviewQueue = (): Promise<RuleSummary[]> =>
  get<RuleSummary[]>(
    "/api/v1/rules/queue",
    () =>
      import("@/mocks/fixtures/rules/queue.json").then((m) => ({
        default: m.default as unknown as RuleSummary[],
      })),
  );

export const getRule = (ruleId: string): Promise<RuleDetail> =>
  get<RuleDetail>(
    `/api/v1/rules/${encodeURIComponent(ruleId)}`,
    async () => {
      const all = (
        await import("@/mocks/fixtures/rules/details.json")
      ).default as unknown as Record<string, RuleDetail>;
      const hit = all[ruleId];
      if (!hit) {
        throw new ApiError(`Rule not found: ${ruleId}`, 404, `/api/v1/rules/${ruleId}`);
      }
      return { default: hit };
    },
  );

// --- Writes ---

export const createRule = (body: RuleCreateBody): Promise<RuleDetail> =>
  send<RuleDetail>("/api/v1/rules", { method: "POST", body: JSON.stringify(body) });

export const updateRule = (
  ruleId: string,
  body: RuleUpdateBody,
): Promise<RuleDetail> =>
  send<RuleDetail>(`/api/v1/rules/${encodeURIComponent(ruleId)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const deleteRule = (
  ruleId: string,
  opts: { force?: boolean } = {},
): Promise<{ deleted: true }> =>
  send<{ deleted: true }>(
    `/api/v1/rules/${encodeURIComponent(ruleId)}${opts.force ? "?force=true" : ""}`,
    { method: "DELETE" },
  );

export const submitRule = (
  ruleId: string,
  body: RuleSubmitBody,
): Promise<RuleDetail> =>
  send<RuleDetail>(`/api/v1/rules/${encodeURIComponent(ruleId)}/submit`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const approveRule = (
  ruleId: string,
  body: RuleDecisionBody,
): Promise<RuleDetail> =>
  send<RuleDetail>(`/api/v1/rules/${encodeURIComponent(ruleId)}/approve`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const rejectRule = (
  ruleId: string,
  body: RuleDecisionBody,
): Promise<RuleDetail> =>
  send<RuleDetail>(`/api/v1/rules/${encodeURIComponent(ruleId)}/reject`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const validateDsl = (when: Condition): Promise<RuleValidateResult> =>
  send<RuleValidateResult>("/api/v1/rules/validate", {
    method: "POST",
    body: JSON.stringify({ when }),
  });

export const evaluateRule = (
  ruleId: string,
  context: Record<string, unknown>,
): Promise<RuleEvaluateResult> =>
  send<RuleEvaluateResult>(`/api/v1/rules/${encodeURIComponent(ruleId)}/evaluate`, {
    method: "POST",
    body: JSON.stringify({ context }),
  });

// Opp→Deal API client. HTTP-only (no fixture fallback) — every UI surface
// in this feature expects a live API gateway at VITE_API_BASE_URL.

import { ApiError } from "./client";
import type {
  ApprovalRequest,
  CapacityImpact,
  CommitmentSet,
  ComplexityScorecard,
  CostStack,
  DealJournalEvent,
  EcrmSource,
  EcrmSourceState,
  OperatingModelPlan,
  Opportunity,
  PricingProposal,
  ReplayReport,
  ScopeManifest,
  SealedDealBundle,
  UpmEntry,
} from "@/types/oppDeal";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

async function http<T>(path: string, init: RequestInit = {}): Promise<T> {
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

// ── catalogs ──
export const listUpm = () => http<UpmEntry[]>("/api/v1/opp-deal/upm");
export const listApps = () => http<Array<Record<string, unknown>>>("/api/v1/opp-deal/apps");

// ── opportunities (S01) ──
export const listOpportunities = () =>
  http<Opportunity[]>("/api/v1/opp-deal/opportunities");

export const getOpportunity = (id: string) =>
  http<Opportunity>(`/api/v1/opp-deal/opportunities/${id}`);

export const createOpportunity = (body: unknown) =>
  http<Opportunity>("/api/v1/opp-deal/opportunities", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const patchOpportunity = (id: string, body: unknown) =>
  http<Opportunity>(`/api/v1/opp-deal/opportunities/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });

export const deleteOpportunity = (id: string) =>
  http<{ deleted: boolean }>(`/api/v1/opp-deal/opportunities/${id}`, {
    method: "DELETE",
  });

// ── stages ──
export const runScope = (id: string) =>
  http<ScopeManifest>(`/api/v1/opp-deal/opportunities/${id}/scope`, { method: "POST" });
export const getScope = (id: string) =>
  http<ScopeManifest>(`/api/v1/opp-deal/opportunities/${id}/scope`);

export const setCommitments = (id: string, body: unknown) =>
  http<CommitmentSet>(`/api/v1/opp-deal/opportunities/${id}/commitments`, {
    method: "POST",
    body: JSON.stringify(body),
  });
export const getCommitments = (id: string) =>
  http<CommitmentSet>(`/api/v1/opp-deal/opportunities/${id}/commitments`);

export const runComplexity = (id: string) =>
  http<ComplexityScorecard>(`/api/v1/opp-deal/opportunities/${id}/complexity`, {
    method: "POST",
  });
export const getComplexity = (id: string) =>
  http<ComplexityScorecard>(`/api/v1/opp-deal/opportunities/${id}/complexity`);

export const runCost = (id: string) =>
  http<CostStack>(`/api/v1/opp-deal/opportunities/${id}/cost`, { method: "POST" });
export const getCost = (id: string) =>
  http<CostStack>(`/api/v1/opp-deal/opportunities/${id}/cost`);

export const runCapacity = (id: string) =>
  http<CapacityImpact>(`/api/v1/opp-deal/opportunities/${id}/capacity`, {
    method: "POST",
  });
export const getCapacity = (id: string) =>
  http<CapacityImpact>(`/api/v1/opp-deal/opportunities/${id}/capacity`);

export const runPricing = (id: string) =>
  http<PricingProposal>(`/api/v1/opp-deal/opportunities/${id}/pricing`, {
    method: "POST",
  });
export const getPricing = (id: string) =>
  http<PricingProposal>(`/api/v1/opp-deal/opportunities/${id}/pricing`);

export const runOperatingModel = (id: string) =>
  http<OperatingModelPlan>(`/api/v1/opp-deal/opportunities/${id}/operating-model`, {
    method: "POST",
  });
export const getOperatingModel = (id: string) =>
  http<OperatingModelPlan>(`/api/v1/opp-deal/opportunities/${id}/operating-model`);

export const requestApproval = (id: string) =>
  http<ApprovalRequest>(`/api/v1/opp-deal/opportunities/${id}/approval`, {
    method: "POST",
  });
export const getApproval = (id: string) =>
  http<ApprovalRequest>(`/api/v1/opp-deal/opportunities/${id}/approval`);

export const decideApproval = (
  id: string,
  role: string,
  user_id: string,
  comment = "",
) =>
  http<ApprovalRequest>(
    `/api/v1/opp-deal/opportunities/${id}/approval/decide`,
    {
      method: "POST",
      body: JSON.stringify({ role, user_id, comment }),
    },
  );

export const sealDeal = (id: string) =>
  http<SealedDealBundle>(`/api/v1/opp-deal/opportunities/${id}/seal`, {
    method: "POST",
  });
export const getBundle = (id: string) =>
  http<SealedDealBundle>(`/api/v1/opp-deal/opportunities/${id}/bundle`);

export const replayDeal = (id: string) =>
  http<ReplayReport>(`/api/v1/opp-deal/opportunities/${id}/replay`);

export const getJournal = (id: string) =>
  http<DealJournalEvent[]>(`/api/v1/opp-deal/opportunities/${id}/journal`);

// ── lifecycle helpers ──
export const advanceOpportunity = (id: string) =>
  http<Opportunity>(`/api/v1/opp-deal/opportunities/${id}/advance`, {
    method: "POST",
  });

export const disposeOpportunity = (
  id: string,
  state: "lost" | "withdrawn",
  reason: string,
) =>
  http<Opportunity>(`/api/v1/opp-deal/opportunities/${id}/dispose`, {
    method: "POST",
    body: JSON.stringify({ state, reason }),
  });

// ── eCRM source inbox (S01 pre-intake) ──
export const listSources = (state?: EcrmSourceState) => {
  const q = state ? `?state=${encodeURIComponent(state)}` : "";
  return http<EcrmSource[]>(`/api/v1/opp-deal/sources${q}`);
};

export const getSource = (id: string) =>
  http<EcrmSource>(`/api/v1/opp-deal/sources/${id}`);

export const promoteSource = (id: string) =>
  http<Opportunity>(`/api/v1/opp-deal/sources/${id}/promote`, { method: "POST" });

export const declineSource = (id: string, reason: string) =>
  http<EcrmSource>(`/api/v1/opp-deal/sources/${id}/decline`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

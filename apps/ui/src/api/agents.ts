// AutoGen Lite client. Always hits the API gateway over HTTP — fixture mode
// is not modeled here because these endpoints are intrinsically stateful.
// Callers should run with VITE_API_MODE=http; in fixture mode the loaders
// reject with a clear error.

import type {
  ActivateBody,
  AgentDetail,
  AgentSummary,
  ApplyTemplateBody,
  AuditEntry,
  CreateVersionBody,
  Model,
  PlaygroundRun,
  PromptDocument,
  SkillSummary,
  Template,
  VersionSummary,
} from "@/types/agent";
import { ApiError, get } from "./client";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

async function send<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${baseUrl}${path}`, {
    headers: { "content-type": "application/json", ...(init.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(`${init.method ?? "GET"} ${path} ${res.status}: ${body}`, res.status, path);
  }
  return (await res.json()) as T;
}

const rejectFixture = () =>
  Promise.reject(new ApiError("Live API only; not available in fixture mode", 503, ""));

// --- agents ---

export const listAgents = (): Promise<AgentSummary[]> =>
  get<AgentSummary[]>("/api/v1/agents", rejectFixture);

export const getAgent = (id: string): Promise<AgentDetail> =>
  get<AgentDetail>(`/api/v1/agents/${id}`, rejectFixture);

export const listVersions = (id: string): Promise<VersionSummary[]> =>
  get<VersionSummary[]>(`/api/v1/agents/${id}/versions`, rejectFixture);

export const getVersion = (id: string, version: string): Promise<PromptDocument> =>
  get<PromptDocument>(`/api/v1/agents/${id}/versions/${version}`, rejectFixture);

export const createVersion = (id: string, body: CreateVersionBody): Promise<PromptDocument> =>
  send<PromptDocument>(`/api/v1/agents/${id}/versions`, {
    method: "POST", body: JSON.stringify(body),
  });

export const activateVersion = (id: string, body: ActivateBody): Promise<AgentDetail> =>
  send<AgentDetail>(`/api/v1/agents/${id}/active`, {
    method: "PUT", body: JSON.stringify(body),
  });

export const applyTemplate = (id: string, body: ApplyTemplateBody): Promise<PromptDocument> =>
  send<PromptDocument>(`/api/v1/agents/${id}/apply-template`, {
    method: "POST", body: JSON.stringify(body),
  });

export const getAudit = (id: string): Promise<AuditEntry[]> =>
  get<AuditEntry[]>(`/api/v1/agents/${id}/audit`, rejectFixture);

// --- models / skills / templates ---

export const listModels = (): Promise<Model[]> =>
  get<Model[]>("/api/v1/models", rejectFixture);

export const listSkills = (): Promise<SkillSummary[]> =>
  get<SkillSummary[]>("/api/v1/skills", rejectFixture);

export const listTemplates = (): Promise<Template[]> =>
  get<Template[]>("/api/v1/templates", rejectFixture);

// --- playground ---

export const submitPlayground = (body: {
  question: string;
  framework: string;
  actor?: string;
}): Promise<{ runId: string }> =>
  send<{ runId: string }>("/api/v1/playground/runs", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getPlaygroundRun = (runId: string): Promise<PlaygroundRun> =>
  get<PlaygroundRun>(`/api/v1/playground/runs/${runId}`, rejectFixture);

export const listPlaygroundRuns = (): Promise<PlaygroundRun[]> =>
  get<PlaygroundRun[]>("/api/v1/playground/runs", rejectFixture);

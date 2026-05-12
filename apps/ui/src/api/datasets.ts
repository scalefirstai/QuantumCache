// Dataset-management client.
//
// Reads (list / get) fall back to the static fixtures under
// `apps/ui/src/mocks/fixtures/datasets/` when `VITE_API_MODE=fixture`, so
// the e2e screenshot suite can run without a backend. Writes
// (POST/PUT/DELETE) always hit HTTP — fixture mode rejects with a clear
// error.

import type {
  AuditRedaction,
  AuditRedactionCreateBody,
  AuditRunDetail,
  AuditRunSummary,
  AuditVerifyResult,
  CanonicalCreateBody,
  CanonicalDetail,
  CanonicalUpdateBody,
  DatasetSummary,
  KnowledgeConfirmBody,
  KnowledgeCreateBody,
  KnowledgeDoc,
  KnowledgeUpdateBody,
  KnowledgeUploadInitBody,
  KnowledgeUploadTicket,
} from "@/types/dataset";
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
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

// --- Index ---

export const listDatasets = (): Promise<DatasetSummary[]> =>
  get<DatasetSummary[]>(
    "/api/v1/datasets",
    () =>
      import("@/mocks/fixtures/datasets/index.json").then((m) => ({
        default: m.default as unknown as DatasetSummary[],
      })),
  );

// --- Knowledge ---

export const listKnowledge = (): Promise<KnowledgeDoc[]> =>
  get<KnowledgeDoc[]>(
    "/api/v1/datasets/knowledge",
    () =>
      import("@/mocks/fixtures/datasets/knowledge.json").then((m) => ({
        default: m.default as unknown as KnowledgeDoc[],
      })),
  );

export const getKnowledge = (docId: string): Promise<KnowledgeDoc> =>
  get<KnowledgeDoc>(
    `/api/v1/datasets/knowledge/${encodeURIComponent(docId)}`,
    async () => {
      const all = (
        await import("@/mocks/fixtures/datasets/knowledge.json")
      ).default as unknown as KnowledgeDoc[];
      const hit = all.find((d) => d.docId === docId);
      if (!hit) {
        throw new ApiError(
          `Knowledge doc not found: ${docId}`,
          404,
          `/api/v1/datasets/knowledge/${docId}`,
        );
      }
      return { default: hit };
    },
  );

export const createKnowledge = (body: KnowledgeCreateBody): Promise<KnowledgeDoc> =>
  send<KnowledgeDoc>("/api/v1/datasets/knowledge", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const requestKnowledgeUpload = (
  body: KnowledgeUploadInitBody,
): Promise<KnowledgeUploadTicket> =>
  send<KnowledgeUploadTicket>("/api/v1/datasets/knowledge/upload-url", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const putKnowledgeUploadObject = async (
  ticket: KnowledgeUploadTicket,
  file: File,
  onProgress?: (loaded: number, total: number) => void,
): Promise<void> => {
  // XMLHttpRequest because fetch() lacks PUT progress events.
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(ticket.method, ticket.uploadUrl, true);
    for (const [k, v] of Object.entries(ticket.headers)) {
      xhr.setRequestHeader(k, v);
    }
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded, e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`S3 PUT ${xhr.status}: ${xhr.responseText}`));
    };
    xhr.onerror = () => reject(new Error("S3 PUT network error"));
    xhr.send(file);
  });
};

export const confirmKnowledgeUpload = (body: KnowledgeConfirmBody): Promise<KnowledgeDoc> =>
  send<KnowledgeDoc>("/api/v1/datasets/knowledge/confirm", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateKnowledge = (
  docId: string,
  body: KnowledgeUpdateBody,
): Promise<KnowledgeDoc> =>
  send<KnowledgeDoc>(`/api/v1/datasets/knowledge/${encodeURIComponent(docId)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const deleteKnowledge = (docId: string): Promise<{ deleted: true }> =>
  send<{ deleted: true }>(
    `/api/v1/datasets/knowledge/${encodeURIComponent(docId)}`,
    { method: "DELETE" },
  );

// --- Canonical ---

export const listCanonical = (): Promise<CanonicalDetail[]> =>
  get<CanonicalDetail[]>(
    "/api/v1/datasets/canonical",
    () =>
      import("@/mocks/fixtures/datasets/canonical.json").then((m) => ({
        default: m.default as unknown as CanonicalDetail[],
      })),
  );

export const getCanonical = (canonicalId: string): Promise<CanonicalDetail> =>
  get<CanonicalDetail>(
    `/api/v1/datasets/canonical/${encodeURIComponent(canonicalId)}`,
    async () => {
      const all = (
        await import("@/mocks/fixtures/datasets/canonical.json")
      ).default as unknown as CanonicalDetail[];
      const hit = all.find((q) => q.canonicalId === canonicalId);
      if (!hit) {
        throw new ApiError(
          `Canonical not found: ${canonicalId}`,
          404,
          `/api/v1/datasets/canonical/${canonicalId}`,
        );
      }
      return { default: hit };
    },
  );

export const createCanonical = (body: CanonicalCreateBody): Promise<CanonicalDetail> =>
  send<CanonicalDetail>("/api/v1/datasets/canonical", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateCanonical = (
  canonicalId: string,
  body: CanonicalUpdateBody,
): Promise<CanonicalDetail> =>
  send<CanonicalDetail>(`/api/v1/datasets/canonical/${encodeURIComponent(canonicalId)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const deleteCanonical = (
  canonicalId: string,
  opts: { force?: boolean } = {},
): Promise<{ deleted: true }> =>
  send<{ deleted: true }>(
    `/api/v1/datasets/canonical/${encodeURIComponent(canonicalId)}${
      opts.force ? "?force=true" : ""
    }`,
    { method: "DELETE" },
  );

// --- Audit ---

export const listAudit = (): Promise<AuditRunSummary[]> =>
  get<AuditRunSummary[]>(
    "/api/v1/datasets/audit",
    () =>
      import("@/mocks/fixtures/datasets/audit.json").then((m) => ({
        default: m.default as unknown as AuditRunSummary[],
      })),
  );

export const getAudit = (runId: string): Promise<AuditRunDetail> =>
  get<AuditRunDetail>(
    `/api/v1/datasets/audit/${encodeURIComponent(runId)}`,
    async () => {
      const all = (
        await import("@/mocks/fixtures/datasets/audit-detail.json")
      ).default as unknown as Record<string, AuditRunDetail>;
      const hit = all[runId];
      if (!hit) {
        throw new ApiError(
          `Audit run not found: ${runId}`,
          404,
          `/api/v1/datasets/audit/${runId}`,
        );
      }
      return { default: hit };
    },
  );

export const verifyAudit = (runId: string): Promise<AuditVerifyResult> =>
  send<AuditVerifyResult>(
    `/api/v1/datasets/audit/${encodeURIComponent(runId)}/verify`,
    { method: "POST" },
  );

export const listAuditRedactions = (runId: string): Promise<AuditRedaction[]> =>
  get<AuditRedaction[]>(
    `/api/v1/datasets/audit/${encodeURIComponent(runId)}/redactions`,
    () => Promise.resolve({ default: [] as AuditRedaction[] }),
  );

export const createAuditRedaction = (
  runId: string,
  body: AuditRedactionCreateBody,
): Promise<AuditRedaction> =>
  send<AuditRedaction>(
    `/api/v1/datasets/audit/${encodeURIComponent(runId)}/redactions`,
    { method: "POST", body: JSON.stringify(body) },
  );

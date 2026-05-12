// Wire shapes for /api/v1/datasets/* — mirror docs/specs/dataset-management.md §3.

export type DatasetId = "knowledge" | "canonical" | "audit";

export interface DatasetSummary {
  id: DatasetId;
  label: string;
  count: number;
  lastUpdatedAt: string | null;
  description: string;
}

export interface KnowledgeDoc {
  docId: string;
  source: string;
  entity: string;
  kind: string | null;
  effectiveDate: string | null;
  primaryDesc: string;
  docHash: string;
  contentType: string;
  bytes: number;
  url: string | null;
  s3Uri: string;
  tags: string[];
  ingestedAt: string;
  updatedAt: string | null;
  displayTitle: string;
}

export interface KnowledgeCreateBody {
  docId: string;
  source: string;
  entity: string;
  primaryDesc: string;
  docHash: string;
  contentType: string;
  bytes: number;
  s3Uri: string;
  kind?: string | null;
  effectiveDate?: string | null;
  url?: string | null;
  tags?: string[];
}

export interface KnowledgeUpdateBody {
  primaryDesc?: string;
  kind?: string | null;
  effectiveDate?: string | null;
  tags?: string[];
  url?: string | null;
}

export interface KnowledgeUploadInitBody {
  filename: string;
  contentType: string;
  sizeBytes: number;
  source?: string;
}

export interface KnowledgeUploadTicket {
  uploadUrl: string;
  method: "PUT";
  headers: Record<string, string>;
  bucket: string;
  key: string;
  s3Uri: string;
  expiresInSec: number;
}

export interface KnowledgeConfirmBody {
  key: string;
  docId: string;
  source: string;
  entity: string;
  primaryDesc: string;
  contentType: string;
  kind?: string | null;
  effectiveDate?: string | null;
  url?: string | null;
  tags?: string[];
  clientDocHash?: string;
}

export interface FrameworkMapping {
  framework: string;
  version: string;
  questionRef: string;
}

export interface CanonicalDetail {
  canonicalId: string;
  label: string;
  description: string;
  parentId: string | null;
  tier: 1 | 2 | 3;
  doNotAnswer: boolean;
  owners: string[];
  tags: string[];
  frameworkMappings: FrameworkMapping[];
  createdAt: string;
  updatedAt: string;
}

export interface CanonicalCreateBody {
  canonicalId: string;
  label: string;
  description?: string;
  parentId?: string | null;
  tier?: 1 | 2 | 3;
  doNotAnswer?: boolean;
  owners?: string[];
  tags?: string[];
  frameworkMappings?: FrameworkMapping[];
}

export type CanonicalUpdateBody = Partial<Omit<CanonicalCreateBody, "canonicalId">>;

export interface AuditEvent {
  eventId: string;
  kind: string;
  agent: string | null;
  ts: string | null;
  payloadHash: string | null;
  prevHash: string | null;
  chainHash: string | null;
}

export interface AuditRunSummary {
  runId: string;
  ddqId: string | null;
  client: string;
  framework: string;
  verdict: string;
  sealedAt: string | null;
  eventCount: number;
  merkleRoot: string | null;
}

export interface AuditRunDetail {
  runId: string;
  ddqId: string | null;
  sealedAt: string | null;
  platformVersion: string | null;
  taxonomyVersion: string | null;
  libraryVersion: string | null;
  input: { questionId?: string; framework?: string; text?: string } | null;
  verdict: string | null;
  route: string | null;
  merkleRoot: string | null;
  events: AuditEvent[];
  agents: Record<string, unknown>;
  redactionCount: number;
}

export interface AuditVerifyResult {
  chainOk: boolean;
  merkleOk: boolean;
  expectedMerkle: string | null;
  recomputedMerkle: string;
  brokenAt: string | null;
  verifiedAt: string;
}

export interface AuditRedaction {
  redactionId: string;
  runId: string;
  eventId: string;
  field: string;
  reason: string;
  actor: string;
  ts: string;
}

export interface AuditRedactionCreateBody {
  eventId: string;
  field: string;
  reason: string;
  actor?: string;
}

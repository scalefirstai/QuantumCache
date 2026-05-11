// End-to-end view of one DDQ email through the 8-agent L06 roster.
// Built by data/bootstrap/13_build_pipeline_fixtures.py from the sealed
// run JSONs under data/manifests/runs/. Shape on the wire = fixture shape.

export type StageStatus = "pass" | "warn" | "halt" | "skip";
export type StageKind = "system" | "agent" | "rule";

export type PipelineStageId =
  | "intake"
  | "mapper"
  | "library"
  | "retrieve"
  | "sourcer"
  | "drafter"
  | "verifier"
  | "consistency"
  | "pii"
  | "freshness"
  | "router"
  | "sealed";

export interface PipelineStageEvent {
  eventId: string;
  ts: string;
  kind: string;
  agent: string;
  payload: Record<string, unknown>;
  payloadHash: string;
  chainHash: string;
}

export interface PipelineStage {
  id: PipelineStageId;
  title: string;
  agent: string;
  kind: StageKind;
  status: StageStatus;
  summary: string;
  events: PipelineStageEvent[];
  payload: Record<string, unknown>;
}

export interface PipelineQuestion {
  questionId: string;
  framework: string;
  text: string;
  runId: string;
  canonicalId: string | null;
  confidence: number;
  libraryHit: boolean;
  verdict: string;
  route: string;
  queue: string | null;
  tier: string;
  elapsedMs: number;
  draftChars: number;
  citationCount: number;
  merkleRoot: string;
  outboundPreview: string;
  stages: PipelineStage[];
}

export interface Pipeline {
  ddqId: string;
  subject: string;
  from: string;
  to: string;
  rawEmlSha256: string;
  sealedAt: string;
  platformVersion: string;
  questionCount: number;
  questions: PipelineQuestion[];
}

export interface PipelineIndexEntry {
  ddqId: string;
  subject: string;
  from: string;
  questionCount: number;
  sealedAt: string;
}

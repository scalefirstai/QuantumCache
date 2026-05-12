// AutoGen Lite — agent / model / skill / template / playground types.
// Mirrors the wire shape from apps/api_gateway/routers/{agents,models,skills,
// templates,playground}.py. Spec: docs/autogen-lite.md.

export type AgentKind = "llm" | "rule";

export interface AgentSummary {
  id: string;
  name: string;
  kind: AgentKind;
  model: string | null;
  temperature: number | null;
  maxTokens: number | null;
  tools: string[];
  activeVersion: string | null;
  versionCount: number;
  lastEditedAt: string | null;
}

export interface PromptDocument {
  agentId: string;
  agentName: string;
  version: string;
  model: string;
  temperature: number;
  maxTokens: number;
  description: string;
  tools: string[];
  system: string;
  userTemplate: string;
  raw: string;
  sha256: string;
}

export interface AgentDetail extends AgentSummary {
  description: string;
  active: PromptDocument | null;
}

export interface VersionSummary {
  version: string;
  createdAt: string;
  isActive: boolean;
  sha256: string;
  comment: string | null;
}

export interface AuditEntry {
  ts: string;
  actor: string;
  action: "create" | "activate" | "apply-template";
  fromVersion: string | null;
  toVersion: string;
  comment: string | null;
}

export interface CreateVersionBody {
  baseVersion: string;
  bump: "patch" | "minor" | "major";
  system: string;
  userTemplate: string;
  model?: string;
  temperature?: number;
  maxTokens?: number;
  description?: string;
  tools?: string[];
  comment?: string;
  actor?: string;
  activate?: boolean;
}

export interface ApplyTemplateBody {
  templateId: string;
  bump?: "patch" | "minor" | "major";
  actor?: string;
  comment?: string;
  activate?: boolean;
}

export interface ActivateBody {
  version: string;
  comment?: string;
  actor?: string;
}

export interface Model {
  id: string;
  displayName: string;
  provider: string;
  tier: string;
  contextWindow: number;
  supportsTools: boolean;
  supportsThinking: boolean;
  pricing: { inputPerMTok: number; outputPerMTok: number };
  notes: string;
}

export interface SkillSummary {
  id: string;
  name: string;
  category: string;
  ownedBy: string;
  description: string;
  signature: string;
  usedBy: string[];
}

export interface Template {
  id: string;
  name: string;
  description: string;
  patch: {
    model?: string;
    temperature?: number;
    maxTokens?: number;
    systemSuffix?: string;
  };
}

export type PlaygroundStatus = "queued" | "running" | "succeeded" | "failed";

export interface PlaygroundRun {
  runId: string;
  question: string;
  framework: string;
  actor: string;
  status: PlaygroundStatus;
  submittedAt: string;
  completedAt: string | null;
  sealedRunId: string | null;
  error: string | null;
}

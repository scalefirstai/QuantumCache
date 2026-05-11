export interface SkillSignatureRow {
  label: string;
  value: string;
  mono?: boolean;
}

export interface PipelineNode {
  id: string;
  label: string;
  sub?: string;
  meta?: string;
  variant: "input" | "step" | "filter" | "merge" | "output";
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface PipelineEdge {
  from: string;
  to: string;
  /** "main" or "branch" — branch edges render with secondary stroke */
  kind: "main" | "branch";
}

export interface PipelineCacheNote {
  title: string;
  lines: string[];
  hitRate: string;
  cachedP95: string;
}

export interface SkillIO {
  name: string;
  description: string;
}

export interface LatencyBar {
  label: string;
  ms: number;
  tone: "step" | "filter" | "total" | "cached";
}

export interface QualityCard {
  label: string;
  value: string;
  target: string;
  tone: "ok" | "warn" | "neutral";
}

export interface SkillDetail {
  id: string;
  name: string;
  tagline: string;
  signature: SkillSignatureRow[];
  pipeline: {
    nodes: PipelineNode[];
    edges: PipelineEdge[];
    cache: PipelineCacheNote;
  };
  inputs: SkillIO[];
  output: { typeName: string; fields: SkillIO[] };
  latency: { budget: LatencyBar[]; max: number };
  quality: QualityCard[];
  failureModes: string[];
}

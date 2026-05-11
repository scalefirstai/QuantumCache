export type StatusTone = "ok" | "warn" | "danger" | "neutral";

export interface ReviewKpi {
  label: string;
  value: string;
  delta: string;
  tone: StatusTone;
}

export interface QualitySeries {
  months: string[];
  libraryHit: number[];
  autoPass: number[];
  hallucinationX10: number[];
  /** Optional override for the third series legend (e.g., "Halt rate %"). */
  tertiaryLabel?: string;
  libraryHitTarget: number;
}

export interface CostSeries {
  months: string[];
  opus: number[];
  sonnet: number[];
  haiku: number[];
  budget: number;
}

export interface WaitSeries {
  domains: string[];
  values: number[];
  target: number;
  toneByDomain: StatusTone[];
}

export type AgentStatus = "ok" | "warn" | "danger";

export interface AgentScorecardRow {
  name: string;
  calls: number;
  p95: string;
  evalPass: string;
  cost: string;
  costTone: StatusTone;
  status: AgentStatus;
}

export interface PerformanceReview {
  employeeId: string;
  period: string;
  reviewer: string;
  signedOffBy: string;
  overall: string;
  overallSub: string;
  summary: string;
  kpis: ReviewKpi[];
  quality: QualitySeries;
  cost: CostSeries;
  wait: WaitSeries;
  scorecard: AgentScorecardRow[];
  whatWentWell: string[];
  goals: string[];
}

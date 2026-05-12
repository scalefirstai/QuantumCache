// Wire shapes for /api/v1/rules/* — mirror docs/specs/rule-engine.md §3.

export type RuleEngine = "freshness" | "approval";
export type RuleStatus = "draft" | "pending_review" | "active" | "archived";
export type RuleOp =
  | "eq" | "ne"
  | "lt" | "lte" | "gt" | "gte"
  | "in" | "not_in"
  | "contains"
  | "matches"
  | "startswith" | "endswith"
  | "age_days_gt"
  | "exists" | "truthy";

export interface LeafCondition {
  field: string;
  op: RuleOp;
  value?: unknown;
}

export interface AllCondition { all: Condition[]; }
export interface AnyCondition { any: Condition[]; }
export interface NotCondition { not: Condition; }

export type Condition =
  | LeafCondition
  | AllCondition
  | AnyCondition
  | NotCondition
  | Record<string, never>; // empty {} = vacuously true

export interface RuleSummary {
  ruleId: string;
  engine: RuleEngine;
  title: string;
  priority: number;
  status: RuleStatus;
  version: string;
  reviewQueue: string;
  tags: string[];
  updatedAt: string;
  submittedBy?: string;
}

export interface RuleDetail {
  ruleId: string;
  engine: RuleEngine;
  title: string;
  description: string;
  priority: number;
  status: RuleStatus;
  version: string;
  when: Condition;
  then: Record<string, unknown>;
  reviewQueue: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
  approvedAt: string | null;
  approvedBy: string | null;
  submittedBy: string | null;
  rationale: string | null;
}

export interface RuleCreateBody {
  ruleId: string;
  engine: RuleEngine;
  title: string;
  description?: string;
  priority?: number;
  when?: Condition;
  then?: Record<string, unknown>;
  reviewQueue?: string;
  tags?: string[];
}

export interface RuleUpdateBody {
  title?: string;
  description?: string;
  priority?: number;
  when?: Condition;
  then?: Record<string, unknown>;
  reviewQueue?: string;
  tags?: string[];
}

export interface RuleSubmitBody { submittedBy: string; }
export interface RuleDecisionBody { approver: string; rationale: string; }

export interface RuleValidateResult {
  ok: boolean;
  errors: Array<{ path: string; msg: string }>;
}

export interface RuleEvaluateResult {
  ruleId: string;
  fired: boolean;
  verdict: Record<string, unknown> | null;
}

export interface Kpi {
  label: string;
  value: string;
}

export type AgentTone = "primary" | "rule";

export interface Agent {
  name: string;
  modelLine: string;
  description: string;
  skills: string[];
  tone: AgentTone;
}

export type QueueStatus = "open" | "halted";

export interface QueueItem {
  domain: string;
  scope: string;
  caption: string;
  status: QueueStatus;
}

export interface DecisionRight {
  icon: "check" | "user-check" | "shield-x";
  text: string;
}

export interface TimelineStep {
  title: string;
  caption: string;
  duration: string;
  tone: "ink" | "teal" | "ochre";
}

export interface EmployeeConsole {
  id: string;
  name: string;
  role: string;
  runId: string;
  runDescription: string;
  reportingLine: string;
  progressPct: number;
  kpis: Kpi[];
  agents: Agent[];
  queue: { awaiting: number; items: QueueItem[] };
  decisionRights: DecisionRight[];
  timeline: TimelineStep[];
}

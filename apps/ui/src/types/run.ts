import type { RichText } from "./tokens";

export type Lane = "knowledge" | "canonical" | "audit";

export type StageId =
  | "intake"
  | "classify"
  | "retrieve"
  | "draft"
  | "validate"
  | "approve"
  | "respond";

export interface DataCell {
  lane: Lane;
  label: string;
  body: RichText;
}

export interface Stage {
  id: StageId;
  ordinal: number;
  title: string;
  sub: string;
  user: RichText;
  system: RichText;
  data: DataCell[];
}

export interface RunView {
  runId: string;
  client: string;
  framework: string;
  questionCount: number;
  /** Verbatim question text the run answered, when available. */
  rawQuestion?: string;
  /** Final verdict: "pass" | "halt" | other. */
  verdict?: string;
  /** ISO timestamp when the run was sealed to S3. */
  sealedAt?: string;
  /** sha256:… Merkle root over the journal. */
  merkleRoot?: string;
  stages: Stage[];
}

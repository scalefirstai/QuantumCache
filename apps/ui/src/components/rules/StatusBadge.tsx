import { TagPill } from "@/components/datasets/Common";
import type { RuleStatus } from "@/types/rule";

const TONE: Record<RuleStatus, "neutral" | "audit" | "ok" | "danger"> = {
  draft: "neutral",
  pending_review: "audit",
  active: "ok",
  archived: "danger",
};

const LABEL: Record<RuleStatus, string> = {
  draft: "Draft",
  pending_review: "Pending review",
  active: "Active",
  archived: "Archived",
};

export function StatusBadge({ status, testId }: { status: RuleStatus; testId?: string }) {
  return (
    <span data-testid={testId ?? `status-badge-${status}`}>
      <TagPill tone={TONE[status]}>{LABEL[status]}</TagPill>
    </span>
  );
}

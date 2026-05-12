import type { RuleCreateBody, RuleEngine } from "@/types/rule";

export interface RuleEditorValue extends RuleCreateBody {
  whenJson: string;
  thenJson: string;
}

export function blankRuleEditor(engine: RuleEngine = "freshness"): RuleEditorValue {
  return {
    ruleId: "",
    engine,
    title: "",
    description: "",
    priority: 100,
    tags: ["operator-added"],
    when: { field: "", op: "eq", value: "" },
    then: engine === "freshness"
      ? { stale: true, reason: "" }
      : { route: "sme_queue", rationale: "" },
    whenJson: "",
    thenJson: "",
  };
}

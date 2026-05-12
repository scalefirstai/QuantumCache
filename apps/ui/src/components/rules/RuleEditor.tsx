// Form for create + update. JSON-mode toggle for full DSL control;
// structured mode is a friendlier surface for simple leaf rules.
//
// Keep this dumb — it's a controlled component. The parent owns the
// submit + error states.

import { useEffect } from "react";
import {
  FormField,
  Input,
  Select,
  TextArea,
} from "@/components/datasets/Common";
import type { RuleCreateBody, RuleEngine, RuleOp } from "@/types/rule";

const OPS: RuleOp[] = [
  "eq", "ne", "lt", "lte", "gt", "gte",
  "in", "not_in", "contains", "matches",
  "startswith", "endswith", "age_days_gt",
  "exists", "truthy",
];

export interface RuleEditorValue extends RuleCreateBody {
  // raw JSON strings shadow the structured fields when editing via JSON mode
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

export function RuleEditor({
  value,
  onChange,
  mode,
  disableId = false,
  formIdPrefix = "rule",
}: {
  value: RuleEditorValue;
  onChange: (v: RuleEditorValue) => void;
  mode: "structured" | "json";
  disableId?: boolean;
  formIdPrefix?: string;
}) {
  // Keep JSON shadows in sync when the structured form changes.
  useEffect(() => {
    if (mode === "structured") {
      onChange({
        ...value,
        whenJson: JSON.stringify(value.when ?? {}, null, 2),
        thenJson: JSON.stringify(value.then ?? {}, null, 2),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  const setLeaf = (key: "field" | "op" | "value", v: string) => {
    const w = (value.when ?? {}) as { field?: string; op?: RuleOp; value?: unknown };
    let coerced: unknown = v;
    if (key === "value") {
      // Try JSON.parse for typed values; fall back to string
      try {
        coerced = JSON.parse(v);
      } catch {
        coerced = v;
      }
    }
    onChange({ ...value, when: { ...w, [key]: coerced } as never });
  };

  const setThen = (k: string, v: unknown) => {
    onChange({ ...value, then: { ...(value.then ?? {}), [k]: v } });
  };

  return (
    <div>
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Rule ID" hint="dot-separated, e.g. freshness.policy.confidential">
          <Input
            required
            disabled={disableId}
            pattern="[A-Za-z0-9._\-]+"
            value={value.ruleId}
            onChange={(e) => onChange({ ...value, ruleId: e.target.value })}
            data-testid={`${formIdPrefix}-id`}
          />
        </FormField>
        <FormField label="Engine">
          <Select
            value={value.engine}
            disabled={disableId}
            onChange={(e) => onChange({ ...value, engine: e.target.value as RuleEngine })}
            data-testid={`${formIdPrefix}-engine`}
          >
            <option value="freshness">freshness</option>
            <option value="approval">approval</option>
          </Select>
        </FormField>
      </div>
      <FormField label="Title">
        <Input
          required
          value={value.title}
          onChange={(e) => onChange({ ...value, title: e.target.value })}
          data-testid={`${formIdPrefix}-title`}
        />
      </FormField>
      <FormField label="Description">
        <TextArea
          rows={2}
          value={value.description ?? ""}
          onChange={(e) => onChange({ ...value, description: e.target.value })}
          data-testid={`${formIdPrefix}-description`}
        />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Priority" hint="lower runs first">
          <Input
            type="number"
            min={1}
            max={9999}
            value={value.priority ?? 100}
            onChange={(e) =>
              onChange({ ...value, priority: Number(e.target.value) })
            }
            data-testid={`${formIdPrefix}-priority`}
          />
        </FormField>
        <FormField label="Tags" hint="Comma-separated">
          <Input
            value={(value.tags ?? []).join(", ")}
            onChange={(e) =>
              onChange({
                ...value,
                tags: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
              })
            }
            data-testid={`${formIdPrefix}-tags`}
          />
        </FormField>
      </div>

      {mode === "structured" ? (
        <>
          <div className="mt-2 mb-1 text-xs font-medium uppercase tracking-wider text-bny-fog">
            When (condition)
          </div>
          <div className="grid grid-cols-3 gap-2 mb-3">
            <Input
              placeholder="field (dotted path)"
              value={(value.when as { field?: string })?.field ?? ""}
              onChange={(e) => setLeaf("field", e.target.value)}
              data-testid={`${formIdPrefix}-when-field`}
            />
            <Select
              value={(value.when as { op?: RuleOp })?.op ?? "eq"}
              onChange={(e) => setLeaf("op", e.target.value)}
              data-testid={`${formIdPrefix}-when-op`}
            >
              {OPS.map((op) => (
                <option key={op} value={op}>{op}</option>
              ))}
            </Select>
            <Input
              placeholder='value (JSON, e.g. "foo" or 42)'
              value={(() => {
                const v = (value.when as { value?: unknown })?.value;
                if (v === undefined) return "";
                return typeof v === "string" ? v : JSON.stringify(v);
              })()}
              onChange={(e) => setLeaf("value", e.target.value)}
              data-testid={`${formIdPrefix}-when-value`}
            />
          </div>

          <div className="mt-2 mb-1 text-xs font-medium uppercase tracking-wider text-bny-fog">
            Then (verdict)
          </div>
          {value.engine === "freshness" ? (
            <div className="grid grid-cols-1 gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={Boolean((value.then as { stale?: boolean })?.stale)}
                  onChange={(e) => setThen("stale", e.target.checked)}
                  data-testid={`${formIdPrefix}-then-stale`}
                />
                Mark library entry / evidence as stale
              </label>
              <Input
                placeholder="Reason template — supports {dotted.path}"
                value={(value.then as { reason?: string })?.reason ?? ""}
                onChange={(e) => setThen("reason", e.target.value)}
                data-testid={`${formIdPrefix}-then-reason`}
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <Select
                value={(value.then as { route?: string })?.route ?? "sme_queue"}
                onChange={(e) => setThen("route", e.target.value)}
                data-testid={`${formIdPrefix}-then-route`}
              >
                <option value="auto_approve">auto_approve</option>
                <option value="sme_queue">sme_queue</option>
                <option value="halt">halt</option>
              </Select>
              <Input
                placeholder="queue (optional override)"
                value={(value.then as { queue?: string })?.queue ?? ""}
                onChange={(e) => setThen("queue", e.target.value)}
                data-testid={`${formIdPrefix}-then-queue`}
              />
              <Input
                placeholder="rationale (shown to SME)"
                value={(value.then as { rationale?: string })?.rationale ?? ""}
                onChange={(e) => setThen("rationale", e.target.value)}
                data-testid={`${formIdPrefix}-then-rationale`}
                className="col-span-2"
              />
            </div>
          )}
        </>
      ) : (
        <>
          <FormField label="When (JSON)" hint="DSL — see /docs/specs/rule-engine.md">
            <TextArea
              rows={5}
              className="font-mono text-xs"
              value={value.whenJson}
              onChange={(e) => {
                const text = e.target.value;
                let parsed: unknown = value.when;
                try { parsed = JSON.parse(text); } catch { /* keep last good */ }
                onChange({ ...value, whenJson: text, when: parsed as never });
              }}
              data-testid={`${formIdPrefix}-when-json`}
            />
          </FormField>
          <FormField label="Then (JSON)">
            <TextArea
              rows={4}
              className="font-mono text-xs"
              value={value.thenJson}
              onChange={(e) => {
                const text = e.target.value;
                let parsed: unknown = value.then;
                try { parsed = JSON.parse(text); } catch { /* keep last good */ }
                onChange({ ...value, thenJson: text, then: parsed as never });
              }}
              data-testid={`${formIdPrefix}-then-json`}
            />
          </FormField>
        </>
      )}
    </div>
  );
}

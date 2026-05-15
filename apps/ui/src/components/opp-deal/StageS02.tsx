import { useEffect, useState } from "react";
import { getScope, runScope } from "@/api/oppDeal";
import type { Opportunity, ScopeManifest } from "@/types/oppDeal";
import { PrimaryButton } from "@/components/datasets/Common";
import { Card, KeyValueGrid, Empty } from "./Format";

export function StageS02({ opp }: { opp: Opportunity }) {
  const [scope, setScope] = useState<ScopeManifest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (opp.scope_manifest_id) {
      getScope(opp.opportunity_id).then(setScope).catch((e) => setErr(String(e)));
    } else {
      setScope(null);
    }
  }, [opp.opportunity_id, opp.scope_manifest_id]);

  const onRun = async () => {
    setBusy(true);
    setErr(null);
    try {
      const m = await runScope(opp.opportunity_id);
      setScope(m);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section data-testid="stage-s02">
      <Card
        title="S02 · Scope manifest"
        testId="card-s02"
        actions={
          <PrimaryButton onClick={onRun} testId="run-scope-btn">
            {busy ? "Running…" : scope ? "Re-run scope" : "Run scope"}
          </PrimaryButton>
        }
      >
        {err && (
          <div className="text-sm text-bny-danger mb-3" data-testid="scope-error">
            {err}
          </div>
        )}
        {!scope ? (
          <Empty>
            Click <b>Run scope</b> to resolve products against UPM, compute the
            delivery app set, and surface eligibility/dependency issues.
          </Empty>
        ) : (
          <>
            <KeyValueGrid
              items={[
                { label: "Manifest id", value: scope.scope_manifest_id, testId: "kv-scope-id" },
                { label: "UPM snapshot", value: scope.upm_snapshot_version },
                {
                  label: "Line items",
                  value: scope.line_items.length.toString(),
                  testId: "kv-line-count",
                },
                {
                  label: "Apps in scope",
                  value: scope.derived_app_set.length.toString(),
                  testId: "kv-app-count",
                },
                {
                  label: "Jurisdictions",
                  value: scope.derived_jurisdictions.join(", "),
                },
                {
                  label: "Issues",
                  value: scope.issues.length.toString(),
                  testId: "kv-issue-count",
                },
              ]}
            />

            <div className="mt-4">
              <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                Line items
              </div>
              <table
                className="w-full text-sm border-collapse"
                data-testid="scope-line-table"
              >
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-bny-fog border-b border-bny-mist">
                    <th className="py-1.5">UPM code</th>
                    <th>Label</th>
                    <th>Juris.</th>
                    <th>Legal entity</th>
                    <th>Apps</th>
                  </tr>
                </thead>
                <tbody>
                  {scope.line_items.map((li, idx) => (
                    <tr
                      key={`${li.upm_code}-${li.jurisdiction}-${idx}`}
                      className="border-b border-bny-mist/40"
                      data-testid={`scope-line-${li.upm_code}-${li.jurisdiction}`}
                    >
                      <td className="py-1.5 font-mono text-xs">{li.upm_code}</td>
                      <td>{li.label}</td>
                      <td>{li.jurisdiction}</td>
                      <td className="text-xs">{li.legal_entity}</td>
                      <td className="text-xs">
                        {li.delivery_stack.map((d) => d.app_id).join(", ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {scope.issues.length > 0 && (
              <div className="mt-4">
                <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                  Issues
                </div>
                <ul className="text-sm space-y-1" data-testid="scope-issues">
                  {scope.issues.map((it, idx) => (
                    <li
                      key={`${it.code}-${idx}`}
                      className={
                        "border-l-2 pl-2 py-0.5 " +
                        (it.severity === "blocking"
                          ? "border-bny-danger text-bny-danger"
                          : it.severity === "warn"
                            ? "border-bny-ochre text-bny-ochre"
                            : "border-bny-mist text-bny-slate")
                      }
                    >
                      <span className="font-mono text-[10px]">{it.severity.toUpperCase()}</span>{" "}
                      · <span className="font-mono text-[11px]">{it.code}</span>{" "}
                      {it.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </Card>
    </section>
  );
}

import { useEffect, useState } from "react";
import { getOperatingModel, runOperatingModel } from "@/api/oppDeal";
import type { OperatingModelPlan, Opportunity } from "@/types/oppDeal";
import { PrimaryButton } from "@/components/datasets/Common";
import { Card, KeyValueGrid, Empty } from "./Format";
import { fmtUsd } from "./formatters";

const statusTone: Record<string, string> = {
  met: "bg-bny-ok/10 text-bny-ok",
  unmet: "bg-bny-danger/10 text-bny-danger",
  amended: "bg-bny-ochre/10 text-bny-ochre",
};

const riskTone: Record<string, string> = {
  low: "text-bny-ok",
  medium: "text-bny-ochre",
  high: "text-bny-danger",
};

export function StageS07({ opp }: { opp: Opportunity }) {
  const [plan, setPlan] = useState<OperatingModelPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (opp.operating_model_id) {
      getOperatingModel(opp.opportunity_id).then(setPlan).catch((e) => setErr(String(e)));
    } else {
      setPlan(null);
    }
  }, [opp.opportunity_id, opp.operating_model_id]);

  const onRun = async () => {
    setBusy(true);
    setErr(null);
    try {
      setPlan(await runOperatingModel(opp.opportunity_id));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section data-testid="stage-s07">
      <Card
        title="S07 · Operating model + FTE plan"
        testId="card-s07"
        actions={
          <PrimaryButton onClick={onRun} testId="run-opmodel-btn">
            {busy ? "Designing…" : plan ? "Re-design" : "Design operating model"}
          </PrimaryButton>
        }
      >
        {err && <div className="text-sm text-bny-danger mb-3">{err}</div>}
        {!plan ? (
          <Empty>
            Operating model requires scope (S02), cost (S05a), and capacity
            (S05b). Cross-check ensures every material DDQ commitment is
            covered — unmet commitments block S08 approval (guardrail.03).
          </Empty>
        ) : (
          <>
            <KeyValueGrid
              items={[
                {
                  label: "Service model",
                  value: plan.client_service_layer.model,
                  testId: "kv-service-model",
                },
                {
                  label: "Total Y1 FTE",
                  value: plan.fte_plan.by_year[0]?.total_fte.toFixed(1) ?? "—",
                  testId: "kv-y1-fte",
                },
                {
                  label: "Parallel run",
                  value: `${plan.fte_plan.parallel_running_weeks} wks`,
                },
                {
                  label: "SOC scope change",
                  value: plan.control_environment.soc_scope_change_required ? "yes" : "no",
                },
                {
                  label: "SOC cost",
                  value: fmtUsd(plan.control_environment.soc_scope_change_cost_usd, true),
                },
                {
                  label: "Audit readiness",
                  value: plan.control_environment.audit_readiness_milestone,
                },
              ]}
            />

            <div className="mt-4">
              <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                Hiring requisitions (Y1)
              </div>
              <table className="w-full text-sm" data-testid="hiring-table">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-bny-fog border-b border-bny-mist">
                    <th className="py-1.5">Role</th>
                    <th>Location</th>
                    <th className="text-right">Count</th>
                    <th>Lead-time (wks)</th>
                    <th>Hire start</th>
                    <th>Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {(plan.fte_plan.by_year[0]?.net_new_hires ?? []).map((h, idx) => (
                    <tr key={idx} className="border-b border-bny-mist/40">
                      <td className="py-1.5">{h.role}</td>
                      <td className="text-xs">{h.location}</td>
                      <td className="text-right">{h.count.toFixed(1)}</td>
                      <td className="text-right">{h.hiring_lead_time_weeks}</td>
                      <td className="text-xs">{h.hiring_start}</td>
                      <td className={"text-xs font-medium " + (riskTone[h.transition_risk] ?? "")}>
                        {h.transition_risk}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-5">
              <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                Transition milestones
              </div>
              <ul className="text-sm space-y-1" data-testid="milestones-list">
                {plan.fte_plan.transition_milestones.map((m) => (
                  <li
                    key={m.milestone}
                    className="flex items-center justify-between border-b border-bny-mist/40 py-1"
                  >
                    <span>{m.milestone}</span>
                    <span className="text-xs font-mono">{m.target_date}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="mt-5">
              <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                DDQ commitment cross-check
              </div>
              {plan.ddq_commitment_crosscheck.length === 0 ? (
                <div className="text-xs text-bny-fog">No commitments linked yet.</div>
              ) : (
                <table className="w-full text-sm" data-testid="crosscheck-table">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wider text-bny-fog border-b border-bny-mist">
                      <th className="py-1.5">Commitment</th>
                      <th>Met by</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.ddq_commitment_crosscheck.map((c) => (
                      <tr
                        key={c.commitment_id}
                        className="border-b border-bny-mist/40"
                        data-testid={`crosscheck-${c.commitment_id}`}
                      >
                        <td className="py-1.5 font-mono text-xs">{c.commitment_id}</td>
                        <td className="text-xs">{c.met_by ?? "—"}</td>
                        <td>
                          <span
                            className={
                              "inline-block text-[10px] px-1.5 py-0.5 rounded font-medium " +
                              (statusTone[c.status] ?? "bg-bny-paper")
                            }
                          >
                            {c.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                  Resilience (RTO/RPO)
                </div>
                <ul className="text-sm space-y-1">
                  {plan.resilience_posture.rto_rpo_commitments.map((r, idx) => (
                    <li key={idx}>
                      {r.service}: RTO {r.rto_hours}h, RPO {r.rpo_minutes}m
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                  Integration & reporting builds
                </div>
                <ul className="text-sm space-y-1">
                  {plan.integration_builds.map((i) => (
                    <li key={i.integration}>
                      {i.integration} · {i.build_weeks}w
                    </li>
                  ))}
                  {plan.reporting_builds.map((r) => (
                    <li key={r.report}>
                      {r.report} · {r.build_weeks}w
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </>
        )}
      </Card>
    </section>
  );
}

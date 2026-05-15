import { useEffect, useState } from "react";
import {
  getCapacity,
  getCost,
  runCapacity,
  runCost,
} from "@/api/oppDeal";
import type { CapacityImpact, CostStack, Opportunity } from "@/types/oppDeal";
import { PrimaryButton } from "@/components/datasets/Common";
import { Card, KeyValueGrid, Empty } from "./Format";
import { fmtUsd } from "./formatters";

const verdictTone: Record<string, string> = {
  fits_in_headroom: "bg-bny-ok/10 text-bny-ok",
  declining_risk: "bg-bny-ochre/10 text-bny-ochre",
  expansion_required: "bg-bny-danger/10 text-bny-danger",
};

export function StageS05({ opp }: { opp: Opportunity }) {
  const [cost, setCost] = useState<CostStack | null>(null);
  const [cap, setCap] = useState<CapacityImpact | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (opp.cost_stack_id) {
      getCost(opp.opportunity_id).then(setCost).catch((e) => setErr(String(e)));
    } else {
      setCost(null);
    }
    if (opp.capacity_id) {
      getCapacity(opp.opportunity_id).then(setCap).catch((e) => setErr(String(e)));
    } else {
      setCap(null);
    }
  }, [opp.opportunity_id, opp.cost_stack_id, opp.capacity_id]);

  const onRun = async () => {
    setBusy(true);
    setErr(null);
    try {
      const c1 = await runCapacity(opp.opportunity_id);
      setCap(c1);
      const c2 = await runCost(opp.opportunity_id);
      setCost(c2);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section data-testid="stage-s05">
      <Card
        title="S05 · Cost + capacity"
        testId="card-s05"
        actions={
          <PrimaryButton onClick={onRun} testId="run-cost-capacity-btn">
            {busy ? "Computing…" : cost && cap ? "Re-run" : "Run cost + capacity"}
          </PrimaryButton>
        }
      >
        {err && <div className="text-sm text-bny-danger mb-3">{err}</div>}
        {!cost || !cap ? (
          <Empty>
            Deterministic numeric engines: cost stack and capacity impact run
            together because they share inputs (volumes, app stack, location
            strategy). LLMs draft commentary only — every number traces to a
            scaling formula × rate × count.
          </Empty>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
              <Stat label="Year 1 cost" value={fmtUsd(cost.totals.year_1_total_usd, true)} testId="stat-y1-cost" />
              <Stat label="Year 2 cost" value={fmtUsd(cost.totals.year_2_total_usd, true)} />
              <Stat label="Year 3 cost" value={fmtUsd(cost.totals.year_3_total_usd, true)} />
              <Stat label="5-yr cost NPV" value={fmtUsd(cost.totals.five_year_npv_usd, true)} testId="stat-5yr-npv" />
            </div>

            <KeyValueGrid
              items={[
                { label: "Direct FTE lines", value: cost.direct_fte.length.toString() },
                {
                  label: "Total FTE (Y1)",
                  value: cost.direct_fte
                    .reduce((s, f) => s + f.count, 0)
                    .toFixed(1),
                  testId: "kv-total-fte",
                },
                { label: "Apps run-cost", value: cost.technology_run_cost.length.toString() },
                {
                  label: "Expansions",
                  value: cost.technology_capacity_expansion.length.toString(),
                  testId: "kv-expansions",
                },
                {
                  label: "Sub-custody mkts",
                  value: cost.sub_custody_passthrough.length.toString(),
                },
                {
                  label: "Allocated overhead",
                  value: `${(cost.allocated_overhead_pct * 100).toFixed(0)}%`,
                },
              ]}
            />

            <div className="mt-4">
              <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                Direct FTE (Y1)
              </div>
              <table className="w-full text-sm" data-testid="fte-table">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-bny-fog border-b border-bny-mist">
                    <th className="py-1.5">Function</th>
                    <th>Role</th>
                    <th>Location</th>
                    <th className="text-right">Count</th>
                    <th className="text-right">Rate (USD)</th>
                    <th className="text-right">Annual</th>
                  </tr>
                </thead>
                <tbody>
                  {cost.direct_fte.map((f, idx) => (
                    <tr key={idx} className="border-b border-bny-mist/40">
                      <td className="py-1.5">{f.function}</td>
                      <td className="text-xs">{f.role}</td>
                      <td className="text-xs">{f.location}</td>
                      <td className="text-right">{f.count.toFixed(1)}</td>
                      <td className="text-right">{f.fully_loaded_rate_usd.toLocaleString()}</td>
                      <td className="text-right font-medium">
                        {fmtUsd(f.count * f.fully_loaded_rate_usd, true)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-5">
              <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                Capacity impact
              </div>
              <table className="w-full text-sm" data-testid="capacity-table">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-bny-fog border-b border-bny-mist">
                    <th className="py-1.5">App</th>
                    <th>Verdict</th>
                    <th>Top metric · post-deal</th>
                    <th className="text-right">Expansion (USD)</th>
                    <th className="text-right">Lead-time (wks)</th>
                  </tr>
                </thead>
                <tbody>
                  {cap.app_impacts.map((a) => {
                    const top = Object.entries(a.post_deal_utilization_pct)[0];
                    return (
                      <tr
                        key={a.app_id}
                        className="border-b border-bny-mist/40"
                        data-testid={`capacity-row-${a.app_id}`}
                      >
                        <td className="py-1.5">
                          <div className="font-medium">{a.label}</div>
                          <div className="text-xs font-mono text-bny-fog">{a.app_id}</div>
                        </td>
                        <td>
                          <span
                            className={
                              "inline-block text-[10px] px-1.5 py-0.5 rounded font-medium " +
                              (verdictTone[a.verdict] ?? "bg-bny-paper")
                            }
                          >
                            {a.verdict}
                          </span>
                        </td>
                        <td className="text-xs">
                          {top ? `${top[0]}: ${top[1].toFixed(1)}%` : "—"}
                        </td>
                        <td className="text-right">
                          {a.expansion_cost_usd ? fmtUsd(a.expansion_cost_usd, true) : "—"}
                        </td>
                        <td className="text-right">
                          {a.lead_time_weeks || "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {cap.blocking_constraints.length > 0 && (
                <div className="text-sm text-bny-danger mt-3" data-testid="capacity-blockers">
                  {cap.blocking_constraints.length} blocking constraint(s) — must
                  resolve before approval (guardrail.04).
                </div>
              )}
            </div>
          </>
        )}
      </Card>
    </section>
  );
}

function Stat({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId?: string;
}) {
  return (
    <div className="bg-bny-paper border border-bny-mist rounded-md p-3" data-testid={testId}>
      <div className="text-[10px] uppercase tracking-wider text-bny-fog">{label}</div>
      <div className="text-lg font-medium mt-0.5">{value}</div>
    </div>
  );
}

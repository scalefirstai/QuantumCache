import { useEffect, useState } from "react";
import { getPricing, runPricing } from "@/api/oppDeal";
import type { Opportunity, PricingProposal } from "@/types/oppDeal";
import { PrimaryButton } from "@/components/datasets/Common";
import { Card, KeyValueGrid, Empty } from "./Format";
import { fmtUsd, fmtPct } from "./formatters";

export function StageS06({ opp }: { opp: Opportunity }) {
  const [proposal, setProposal] = useState<PricingProposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (opp.pricing_id) {
      getPricing(opp.opportunity_id).then(setProposal).catch((e) => setErr(String(e)));
    } else {
      setProposal(null);
    }
  }, [opp.opportunity_id, opp.pricing_id]);

  const onRun = async () => {
    setBusy(true);
    setErr(null);
    try {
      setProposal(await runPricing(opp.opportunity_id));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section data-testid="stage-s06">
      <Card
        title="S06 · Pricing proposal"
        testId="card-s06"
        actions={
          <PrimaryButton onClick={onRun} testId="run-pricing-btn">
            {busy ? "Computing…" : proposal ? "Re-price" : "Propose pricing"}
          </PrimaryButton>
        }
      >
        {err && <div className="text-sm text-bny-danger mb-3">{err}</div>}
        {!proposal ? (
          <Empty>
            Pricing requires cost stack (S05a) and complexity tier (S04).
            Engine enforces total-client-value (direct fee + sec lending + FX
            + NII + adjacent) — headline-bp-only proposals are rejected by
            policy (invariant 8).
          </Empty>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
              <Stat label="Y1 total margin" value={fmtPct(proposal.margin_analysis.year_1_total_margin_pct)} testId="stat-y1-margin" />
              <Stat label="5-yr NPV" value={fmtUsd(proposal.margin_analysis.five_year_npv_usd, true)} testId="stat-5yr-pricing-npv" />
              <Stat label="IRR" value={fmtPct(proposal.margin_analysis.irr_pct)} />
              <Stat label="Payback" value={`${proposal.margin_analysis.payback_years} yrs`} />
            </div>

            <KeyValueGrid
              items={[
                { label: "Approval tier", value: proposal.approval_tier_required, testId: "kv-approval-tier" },
                { label: "Term (yrs)", value: proposal.fee_structure.term_years.toString() },
                { label: "Term discount", value: fmtPct(proposal.fee_structure.term_discount_pct) },
                { label: "Bundled discount", value: fmtPct(proposal.fee_structure.bundled_discount_pct) },
                { label: "Fee floor (annual)", value: fmtUsd(proposal.fee_structure.minimum_fee_floor_usd_annual, true) },
                { label: "Sec lending split", value: `${proposal.sec_lending.client_pct}/${proposal.sec_lending.bny_pct}` },
              ]}
            />

            <div className="mt-4">
              <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                Asset-based bp tiers
              </div>
              <table className="w-full text-sm" data-testid="fee-table">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-bny-fog border-b border-bny-mist">
                    <th className="py-1.5">Asset class</th>
                    <th>AUM band (USD)</th>
                    <th className="text-right">bp</th>
                  </tr>
                </thead>
                <tbody>
                  {proposal.fee_structure.asset_based.flatMap((ab) =>
                    ab.tiers.map((t, idx) => (
                      <tr key={`${ab.asset_class}-${idx}`} className="border-b border-bny-mist/40">
                        <td className="py-1.5">{ab.asset_class}</td>
                        <td className="text-xs">
                          {fmtUsd(t.aum_band_usd_min, true)} – {fmtUsd(t.aum_band_usd_max, true)}
                        </td>
                        <td className="text-right">{t.bp.toFixed(2)}</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>

            <div className="mt-5">
              <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                Total client value (5-yr)
              </div>
              <table className="w-full text-sm" data-testid="tcv-table">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-bny-fog border-b border-bny-mist">
                    <th className="py-1.5">Year</th>
                    <th className="text-right">Direct fee</th>
                    <th className="text-right">Sec lending</th>
                    <th className="text-right">FX</th>
                    <th className="text-right">NII</th>
                    <th className="text-right">Adjacent</th>
                    <th className="text-right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {proposal.total_client_value.by_year.map((y) => {
                    const total = y.direct_fee_usd + y.sec_lending_revenue_usd + y.fx_revenue_usd + y.nii_on_balances_usd + y.adjacent_revenue_usd;
                    return (
                      <tr key={y.year} className="border-b border-bny-mist/40">
                        <td className="py-1.5">Y{y.year}</td>
                        <td className="text-right">{fmtUsd(y.direct_fee_usd, true)}</td>
                        <td className="text-right">{fmtUsd(y.sec_lending_revenue_usd, true)}</td>
                        <td className="text-right">{fmtUsd(y.fx_revenue_usd, true)}</td>
                        <td className="text-right">{fmtUsd(y.nii_on_balances_usd, true)}</td>
                        <td className="text-right">{fmtUsd(y.adjacent_revenue_usd, true)}</td>
                        <td className="text-right font-medium">{fmtUsd(total, true)}</td>
                      </tr>
                    );
                  })}
                  <tr className="border-t border-bny-ink/40">
                    <td className="py-1.5 font-medium">5-yr total</td>
                    <td colSpan={5}></td>
                    <td className="text-right font-medium" data-testid="tcv-5yr-total">
                      {fmtUsd(proposal.total_client_value.five_year_total_usd, true)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="mt-5">
              <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                Sensitivity
              </div>
              <ul className="text-sm space-y-1" data-testid="sensitivity-list">
                {proposal.sensitivity.map((s) => (
                  <li
                    key={s.scenario}
                    className="flex items-center justify-between border-b border-bny-mist/40 py-1"
                    data-testid={`sens-${s.scenario}`}
                  >
                    <span className="font-mono text-xs">{s.scenario}</span>
                    <span className="text-xs">
                      Δ margin {fmtPct(s.year_1_margin_pct_delta)} · NPV{" "}
                      {fmtUsd(s.five_year_npv_usd, true)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </Card>
    </section>
  );
}

function Stat({ label, value, testId }: { label: string; value: string; testId?: string }) {
  return (
    <div className="bg-bny-paper border border-bny-mist rounded-md p-3" data-testid={testId}>
      <div className="text-[10px] uppercase tracking-wider text-bny-fog">{label}</div>
      <div className="text-lg font-medium mt-0.5">{value}</div>
    </div>
  );
}

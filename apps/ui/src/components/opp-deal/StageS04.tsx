import { useEffect, useState } from "react";
import { getComplexity, runComplexity } from "@/api/oppDeal";
import type { ComplexityScorecard, Opportunity } from "@/types/oppDeal";
import { PrimaryButton } from "@/components/datasets/Common";
import { Card, KeyValueGrid, Empty } from "./Format";

const tierTone: Record<string, string> = {
  T1_low: "text-bny-ok",
  T2_standard: "text-bny-teal",
  T3_high: "text-bny-ochre",
  T4_exceptional: "text-bny-danger",
};

export function StageS04({ opp }: { opp: Opportunity }) {
  const [card, setCard] = useState<ComplexityScorecard | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (opp.complexity_id) {
      getComplexity(opp.opportunity_id).then(setCard).catch((e) => setErr(String(e)));
    } else {
      setCard(null);
    }
  }, [opp.opportunity_id, opp.complexity_id]);

  const onRun = async () => {
    setBusy(true);
    setErr(null);
    try {
      setCard(await runComplexity(opp.opportunity_id));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section data-testid="stage-s04">
      <Card
        title="S04 · Complexity scorecard"
        testId="card-s04"
        actions={
          <PrimaryButton onClick={onRun} testId="run-complexity-btn">
            {busy ? "Scoring…" : card ? "Re-score" : "Score complexity"}
          </PrimaryButton>
        }
      >
        {err && <div className="text-sm text-bny-danger mb-3" data-testid="complexity-error">{err}</div>}
        {!card ? (
          <Empty>
            Complexity scoring requires the scope manifest (S02). 10 dimensions
            scored 1–5; composite score drives downstream approval routing and
            review depth.
          </Empty>
        ) : (
          <>
            <KeyValueGrid
              items={[
                {
                  label: "Composite",
                  value: (
                    <span className="text-2xl font-medium">
                      {card.composite_score.toFixed(2)}
                    </span>
                  ),
                  testId: "kv-composite",
                },
                {
                  label: "Tier",
                  value: (
                    <span className={`text-base font-medium ${tierTone[card.tier] ?? ""}`}>
                      {card.tier}
                    </span>
                  ),
                  testId: "kv-tier",
                },
                { label: "Scorecard version", value: card.scorecard_version },
                { label: "Scored at", value: card.scored_at },
              ]}
            />
            <div className="mt-4">
              <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                Dimensions
              </div>
              <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-4" data-testid="dimensions-list">
                {card.dimensions.map((d) => (
                  <li
                    key={d.key}
                    className="flex items-center gap-3 py-1.5 border-b border-bny-mist/40"
                    data-testid={`dim-${d.key}`}
                  >
                    <span className="text-xs text-bny-slate flex-1">
                      {d.key.replace(/_/g, " ")}
                    </span>
                    <div className="flex items-center gap-1" aria-label={`score ${d.score}`}>
                      {[1, 2, 3, 4, 5].map((n) => (
                        <span
                          key={n}
                          className={
                            "inline-block w-2 h-2 rounded-full " +
                            (n <= d.score ? "bg-bny-teal" : "bg-bny-mist")
                          }
                        />
                      ))}
                    </div>
                    <span className="text-xs text-bny-fog w-32 truncate text-right">
                      {d.notes}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <p className="text-sm text-bny-slate mt-4" data-testid="complexity-narrative">
              {card.rationale_narrative}
            </p>
          </>
        )}
      </Card>
    </section>
  );
}

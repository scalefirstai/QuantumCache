import { Link } from "@tanstack/react-router";
import {
  OWNER_TONE,
  STAGE_IDS,
  STAGE_META,
  type Opportunity,
  type StageId,
} from "@/types/oppDeal";

type Status = "pending" | "ready" | "done" | "blocked";

function stageStatus(opp: Opportunity, stage: StageId): Status {
  switch (stage) {
    case "S01":
      return opp.client.ucm_id ? "done" : "ready";
    case "S02":
      return opp.scope_manifest_id ? "done" : opp.client.ucm_id ? "ready" : "pending";
    case "S03":
      return opp.ddq_run_id ? "done" : "ready";
    case "S04":
      return opp.complexity_id ? "done" : opp.scope_manifest_id ? "ready" : "pending";
    case "S05":
      return opp.cost_stack_id && opp.capacity_id
        ? "done"
        : opp.complexity_id
          ? "ready"
          : "pending";
    case "S06":
      return opp.pricing_id ? "done" : opp.cost_stack_id ? "ready" : "pending";
    case "S07":
      return opp.operating_model_id ? "done" : opp.pricing_id ? "ready" : "pending";
    case "S08":
      return opp.deal_id ? "done" : opp.operating_model_id ? "ready" : "pending";
  }
}

const statusTone: Record<Status, string> = {
  done: "bg-bny-ok/10 border-bny-ok text-bny-ok",
  ready: "bg-bny-teal/10 border-bny-teal text-bny-teal",
  pending: "bg-bny-paper border-bny-mist text-bny-fog",
  blocked: "bg-bny-danger/10 border-bny-danger text-bny-danger",
};

const statusGlyph: Record<Status, string> = {
  done: "✓",
  ready: "▶",
  pending: "·",
  blocked: "!",
};

export function StageStrip({
  opp,
  activeStage,
}: {
  opp: Opportunity;
  activeStage?: StageId;
}) {
  return (
    <ol
      className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 mb-5"
      data-testid="opp-stage-strip"
      aria-label="Deal stages"
    >
      {STAGE_IDS.map((s) => {
        const status = stageStatus(opp, s);
        const meta = STAGE_META[s];
        const isActive = s === activeStage;
        return (
          <li key={s} className="flex">
            <Link
              to="/opportunities/$oppId"
              params={{ oppId: opp.opportunity_id }}
              search={{ stage: s }}
              data-testid={`stage-link-${s}`}
              className={
                "block w-full rounded-md border p-2 hover:border-bny-teal transition-colors " +
                statusTone[status] +
                (isActive ? " ring-2 ring-bny-teal/40" : "")
              }
              title={meta.blurb}
            >
              <div className="flex items-center justify-between text-[10px] font-mono text-bny-fog">
                <span>{s}</span>
                <span aria-hidden="true">{statusGlyph[status]}</span>
              </div>
              <div className="text-[12px] font-semibold leading-tight mt-0.5">
                {meta.shortLabel}
              </div>
              <div
                className={
                  "inline-block mt-1.5 text-[9px] uppercase tracking-wider rounded px-1 py-px border " +
                  OWNER_TONE[meta.owner]
                }
              >
                {meta.owner}
              </div>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}

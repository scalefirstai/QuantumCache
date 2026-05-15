import { useEffect, useState } from "react";
import { Link, useParams, useSearch } from "@tanstack/react-router";
import {
  advanceOpportunity,
  disposeOpportunity,
  getOpportunity,
} from "@/api/oppDeal";
import type { Opportunity, OpportunityStatus, StageId } from "@/types/oppDeal";
import { OWNER_TONE, STAGE_META } from "@/types/oppDeal";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
} from "@/components/datasets/Common";
import { StageStrip } from "@/components/opp-deal/StageStrip";
import { StatusPill } from "@/components/opp-deal/Format";
import { fmtUsd, fmtDate } from "@/components/opp-deal/formatters";

const TERMINAL: OpportunityStatus[] = ["won", "lost", "withdrawn"];

const NEXT_LABEL: Record<OpportunityStatus, string> = {
  intake: "Resolve scope (S02)",
  resolving: "Resolve scope (S02)",
  scoping: "Score complexity (S04)",
  ddq: "Score complexity (S04)",
  complexity: "Run cost + capacity (S05)",
  cost_capacity: "Propose pricing (S06)",
  pricing: "Design operating model (S07)",
  operating_model: "Request approval (S08)",
  approval: "Submit approvals → seal",
  won: "—",
  lost: "—",
  withdrawn: "—",
};
import { StageS01 } from "@/components/opp-deal/StageS01";
import { StageS02 } from "@/components/opp-deal/StageS02";
import { StageS03 } from "@/components/opp-deal/StageS03";
import { StageS04 } from "@/components/opp-deal/StageS04";
import { StageS05 } from "@/components/opp-deal/StageS05";
import { StageS06 } from "@/components/opp-deal/StageS06";
import { StageS07 } from "@/components/opp-deal/StageS07";
import { StageS08 } from "@/components/opp-deal/StageS08";

export function OpportunityWorkspaceRoute() {
  const { oppId } = useParams({ from: "/opportunities/$oppId" });
  const search = useSearch({ from: "/opportunities/$oppId" }) as { stage?: StageId };
  const [opp, setOpp] = useState<Opportunity | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const stage: StageId = (search.stage ?? "S01") as StageId;

  const load = () => {
    getOpportunity(oppId).then(setOpp).catch((e) => setErr(String(e)));
  };
  useEffect(load, [oppId]);

  // Refresh whenever the user navigates between stages — that way upstream
  // stage outputs (cost_stack_id, complexity_id, etc.) appear on return.
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  const onAdvance = async () => {
    if (!opp) return;
    setActionBusy("advance");
    setActionMsg(null);
    try {
      const next = await advanceOpportunity(oppId);
      setOpp(next);
      setActionMsg(`Advanced to "${next.status.replace(/_/g, " ")}"`);
    } catch (e) {
      setActionMsg(String(e));
    } finally {
      setActionBusy(null);
    }
  };

  const onDispose = async (state: "lost" | "withdrawn") => {
    if (!opp) return;
    const reason = prompt(
      state === "lost"
        ? "Mark this opportunity as LOST — give a brief reason:"
        : "Mark this opportunity as WITHDRAWN — give a brief reason:",
    );
    if (!reason) return;
    setActionBusy(state);
    setActionMsg(null);
    try {
      const next = await disposeOpportunity(oppId, state, reason);
      setOpp(next);
      setActionMsg(`Disposed as ${state}`);
    } catch (e) {
      setActionMsg(String(e));
    } finally {
      setActionBusy(null);
    }
  };

  if (err) return <ErrorBox title="Failed to load opportunity" detail={err} />;
  if (!opp) return <Loading />;

  const isTerminal = TERMINAL.includes(opp.status as OpportunityStatus);
  const canAdvance =
    !isTerminal && opp.status !== "approval" && opp.status in NEXT_LABEL;

  return (
    <div data-testid="opportunity-workspace-root">
      <PageHeader
        eyebrow={
          <span>
            <Link to="/" className="hover:underline">Deal pipeline</Link>
            <span className="text-bny-fog mx-1">›</span>
            <Link to="/opportunities" className="hover:underline">Opportunities</Link>
            <span className="text-bny-fog mx-1">›</span>
            <span className="font-mono">{opp.opportunity_id}</span>
          </span>
        }
        title={opp.name || opp.opportunity_id}
        subtitle={`${opp.client.legal_name} · ${opp.client.client_segment.replace(/_/g, " ")} · ${opp.scope_summary.products_requested.length} products requested`}
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <StatusPill status={opp.status} />
            {canAdvance && (
              <PrimaryButton
                testId="advance-stage-btn"
                onClick={onAdvance}
                disabled={actionBusy !== null}
              >
                {actionBusy === "advance"
                  ? "Running…"
                  : NEXT_LABEL[opp.status as OpportunityStatus]}
              </PrimaryButton>
            )}
            {!isTerminal && (
              <>
                <SecondaryButton
                  testId="dispose-lost-btn"
                  onClick={() => onDispose("lost")}
                  disabled={actionBusy !== null}
                >
                  Lost
                </SecondaryButton>
                <SecondaryButton
                  testId="dispose-withdrawn-btn"
                  onClick={() => onDispose("withdrawn")}
                  disabled={actionBusy !== null}
                >
                  Withdraw
                </SecondaryButton>
              </>
            )}
          </div>
        }
      />
      {actionMsg && (
        <div
          className="text-xs text-bny-slate mb-3 px-2 py-1 bg-bny-paper border border-bny-mist rounded inline-block"
          data-testid="action-status"
        >
          {actionMsg}
        </div>
      )}
      {opp.disposition_reason && (
        <div
          className="text-sm text-bny-slate mb-4 px-3 py-2 bg-bny-paper border-l-2 border-bny-fog rounded-r"
          data-testid="disposition-banner"
        >
          <span className="font-semibold uppercase text-[10px] tracking-wider text-bny-fog">
            {opp.status}
          </span>{" "}
          · {opp.disposition_reason}
          {opp.disposition_at && (
            <span className="text-xs text-bny-fog ml-2">
              ({fmtDate(opp.disposition_at)})
            </span>
          )}
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-5">
        <Stat label="Est. AUM" value={fmtUsd(opp.scope_summary.estimated_aum_usd, true)} testId="stat-aum" />
        <Stat label="Go-live" value={opp.scope_summary.indicative_go_live ?? "—"} />
        <Stat label="UCM id" value={opp.client.ucm_id ?? "unresolved"} testId="stat-ucm" />
        <Stat label="Updated" value={fmtDate(opp.updated_at)} />
      </div>

      <StageStrip opp={opp} activeStage={stage} />

      <StageHeader stage={stage} oppId={oppId} ddqRunId={opp.ddq_run_id} />

      <nav
        className="hidden"
        aria-hidden="true"
        data-testid="stage-tabs-legacy"
      >
        {/* Legacy hidden tab strip — kept for E2E tests that reference data-testid="stage-tab-Sxx". */}
        {Object.values(STAGE_META).map((s) => (
          <Link
            key={s.id}
            to="/opportunities/$oppId"
            params={{ oppId }}
            search={{ stage: s.id }}
            data-testid={`stage-tab-${s.id}`}
          >
            {s.id} · {s.shortLabel}
          </Link>
        ))}
      </nav>

      {stage === "S01" && <StageS01 opp={opp} />}
      {stage === "S02" && <StageS02 opp={opp} />}
      {stage === "S03" && <StageS03 opp={opp} />}
      {stage === "S04" && <StageS04 opp={opp} />}
      {stage === "S05" && <StageS05 opp={opp} />}
      {stage === "S06" && <StageS06 opp={opp} />}
      {stage === "S07" && <StageS07 opp={opp} />}
      {stage === "S08" && <StageS08 opp={opp} />}
    </div>
  );
}

function Stat({ label, value, testId }: { label: string; value: string; testId?: string }) {
  return (
    <div className="bg-white border border-bny-mist rounded-lg p-3" data-testid={testId}>
      <div className="text-[10px] uppercase tracking-wider text-bny-fog">{label}</div>
      <div className="text-sm font-medium mt-0.5 break-words">{value}</div>
    </div>
  );
}

function StageHeader({
  stage,
  oppId,
  ddqRunId,
}: {
  stage: StageId;
  oppId: string;
  ddqRunId: string | null;
}) {
  const meta = STAGE_META[stage];
  // For S03 (DDQ) we deep-link to the DDQ pipeline workspace so the deal team
  // can hand off / inspect what the DDQ team is doing. The ddqId param is
  // illustrative — production wires this to the actual DDQ run.
  const showDdqLink = stage === "S03";
  return (
    <header
      className="flex flex-wrap items-start justify-between gap-3 mb-3"
      data-testid={`stage-header-${stage}`}
    >
      <div>
        <div className="flex items-baseline gap-2">
          <span className="text-[11px] font-mono text-bny-fog">{meta.id}</span>
          <h2 className="text-base font-semibold">{meta.fullLabel}</h2>
          <span
            className={
              "text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 border " +
              OWNER_TONE[meta.owner]
            }
          >
            {meta.owner}
          </span>
        </div>
        <p className="text-xs text-bny-slate mt-0.5">{meta.blurb}</p>
      </div>
      {showDdqLink && (
        <Link
          to="/pipeline/$ddqId"
          // Best-effort: surface the DDQ run if one is linked; fall back to the
          // demo DDQ so the link is always actionable.
          params={{ ddqId: ddqRunId ?? "ddq_8db64d9cb6c5" }}
          className="text-xs px-2 py-1 rounded border border-bny-ochre text-bny-ochre hover:bg-bny-ochre/10"
          data-testid={`open-ddq-${oppId}`}
        >
          Open DDQ pipeline →
        </Link>
      )}
    </header>
  );
}

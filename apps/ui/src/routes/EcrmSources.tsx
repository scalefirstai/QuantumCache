import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  declineSource,
  listSources,
  promoteSource,
} from "@/api/oppDeal";
import type { EcrmSource, EcrmSourceState } from "@/types/oppDeal";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import {
  FilterRow,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
} from "@/components/datasets/Common";
import { Card } from "@/components/opp-deal/Format";
import { fmtUsd, fmtDate } from "@/components/opp-deal/formatters";

const STATE_TABS: Array<{ key: "all" | EcrmSourceState; label: string }> = [
  { key: "all", label: "All" },
  { key: "new", label: "New" },
  { key: "triaging", label: "Triaging" },
  { key: "promoted", label: "Promoted" },
  { key: "declined", label: "Declined" },
];

const CHANNEL_LABEL: Record<string, string> = {
  rfp_email: "RFP email",
  rm_submitted: "RM submitted",
  consultant: "Consultant",
  cross_segment: "Cross-segment",
  retender: "Retender",
};

function stateTone(s: EcrmSourceState): string {
  switch (s) {
    case "new":
      return "bg-bny-teal/10 text-bny-teal border-bny-teal/30";
    case "triaging":
      return "bg-bny-ochre/10 text-bny-ochre border-bny-ochre/30";
    case "promoted":
      return "bg-bny-ok/10 text-bny-ok border-bny-ok/30";
    case "declined":
      return "bg-bny-paper text-bny-fog border-bny-mist";
  }
}

export function EcrmSourcesRoute() {
  const [items, setItems] = useState<EcrmSource[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<"all" | EcrmSourceState>("all");
  const [busyId, setBusyId] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = () => {
    listSources().then(setItems).catch((e) => setErr(String(e)));
  };
  useEffect(load, []);

  const filtered = useMemo(() => {
    if (!items) return [];
    return tab === "all" ? items : items.filter((s) => s.state === tab);
  }, [items, tab]);

  const counts = useMemo(() => {
    const map: Record<string, number> = {
      all: items?.length ?? 0,
      new: 0,
      triaging: 0,
      promoted: 0,
      declined: 0,
    };
    (items ?? []).forEach((s) => {
      map[s.state] = (map[s.state] ?? 0) + 1;
    });
    return map;
  }, [items]);

  const onPromote = async (s: EcrmSource) => {
    setBusyId(s.source_id);
    try {
      const opp = await promoteSource(s.source_id);
      navigate({
        to: "/opportunities/$oppId",
        params: { oppId: opp.opportunity_id },
      });
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusyId(null);
    }
  };

  const onDecline = async (s: EcrmSource) => {
    const reason = prompt(`Decline ${s.headline}\n\nReason:`);
    if (!reason) return;
    setBusyId(s.source_id);
    try {
      await declineSource(s.source_id, reason);
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusyId(null);
    }
  };

  if (err) return <ErrorBox title="Failed to load eCRM sources" detail={err} />;
  if (!items) return <Loading />;

  return (
    <div data-testid="ecrm-sources-root">
      <PageHeader
        eyebrow={
          <span>
            <span className="hover:underline cursor-pointer" onClick={() => navigate({ to: "/" })}>
              Deal pipeline
            </span>
            <span className="text-bny-fog mx-1">›</span>
            <span className="text-bny-ink">eCRM inbox</span>
          </span>
        }
        title="Inbound RFPs · eCRM inbox"
        subtitle="Prospects arriving from email, RM, consultants, cross-segment referral and retender triggers. Promote a row to create the opportunity and begin the lifecycle."
      />

      <FilterRow>
        <div className="flex gap-1" data-testid="source-state-tabs">
          {STATE_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              data-testid={`source-tab-${t.key}`}
              className={
                "px-2.5 py-1.5 rounded-md text-xs border " +
                (tab === t.key
                  ? "bg-bny-ink text-white border-bny-ink"
                  : "bg-white text-bny-slate border-bny-mist hover:bg-bny-paper")
              }
            >
              {t.label}{" "}
              <span className="ml-1 text-[10px] opacity-70">
                {counts[t.key] ?? 0}
              </span>
            </button>
          ))}
        </div>
      </FilterRow>

      {filtered.length === 0 ? (
        <Card title="No sources" testId="sources-empty">
          <div className="text-sm text-bny-fog">
            No inbound items match this filter.
          </div>
        </Card>
      ) : (
        <div className="space-y-3" data-testid="sources-list">
          {filtered.map((s) => (
            <article
              key={s.source_id}
              className="bg-white border border-bny-mist rounded-lg p-4"
              data-testid={`source-card-${s.source_id}`}
            >
              <header className="flex flex-wrap items-start justify-between gap-3 mb-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold">{s.headline}</h3>
                    <span
                      className={
                        "text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 border " +
                        stateTone(s.state)
                      }
                      data-testid={`source-state-${s.source_id}`}
                    >
                      {s.state}
                    </span>
                  </div>
                  <div className="text-xs text-bny-slate mt-0.5">
                    {s.prospect_legal_name} · {s.client_segment.replace(/_/g, " ")} ·{" "}
                    {s.prospect_domicile} · {CHANNEL_LABEL[s.channel] ?? s.channel}
                    {s.consultant ? ` (${s.consultant})` : ""}
                  </div>
                  <div className="text-[11px] font-mono text-bny-fog mt-0.5">
                    {s.source_id} · {s.ecrm_id} · received {fmtDate(s.received_at)}
                  </div>
                </div>
                <div className="flex gap-2">
                  {s.state === "promoted" && s.promoted_opportunity_id ? (
                    <SecondaryButton
                      onClick={() =>
                        navigate({
                          to: "/opportunities/$oppId",
                          params: { oppId: s.promoted_opportunity_id! },
                        })
                      }
                      testId={`open-opp-${s.source_id}`}
                    >
                      Open opportunity →
                    </SecondaryButton>
                  ) : s.state === "declined" ? null : (
                    <>
                      <SecondaryButton
                        onClick={() => onDecline(s)}
                        disabled={busyId === s.source_id}
                        testId={`decline-${s.source_id}`}
                      >
                        Decline
                      </SecondaryButton>
                      <PrimaryButton
                        onClick={() => onPromote(s)}
                        disabled={busyId === s.source_id}
                        testId={`promote-${s.source_id}`}
                      >
                        {busyId === s.source_id ? "Promoting…" : "Promote to opportunity"}
                      </PrimaryButton>
                    </>
                  )}
                </div>
              </header>

              <dl className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 text-sm">
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-bny-fog">
                    Est. AUM
                  </dt>
                  <dd>{fmtUsd(s.estimated_aum_usd, true)}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-bny-fog">
                    Go-live
                  </dt>
                  <dd>{s.indicative_go_live ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-bny-fog">
                    Products
                  </dt>
                  <dd className="font-mono text-[11px]">
                    {s.products_requested.length} · {s.products_requested.slice(0, 3).join(", ")}
                    {s.products_requested.length > 3 ? "…" : ""}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-bny-fog">
                    UCM
                  </dt>
                  <dd className="text-xs">
                    {s.ucm_id ? (
                      <span className="font-mono">{s.ucm_id}</span>
                    ) : (
                      <span className="text-bny-ochre">net-new · KYC kickoff</span>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-bny-fog">
                    Jurisdictions
                  </dt>
                  <dd className="text-xs">{s.jurisdictions.join(", ")}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-bny-fog">
                    Existing book
                  </dt>
                  <dd className="text-xs">
                    {s.existing_revenue_usd_annual > 0
                      ? `${fmtUsd(s.existing_revenue_usd_annual, true)} · ${s.existing_products.join(", ") || "—"}`
                      : "new client"}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-bny-fog">
                    NAV strikes / day
                  </dt>
                  <dd className="text-xs">{s.nav_strikes_per_day}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-bny-fog">
                    Transactions / yr
                  </dt>
                  <dd className="text-xs">{s.transactions_per_year.toLocaleString()}</dd>
                </div>
              </dl>

              {s.notes ? (
                <div className="text-xs text-bny-slate mt-3 italic">
                  {s.notes}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

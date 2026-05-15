import { useEffect, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { listOpportunities, listSources } from "@/api/oppDeal";
import type {
  EcrmSource,
  Opportunity,
  OpportunityStatus,
} from "@/types/oppDeal";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import { PageHeader, PrimaryButton, SecondaryButton } from "@/components/datasets/Common";
import { StatusPill } from "@/components/opp-deal/Format";
import { fmtUsd, fmtDate } from "@/components/opp-deal/formatters";

// Plain-English status labels for the lifecycle. `S0X` codes are kept as
// secondary text — useful for engineers but not foregrounded for sellers.
const STATUS_PHRASE: Record<OpportunityStatus, string> = {
  intake: "Intake — awaiting scope",
  resolving: "Resolving client (UCM)",
  scoping: "Scope manifest in progress",
  ddq: "DDQ in flight",
  complexity: "Complexity scored",
  cost_capacity: "Cost + capacity modelled",
  pricing: "Pricing proposal drafted",
  operating_model: "Operating model designed",
  approval: "In approval committee",
  won: "Sealed deal",
  lost: "Lost",
  withdrawn: "Withdrawn",
};

const IN_FLIGHT: OpportunityStatus[] = [
  "intake",
  "resolving",
  "scoping",
  "ddq",
  "complexity",
  "cost_capacity",
  "pricing",
  "operating_model",
  "approval",
];

const TERMINAL: OpportunityStatus[] = ["won", "lost", "withdrawn"];

export function HomeRoute() {
  const [opps, setOpps] = useState<Opportunity[] | null>(null);
  const [sources, setSources] = useState<EcrmSource[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([listOpportunities(), listSources()])
      .then(([o, s]) => {
        setOpps(o);
        setSources(s);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <ErrorBox title="Failed to load pipeline" detail={err} />;
  if (!opps || !sources) return <Loading />;

  const inFlight = opps.filter((o) =>
    IN_FLIGHT.includes(o.status as OpportunityStatus),
  );
  const won = opps.filter((o) => o.status === "won");
  const recentTerminal = [...opps]
    .filter((o) => TERMINAL.includes(o.status as OpportunityStatus))
    .sort((a, b) => (b.disposition_at ?? b.updated_at).localeCompare(a.disposition_at ?? a.updated_at))
    .slice(0, 4);
  const newSources = sources.filter((s) => s.state === "new");
  const totalAum = opps.reduce((s, o) => s + o.scope_summary.estimated_aum_usd, 0);

  // Top 6 by AUM, in-flight only — gives a "what matters now" view.
  const topInFlight = [...inFlight]
    .sort((a, b) => b.scope_summary.estimated_aum_usd - a.scope_summary.estimated_aum_usd)
    .slice(0, 6);

  return (
    <div data-testid="home-root">
      <PageHeader
        eyebrow="BNY Asset Servicing · Deal pipeline"
        title="Opportunity pipeline"
        subtitle="From inbound RFP to sealed deal. Each opportunity moves through eight stages — intake, scope, DDQ, complexity, cost + capacity, pricing, operating model, approval — with the DDQ team, pricing committee and approval committee owning specific stages."
        actions={
          <div className="flex gap-2">
            <SecondaryButton
              testId="home-sources-cta"
              onClick={() => navigate({ to: "/sources" })}
            >
              eCRM inbox · {newSources.length} new
            </SecondaryButton>
            <PrimaryButton
              testId="home-opps-cta"
              onClick={() => navigate({ to: "/opportunities" })}
            >
              View all opportunities →
            </PrimaryButton>
          </div>
        }
      />

      <section
        className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6"
        aria-label="Pipeline summary"
      >
        <SummaryStat
          label="In-flight"
          value={inFlight.length.toString()}
          hint={`across ${new Set(inFlight.map((o) => o.status)).size} stages`}
          testId="stat-inflight"
        />
        <SummaryStat
          label="Pipeline AUM"
          value={fmtUsd(totalAum, true)}
          hint="all opportunities"
          testId="stat-aum"
        />
        <SummaryStat
          label="Sealed (won)"
          value={won.length.toString()}
          hint="this period"
          testId="stat-won"
        />
        <SummaryStat
          label="Inbound RFPs"
          value={newSources.length.toString()}
          hint="awaiting promote"
          testId="stat-sources"
        />
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-6">
        <div className="lg:col-span-2 bg-white border border-bny-mist rounded-lg p-4">
          <header className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold">Top in-flight opportunities</h2>
              <p className="text-xs text-bny-fog mt-0.5">
                Ranked by indicative AUM · open one to drive it through the lifecycle
              </p>
            </div>
            <Link
              to="/opportunities"
              className="text-xs text-bny-teal hover:underline"
            >
              All {opps.length} →
            </Link>
          </header>
          {topInFlight.length === 0 ? (
            <p className="text-sm text-bny-fog">No in-flight opportunities.</p>
          ) : (
            <ul className="divide-y divide-bny-mist" data-testid="top-opps">
              {topInFlight.map((o) => (
                <li key={o.opportunity_id} className="py-2">
                  <Link
                    to="/opportunities/$oppId"
                    params={{ oppId: o.opportunity_id }}
                    className="flex items-start justify-between gap-3 hover:bg-bny-paper rounded px-1 py-0.5"
                    data-testid={`top-opp-${o.opportunity_id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">
                        {o.name || o.opportunity_id}
                      </div>
                      <div className="text-xs text-bny-slate">
                        {o.client.legal_name} · {o.client.client_segment.replace(/_/g, " ")}
                      </div>
                      <div className="text-[11px] text-bny-fog mt-0.5">
                        {STATUS_PHRASE[o.status as OpportunityStatus] ?? o.status}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-semibold">
                        {fmtUsd(o.scope_summary.estimated_aum_usd, true)}
                      </div>
                      <div className="mt-1">
                        <StatusPill status={o.status} />
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="bg-white border border-bny-mist rounded-lg p-4">
          <header className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold">eCRM inbox</h2>
              <p className="text-xs text-bny-fog mt-0.5">
                Inbound RFPs across all S01 channels
              </p>
            </div>
            <Link to="/sources" className="text-xs text-bny-teal hover:underline">
              Open inbox →
            </Link>
          </header>
          {newSources.length === 0 ? (
            <p className="text-sm text-bny-fog">No new sources.</p>
          ) : (
            <ul className="space-y-2" data-testid="home-sources">
              {newSources.slice(0, 4).map((s) => (
                <li key={s.source_id}>
                  <Link
                    to="/sources"
                    className="block text-sm hover:bg-bny-paper rounded px-1 py-1"
                    data-testid={`home-source-${s.source_id}`}
                  >
                    <div className="font-medium leading-tight">{s.headline}</div>
                    <div className="text-xs text-bny-fog mt-0.5">
                      {s.channel.replace(/_/g, " ")}
                      {s.consultant ? ` · ${s.consultant}` : ""} · {fmtUsd(s.estimated_aum_usd, true)} AUM
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {recentTerminal.length > 0 && (
        <section className="bg-white border border-bny-mist rounded-lg p-4 mb-6">
          <header className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold">Recent disposition</h2>
              <p className="text-xs text-bny-fog mt-0.5">
                Sealed / lost / withdrawn deals — context for win-loss analytics
              </p>
            </div>
          </header>
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-2" data-testid="recent-disposition">
            {recentTerminal.map((o) => (
              <li key={o.opportunity_id}>
                <Link
                  to="/opportunities/$oppId"
                  params={{ oppId: o.opportunity_id }}
                  className="flex items-start justify-between gap-3 border border-bny-mist rounded p-2 hover:border-bny-teal"
                  data-testid={`recent-${o.opportunity_id}`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{o.name}</div>
                    <div className="text-xs text-bny-slate truncate">
                      {o.disposition_reason ?? "—"}
                    </div>
                    <div className="text-[11px] text-bny-fog mt-1">
                      {fmtDate(o.disposition_at ?? o.updated_at)}
                    </div>
                  </div>
                  <StatusPill status={o.status} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="bg-bny-paper border border-bny-mist rounded-lg p-4">
        <header className="mb-3">
          <h2 className="text-sm font-semibold">Workflow surfaces</h2>
          <p className="text-xs text-bny-fog mt-0.5">
            Stages handed off to partner teams. Each opens its own console — they all
            roll up to the opportunity workspace.
          </p>
        </header>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Link
            to="/pipeline/$ddqId"
            params={{ ddqId: "ddq_8db64d9cb6c5" }}
            className="block bg-white border border-bny-mist rounded-md p-3 hover:border-bny-teal transition-colors"
            data-testid="ref-ddq-pipeline"
          >
            <div className="text-[10px] uppercase tracking-wider text-bny-fog">
              DDQ team
            </div>
            <div className="text-sm font-medium mt-0.5">DDQ pipeline</div>
            <div className="text-xs text-bny-slate mt-1">
              Email → 8-agent roster → sealed run. Powers S03 commitments on every opportunity that needs a DDQ.
            </div>
          </Link>
          <Link
            to="/employees/$de"
            params={{ de: "aria" }}
            className="block bg-white border border-bny-mist rounded-md p-3 hover:border-bny-teal transition-colors"
            data-testid="ref-aria-console"
          >
            <div className="text-[10px] uppercase tracking-wider text-bny-fog">
              DDQ team
            </div>
            <div className="text-sm font-medium mt-0.5">Aria · DDQ digital employee</div>
            <div className="text-xs text-bny-slate mt-1">
              Operator console for SME approvals, agent roster, KPIs.
            </div>
          </Link>
          <Link
            to="/runs/$runId"
            params={{ runId: "run_20260510T125906_2b46b0fd" }}
            className="block bg-white border border-bny-mist rounded-md p-3 hover:border-bny-teal transition-colors"
            data-testid="ref-sealed-run"
          >
            <div className="text-[10px] uppercase tracking-wider text-bny-fog">
              Audit
            </div>
            <div className="text-sm font-medium mt-0.5">Sealed run walkthrough</div>
            <div className="text-xs text-bny-slate mt-1">
              Bit-exact reproducible response — citations, validators, journal.
            </div>
          </Link>
        </div>
      </section>
    </div>
  );
}

function SummaryStat({
  label,
  value,
  hint,
  testId,
}: {
  label: string;
  value: string;
  hint?: string;
  testId?: string;
}) {
  return (
    <div
      className="bg-white border border-bny-mist rounded-lg p-3"
      data-testid={testId}
    >
      <div className="text-[10px] uppercase tracking-wider text-bny-fog">{label}</div>
      <div className="text-xl font-semibold mt-0.5">{value}</div>
      {hint && <div className="text-[10px] text-bny-fog mt-0.5">{hint}</div>}
    </div>
  );
}

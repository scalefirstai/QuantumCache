import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { createOpportunity, listOpportunities } from "@/api/oppDeal";
import type { Opportunity, OpportunityStatus } from "@/types/oppDeal";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import {
  FilterRow,
  FormField,
  Input,
  Modal,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Select,
  TextArea,
} from "@/components/datasets/Common";
import { StatusPill } from "@/components/opp-deal/Format";
import { fmtUsd, fmtDate } from "@/components/opp-deal/formatters";

// Buckets keep the pipeline summary readable — terminal states sit on their own.
const STATUS_BUCKETS: Array<{
  key: "all" | "in_flight" | "won" | "lost" | "withdrawn" | OpportunityStatus;
  label: string;
  match: (s: OpportunityStatus) => boolean;
}> = [
  { key: "all", label: "All", match: () => true },
  {
    key: "in_flight",
    label: "In-flight",
    match: (s) => !["won", "lost", "withdrawn"].includes(s),
  },
  { key: "intake", label: "Intake", match: (s) => s === "intake" || s === "resolving" },
  { key: "scoping", label: "Scope/DDQ", match: (s) => s === "scoping" || s === "ddq" },
  {
    key: "complexity",
    label: "Complexity/Cost",
    match: (s) => s === "complexity" || s === "cost_capacity",
  },
  { key: "pricing", label: "Pricing", match: (s) => s === "pricing" },
  {
    key: "operating_model",
    label: "Op-model",
    match: (s) => s === "operating_model",
  },
  { key: "approval", label: "Approval", match: (s) => s === "approval" },
  { key: "won", label: "Won", match: (s) => s === "won" },
  { key: "lost", label: "Lost", match: (s) => s === "lost" },
  { key: "withdrawn", label: "Withdrawn", match: (s) => s === "withdrawn" },
];

export function OpportunitiesRoute() {
  const [items, setItems] = useState<Opportunity[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [bucket, setBucket] =
    useState<(typeof STATUS_BUCKETS)[number]["key"]>("in_flight");
  const navigate = useNavigate();

  // form state
  const [name, setName] = useState("");
  const [channel, setChannel] = useState("rfp_email");
  const [legalName, setLegalName] = useState("");
  const [ucmId, setUcmId] = useState("");
  const [segment, setSegment] = useState("asset_manager");
  const [domicile, setDomicile] = useState("UK");
  const [products, setProducts] = useState("custody.global, fa.daily_nav, depo.ucits, conn.nexen_portal");
  const [jurisdictions, setJurisdictions] = useState("IE, LU");
  const [aum, setAum] = useState("12000000000");
  const [navStrikes, setNavStrikes] = useState("12");
  const [transactions, setTransactions] = useState("250000");
  const [capitalEvents, setCapitalEvents] = useState("60");
  const [shareholders, setShareholders] = useState("25000");
  const [createErr, setCreateErr] = useState<string | null>(null);

  const load = () => {
    listOpportunities().then(setItems).catch((e) => setErr(String(e)));
  };
  useEffect(load, []);

  const onCreate = async () => {
    setCreateErr(null);
    setBusy(true);
    try {
      const created = await createOpportunity({
        name,
        ecrm_id: "",
        source: { channel, raw_artifacts: [] },
        client: {
          ucm_id: ucmId || null,
          ucm_snapshot_version: "ucm_v2026.05.13",
          legal_name: legalName,
          domicile,
          client_segment: segment,
          entity_tree_roles: [],
        },
        relationship: { existing_revenue_usd_annual: 0, existing_products: [] },
        scope_summary: {
          products_requested: products
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          jurisdictions: jurisdictions
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          estimated_aum_usd: parseInt(aum, 10) || 0,
          nav_strikes_per_day: parseInt(navStrikes, 10) || 0,
          transactions_per_year: parseInt(transactions, 10) || 0,
          capital_events_per_year: parseInt(capitalEvents, 10) || 0,
          shareholders: parseInt(shareholders, 10) || 0,
        },
      });
      setOpen(false);
      load();
      navigate({
        to: "/opportunities/$oppId",
        params: { oppId: created.opportunity_id },
      });
    } catch (e) {
      setCreateErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const counts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const b of STATUS_BUCKETS) {
      map[b.key as string] = (items ?? []).filter((o) =>
        b.match(o.status as OpportunityStatus),
      ).length;
    }
    return map;
  }, [items]);

  if (err) return <ErrorBox title="Failed to load opportunities" detail={err} />;
  if (!items) return <Loading />;

  const activeBucket =
    STATUS_BUCKETS.find((b) => b.key === bucket) ?? STATUS_BUCKETS[0]!;
  const filtered = items
    .filter((o) => activeBucket.match(o.status as OpportunityStatus))
    .filter((o) =>
      search
        ? o.name.toLowerCase().includes(search.toLowerCase()) ||
          o.opportunity_id.toLowerCase().includes(search.toLowerCase()) ||
          o.client.legal_name.toLowerCase().includes(search.toLowerCase())
        : true,
    );

  const totalAum = items.reduce((s, o) => s + o.scope_summary.estimated_aum_usd, 0);
  const wonCount = counts.won ?? 0;

  return (
    <div data-testid="opportunities-root">
      <PageHeader
        eyebrow="Deal pipeline"
        title="Opportunities"
        subtitle="From inbound RFP to sealed deal. Open one to drive it through intake, DDQ, complexity, cost, pricing, operating model and approval — partner teams own specific stages."
        actions={
          <div className="flex gap-2">
            <SecondaryButton
              testId="open-sources-btn"
              onClick={() => navigate({ to: "/sources" })}
            >
              eCRM inbox →
            </SecondaryButton>
            <PrimaryButton testId="add-opportunity-btn" onClick={() => setOpen(true)}>
              New opportunity
            </PrimaryButton>
          </div>
        }
      />

      <div
        className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4"
        data-testid="pipeline-summary"
      >
        <SummaryStat label="Total opportunities" value={items.length.toString()} />
        <SummaryStat
          label="In-flight"
          value={(counts.in_flight ?? 0).toString()}
        />
        <SummaryStat label="Won" value={wonCount.toString()} />
        <SummaryStat label="Pipeline AUM" value={fmtUsd(totalAum, true)} />
      </div>

      <FilterRow>
        <div className="flex flex-wrap gap-1" data-testid="status-tabs">
          {STATUS_BUCKETS.map((b) => (
            <button
              key={b.key}
              type="button"
              onClick={() => setBucket(b.key)}
              data-testid={`status-tab-${b.key}`}
              className={
                "px-2 py-1 rounded-md text-xs border " +
                (bucket === b.key
                  ? "bg-bny-ink text-white border-bny-ink"
                  : "bg-white text-bny-slate border-bny-mist hover:bg-bny-paper")
              }
            >
              {b.label}{" "}
              <span className="ml-1 text-[10px] opacity-70">
                {counts[b.key as string] ?? 0}
              </span>
            </button>
          ))}
        </div>
      </FilterRow>

      <FilterRow>
        <input
          type="search"
          placeholder="Search by name, id, client…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="opportunities-search"
          className="px-2.5 py-1.5 rounded-md border border-bny-mist bg-white text-sm w-72 focus:outline-none focus:ring-2 focus:ring-bny-teal"
        />
        <span className="text-xs text-bny-slate">
          {filtered.length} of {items.length}
        </span>
      </FilterRow>

      <table className="w-full text-sm" data-testid="opportunities-table">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wider text-bny-fog border-b border-bny-mist">
            <th className="py-1.5">Opportunity</th>
            <th>Client</th>
            <th>Segment</th>
            <th>Status</th>
            <th className="text-right">Est. AUM</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((o) => (
            <tr
              key={o.opportunity_id}
              className="border-b border-bny-mist/40"
              data-testid={`opportunity-row-${o.opportunity_id}`}
            >
              <td className="py-1.5">
                <Link
                  to="/opportunities/$oppId"
                  params={{ oppId: o.opportunity_id }}
                  className="text-bny-teal hover:underline font-medium"
                >
                  {o.name || o.opportunity_id}
                </Link>
                <div className="text-xs font-mono text-bny-fog">{o.opportunity_id}</div>
              </td>
              <td className="text-xs">{o.client.legal_name}</td>
              <td className="text-xs">{o.client.client_segment.replace(/_/g, " ")}</td>
              <td>
                <StatusPill status={o.status} />
              </td>
              <td className="text-right text-xs">
                {fmtUsd(o.scope_summary.estimated_aum_usd, true)}
              </td>
              <td className="text-xs">{fmtDate(o.updated_at)}</td>
            </tr>
          ))}
          {filtered.length === 0 && (
            <tr>
              <td colSpan={6} className="py-8 text-center text-bny-fog text-sm">
                No opportunities match the filter.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <Modal
        open={open}
        title="New opportunity (S01 intake)"
        onClose={() => setOpen(false)}
        testId="create-opportunity-modal"
      >
        {createErr && (
          <div className="text-sm text-bny-danger mb-3" data-testid="create-error">
            {createErr}
          </div>
        )}
        <FormField label="Opportunity name">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            data-testid="opp-name"
            placeholder="Acme Pension — Global Custody + UCITS NAV"
          />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label="Channel">
            <Select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              data-testid="opp-channel"
            >
              <option value="rfp_email">RFP via email</option>
              <option value="rm_submitted">RM-submitted</option>
              <option value="consultant">Consultant-driven</option>
              <option value="cross_segment">Cross-segment referral</option>
              <option value="retender">Retender</option>
            </Select>
          </FormField>
          <FormField label="Client segment">
            <Select
              value={segment}
              onChange={(e) => setSegment(e.target.value)}
              data-testid="opp-segment"
            >
              <option value="asset_manager">Asset manager</option>
              <option value="asset_owner_pension">Asset owner (pension)</option>
              <option value="sovereign">Sovereign</option>
              <option value="insurance">Insurance</option>
              <option value="alts_manager">Alts manager</option>
            </Select>
          </FormField>
        </div>
        <FormField label="Legal name">
          <Input
            value={legalName}
            onChange={(e) => setLegalName(e.target.value)}
            data-testid="opp-legal-name"
          />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label="UCM id">
            <Input
              value={ucmId}
              onChange={(e) => setUcmId(e.target.value)}
              data-testid="opp-ucm-id"
              placeholder="ucm_<...>"
            />
          </FormField>
          <FormField label="Domicile">
            <Input
              value={domicile}
              onChange={(e) => setDomicile(e.target.value)}
              data-testid="opp-domicile"
            />
          </FormField>
        </div>
        <FormField label="Products requested (UPM codes, comma-separated)">
          <TextArea
            value={products}
            onChange={(e) => setProducts(e.target.value)}
            data-testid="opp-products"
            rows={2}
          />
        </FormField>
        <FormField label="Jurisdictions (comma-separated)">
          <Input
            value={jurisdictions}
            onChange={(e) => setJurisdictions(e.target.value)}
            data-testid="opp-jurisdictions"
          />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label="Estimated AUM (USD)">
            <Input
              value={aum}
              onChange={(e) => setAum(e.target.value)}
              data-testid="opp-aum"
              type="number"
            />
          </FormField>
          <FormField label="NAV strikes / day">
            <Input
              value={navStrikes}
              onChange={(e) => setNavStrikes(e.target.value)}
              data-testid="opp-nav-strikes"
              type="number"
            />
          </FormField>
          <FormField label="Transactions / year">
            <Input
              value={transactions}
              onChange={(e) => setTransactions(e.target.value)}
              data-testid="opp-transactions"
              type="number"
            />
          </FormField>
          <FormField label="Capital events / year">
            <Input
              value={capitalEvents}
              onChange={(e) => setCapitalEvents(e.target.value)}
              data-testid="opp-capital-events"
              type="number"
            />
          </FormField>
          <FormField label="Shareholders">
            <Input
              value={shareholders}
              onChange={(e) => setShareholders(e.target.value)}
              data-testid="opp-shareholders"
              type="number"
            />
          </FormField>
        </div>
        <div className="flex justify-end gap-2 mt-2">
          <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
          <PrimaryButton
            onClick={onCreate}
            testId="opp-create-submit"
            disabled={busy || !name || !legalName}
          >
            {busy ? "Creating…" : "Create opportunity"}
          </PrimaryButton>
        </div>
      </Modal>
    </div>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white border border-bny-mist rounded-lg p-3">
      <div className="text-[10px] uppercase tracking-wider text-bny-fog">{label}</div>
      <div className="text-lg font-semibold mt-0.5">{value}</div>
    </div>
  );
}

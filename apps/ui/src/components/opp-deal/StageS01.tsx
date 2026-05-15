import type { Opportunity } from "@/types/oppDeal";
import { Card, KeyValueGrid } from "./Format";
import { fmtUsd } from "./formatters";

export function StageS01({ opp }: { opp: Opportunity }) {
  const c = opp.client;
  const r = opp.relationship;
  return (
    <section data-testid="stage-s01">
      <Card title="S01 · Intake & client resolution" testId="card-s01-intake">
        <KeyValueGrid
          items={[
            { label: "Channel", value: opp.source.channel, testId: "kv-channel" },
            { label: "Received", value: opp.source.received_at },
            { label: "Consultant", value: opp.source.consultant ?? "—" },
            { label: "eCRM id", value: opp.ecrm_id },
            { label: "Status", value: opp.status },
            { label: "Artifacts", value: `${opp.source.raw_artifacts.length}` },
          ]}
        />
      </Card>

      <Card title="Client resolution" testId="card-s01-client">
        <KeyValueGrid
          items={[
            { label: "Legal name", value: c.legal_name, testId: "kv-legal-name" },
            { label: "UCM id", value: c.ucm_id ?? "unresolved" },
            { label: "UCM snapshot", value: c.ucm_snapshot_version },
            { label: "Segment", value: c.client_segment },
            { label: "Domicile", value: c.domicile },
            { label: "KYC", value: c.kyc_status },
            {
              label: "Confidence",
              value: `${(c.confidence * 100).toFixed(0)}%`,
              testId: "kv-confidence",
            },
          ]}
        />
        <div className="mt-4">
          <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
            Entity tree
          </div>
          <ul className="text-sm border border-bny-mist rounded-md divide-y divide-bny-mist">
            {c.entity_tree_roles.map((e) => (
              <li
                key={e.ucm_id}
                className="flex items-center justify-between px-3 py-1.5"
                data-testid={`entity-${e.role}`}
              >
                <span className="font-medium">{e.label || e.ucm_id}</span>
                <span className="text-[10px] uppercase tracking-wider text-bny-fog">
                  {e.role}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </Card>

      <Card title="Relationship context" testId="card-s01-relationship">
        <KeyValueGrid
          items={[
            {
              label: "Existing revenue",
              value: fmtUsd(r.existing_revenue_usd_annual, true),
            },
            { label: "Existing products", value: r.existing_products.join(", ") || "—" },
            {
              label: "Cross-sell pipeline",
              value: r.cross_sell_pipeline.join(", ") || "—",
            },
            { label: "Relationship Manager", value: r.rm_user_id ?? "—" },
            { label: "Exec sponsor", value: r.exec_sponsor_user_id ?? "—" },
            {
              label: "At-risk competitor clients",
              value: r.at_risk_competitor_clients.length.toString(),
            },
          ]}
        />
      </Card>
    </section>
  );
}

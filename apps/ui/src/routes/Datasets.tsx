import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { listDatasets } from "@/api/datasets";
import type { DatasetSummary } from "@/types/dataset";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import { PageHeader, formatDate } from "@/components/datasets/Common";

const lane: Record<string, string> = {
  knowledge: "bg-lane-knowledgeBg text-lane-knowledgeFg",
  canonical: "bg-lane-canonicalBg text-lane-canonicalFg",
  audit: "bg-lane-auditBg text-lane-auditFg",
};

export function DatasetsRoute() {
  const [items, setItems] = useState<DatasetSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    listDatasets().then(setItems).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <ErrorBox title="Failed to load datasets" detail={err} />;
  if (!items) return <Loading />;

  return (
    <div data-testid="datasets-root">
      <PageHeader
        eyebrow="Manage"
        title="Datasets"
        subtitle="The three datasets that define platform behavior. Knowledge feeds retrieval; Canonical is the taxonomy questions resolve against; Audit is the sealed, hash-chained record of every run."
      />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 max-w-4xl">
        {items.map((d) => (
          <Link
            key={d.id}
            to="/datasets/$type"
            params={{ type: d.id }}
            data-testid={`dataset-card-${d.id}`}
            className="block bg-white border border-bny-mist rounded-lg p-4 hover:border-bny-teal transition-colors"
          >
            <div
              className={`inline-block text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${
                lane[d.id] ?? "bg-bny-paper"
              }`}
            >
              {d.label}
            </div>
            <div
              className="text-2xl font-medium mt-3 leading-none"
              data-testid={`dataset-count-${d.id}`}
            >
              {d.count.toLocaleString()}
            </div>
            <div className="text-xs text-bny-slate mt-1">records</div>
            <p className="text-sm text-bny-slate mt-3 leading-snug">
              {d.description}
            </p>
            <div className="text-xs text-bny-slate mt-3">
              Updated {formatDate(d.lastUpdatedAt)}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

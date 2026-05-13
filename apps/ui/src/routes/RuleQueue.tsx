import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { listReviewQueue } from "@/api/rules";
import type { RuleSummary } from "@/types/rule";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import { PageHeader, TagPill } from "@/components/datasets/Common";
import { formatDate } from "@/components/datasets/format";
import { StatusBadge } from "@/components/rules/StatusBadge";

export function RuleQueueRoute() {
  const [items, setItems] = useState<RuleSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    listReviewQueue().then(setItems).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <ErrorBox title="Failed to load review queue" detail={err} />;
  if (!items) return <Loading />;

  return (
    <div data-testid="rule-queue-root">
      <PageHeader
        eyebrow="Rule engine · SME"
        title="Review queue"
        subtitle="Rules pending SME approval. Approve to activate; reject to bounce back to draft."
        actions={
          <Link to="/rules" className="text-sm text-bny-teal hover:underline">
            ← All rules
          </Link>
        }
      />

      {items.length === 0 ? (
        <div className="bg-white border border-bny-mist rounded-lg p-8 text-center text-sm text-bny-fog" data-testid="queue-empty">
          No rules pending review.
        </div>
      ) : (
        <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
          <table className="w-full text-sm" data-testid="queue-table">
            <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
              <tr>
                <th className="text-left font-medium px-3 py-2">Queue</th>
                <th className="text-left font-medium px-3 py-2">Rule ID</th>
                <th className="text-left font-medium px-3 py-2">Engine</th>
                <th className="text-left font-medium px-3 py-2">Title</th>
                <th className="text-left font-medium px-3 py-2">Submitted by</th>
                <th className="text-left font-medium px-3 py-2">Updated</th>
                <th className="text-left font-medium px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr
                  key={r.ruleId}
                  className="border-t border-bny-mist hover:bg-bny-paper/60"
                  data-testid={`queue-row-${r.ruleId}`}
                >
                  <td className="px-3 py-2">
                    <TagPill tone="audit">{r.reviewQueue}</TagPill>
                  </td>
                  <td className="px-3 py-2">
                    <Link
                      to="/rules/$ruleId"
                      params={{ ruleId: r.ruleId }}
                      className="text-bny-teal hover:underline font-mono text-xs"
                    >
                      {r.ruleId}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <TagPill tone={r.engine === "freshness" ? "knowledge" : "audit"}>
                      {r.engine}
                    </TagPill>
                  </td>
                  <td className="px-3 py-2">{r.title}</td>
                  <td className="px-3 py-2 text-xs">{r.submittedBy ?? "—"}</td>
                  <td className="px-3 py-2 text-xs">{formatDate(r.updatedAt)}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

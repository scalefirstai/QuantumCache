import { Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { listAudit, verifyAudit } from "@/api/datasets";
import type { AuditRunSummary, AuditVerifyResult } from "@/types/dataset";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import {
  FilterRow,
  Input,
  PageHeader,
  TagPill,
  VerdictPill,
} from "@/components/datasets/Common";
import { formatDate } from "@/components/datasets/format";
import { Pagination } from "@/components/datasets/Pagination";
import {
  DEFAULT_PAGE_SIZE,
  paginate,
  type PageSize,
} from "@/components/datasets/paginationUtils";

export function AuditListRoute() {
  const [items, setItems] = useState<AuditRunSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [framework, setFramework] = useState("");
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verifyResults, setVerifyResults] = useState<Record<string, AuditVerifyResult>>({});
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<PageSize>(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setPage(0);
  }, [query, framework]);

  useEffect(() => {
    listAudit().then(setItems).catch((e) => setErr(String(e)));
  }, []);

  const frameworks = useMemo(() => {
    if (!items) return [];
    return Array.from(new Set(items.map((r) => r.framework).filter(Boolean))).sort();
  }, [items]);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = query.toLowerCase();
    return items.filter((r) => {
      if (framework && r.framework !== framework) return false;
      if (!q) return true;
      return (
        r.runId.toLowerCase().includes(q) ||
        (r.ddqId ?? "").toLowerCase().includes(q) ||
        r.verdict.toLowerCase().includes(q)
      );
    });
  }, [items, query, framework]);

  const { pageItems, total } = useMemo(
    () => paginate(filtered, page, pageSize),
    [filtered, page, pageSize],
  );

  if (err) return <ErrorBox title="Failed to load audit runs" detail={err} />;
  if (!items) return <Loading />;

  const runVerify = async (runId: string) => {
    setVerifying(runId);
    try {
      const r = await verifyAudit(runId);
      setVerifyResults((prev) => ({ ...prev, [runId]: r }));
    } finally {
      setVerifying(null);
    }
  };

  return (
    <div data-testid="audit-list-root">
      <PageHeader
        eyebrow="Datasets · Audit"
        title="Sealed run journals"
        subtitle="Hash-chained, Merkle-rooted records of every DDQ response. Records are immutable — only redactions (legal hold) and integrity checks are available here."
        actions={
          <Link to="/datasets" className="text-sm text-bny-teal hover:underline">
            ← Datasets
          </Link>
        }
      />
      <FilterRow>
        <Input
          aria-label="Search audit runs"
          placeholder="Search runId, ddqId, verdict…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-sm"
          data-testid="audit-search"
        />
        <select
          aria-label="Filter by framework"
          value={framework}
          onChange={(e) => setFramework(e.target.value)}
          className="px-2 py-1.5 rounded-md border border-bny-mist bg-white text-sm"
          data-testid="audit-framework-filter"
        >
          <option value="">All frameworks</option>
          {frameworks.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-bny-fog" data-testid="audit-count">
          {filtered.length} of {items.length}
        </span>
      </FilterRow>
      <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm" data-testid="audit-table">
          <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
            <tr>
              <Th>Run</Th>
              <Th>Framework</Th>
              <Th>Verdict</Th>
              <Th className="text-right">Events</Th>
              <Th>Merkle root</Th>
              <Th>Sealed</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((r) => {
              const result = verifyResults[r.runId];
              return (
                <tr
                  key={r.runId}
                  className="border-t border-bny-mist hover:bg-bny-paper/60"
                  data-testid={`audit-row-${r.runId}`}
                >
                  <Td>
                    <Link
                      to="/datasets/audit/$runId"
                      params={{ runId: r.runId }}
                      className="text-bny-teal hover:underline font-mono text-xs"
                    >
                      {r.runId}
                    </Link>
                    {r.ddqId && (
                      <div className="text-[11px] text-bny-fog font-mono mt-0.5">
                        ddq: {r.ddqId}
                      </div>
                    )}
                  </Td>
                  <Td>
                    <TagPill tone="audit">{r.framework || "—"}</TagPill>
                  </Td>
                  <Td>
                    <VerdictPill verdict={r.verdict} />
                  </Td>
                  <Td className="text-right font-mono text-xs">{r.eventCount}</Td>
                  <Td>
                    <code className="text-[10px] text-bny-slate break-all">
                      {r.merkleRoot?.slice(0, 20)}…
                    </code>
                  </Td>
                  <Td className="text-xs text-bny-fog">{formatDate(r.sealedAt)}</Td>
                  <Td className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      {result && (
                        <TagPill tone={result.chainOk && result.merkleOk ? "ok" : "danger"}>
                          {result.chainOk && result.merkleOk ? "✓ verified" : "✗ broken"}
                        </TagPill>
                      )}
                      <button
                        type="button"
                        onClick={() => runVerify(r.runId)}
                        disabled={verifying === r.runId}
                        className="text-xs text-bny-teal hover:underline disabled:text-bny-fog disabled:cursor-not-allowed"
                        data-testid={`verify-${r.runId}`}
                      >
                        {verifying === r.runId ? "Verifying…" : "Verify"}
                      </button>
                    </div>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pagination
        page={page}
        pageSize={pageSize}
        total={total}
        onPageChange={setPage}
        onPageSizeChange={(s) => {
          setPageSize(s);
          setPage(0);
        }}
        testId="audit-pagination"
      />
      <p className="text-xs text-bny-fog mt-3 max-w-2xl">
        Sealed runs cannot be edited or deleted (ddq.md invariant 2). The verify
        action recomputes payload hashes, the chain hash for every event, and the
        Merkle root, comparing against the stored values.
      </p>
    </div>
  );
}

const Th = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <th className={`text-left font-medium px-3 py-2 ${className}`}>{children}</th>
);
const Td = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <td className={`px-3 py-2 align-middle ${className}`}>{children}</td>
);

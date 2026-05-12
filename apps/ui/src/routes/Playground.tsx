import { Link } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { getPlaygroundRun, listPlaygroundRuns, submitPlayground } from "@/api/agents";
import type { PlaygroundRun } from "@/types/agent";

const POLL_INTERVAL_MS = 2000;

export function PlaygroundRoute() {
  const [question, setQuestion] = useState(
    "Is multi-factor authentication enforced for privileged user access?",
  );
  const [framework, setFramework] = useState("CAIQ");
  const [run, setRun] = useState<PlaygroundRun | null>(null);
  const [history, setHistory] = useState<PlaygroundRun[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listPlaygroundRuns());
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  // Poll the current run until terminal status.
  useEffect(() => {
    if (!run || run.status === "succeeded" || run.status === "failed") return;
    pollRef.current = window.setInterval(async () => {
      try {
        const updated = await getPlaygroundRun(run.runId);
        setRun(updated);
        if (updated.status === "succeeded" || updated.status === "failed") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          void refreshHistory();
        }
      } catch (e) {
        setErr(String(e));
      }
    }, POLL_INTERVAL_MS) as unknown as number;
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [run, refreshHistory]);

  const onSubmit = async () => {
    setSubmitting(true);
    setErr(null);
    try {
      const { runId } = await submitPlayground({
        question,
        framework,
        actor: "aria@bny.com",
      });
      setRun({
        runId,
        question,
        framework,
        actor: "aria@bny.com",
        status: "queued",
        submittedAt: new Date().toISOString(),
        completedAt: null,
        sealedRunId: null,
        error: null,
      });
      void refreshHistory();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="px-6 py-5 max-w-5xl" data-testid="playground-root">
      <header className="mb-4">
        <h1 className="text-xl font-semibold leading-tight">Playground</h1>
        <p className="text-sm text-bny-fog mt-1">
          Fire a single question through the full L06/L07 pipeline. Uses real Anthropic +
          retrieval + library + audit — every submission produces a sealed run.
        </p>
      </header>

      <section className="grid grid-cols-3 gap-4 mb-6">
        <div className="col-span-2 border border-bny-mist rounded-lg bg-white p-4">
          <label className="block text-xs text-bny-fog mb-1">Framework</label>
          <select
            data-testid="framework-select"
            value={framework}
            onChange={(e) => setFramework(e.target.value)}
            className="w-44 text-sm p-2 rounded-md border border-bny-mist mb-3"
          >
            {["CAIQ", "AFME", "NIST_CSF_v2.0", "ADVERSARIAL", "BESPOKE"].map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
          <label className="block text-xs text-bny-fog mb-1">Question</label>
          <textarea
            data-testid="question-textarea"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            className="w-full h-28 text-sm font-mono p-3 rounded-md border border-bny-mist"
          />
          <button
            data-testid="submit-button"
            onClick={onSubmit}
            disabled={submitting || (!!run && run.status === "running")}
            className="mt-3 text-sm font-medium px-3 py-2 rounded-md bg-bny-teal text-white hover:bg-bny-teal/90 disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit"}
          </button>
          {err && (
            <p data-testid="error" className="text-xs text-red-600 mt-2 whitespace-pre-wrap">
              {err}
            </p>
          )}
        </div>

        <div className="border border-bny-mist rounded-lg bg-white p-4" data-testid="active-run">
          <h2 className="text-sm font-semibold mb-2">Active run</h2>
          {run ? (
            <dl className="text-xs space-y-1">
              <Row label="ID" value={<code className="font-mono">{run.runId}</code>} />
              <Row label="Status" value={<StatusPill s={run.status} />} />
              <Row
                label="Submitted"
                value={<span className="text-bny-fog">{new Date(run.submittedAt).toLocaleTimeString()}</span>}
              />
              {run.completedAt && (
                <Row
                  label="Completed"
                  value={
                    <span className="text-bny-fog">{new Date(run.completedAt).toLocaleTimeString()}</span>
                  }
                />
              )}
              {run.sealedRunId && (
                <Row
                  label="Sealed run"
                  value={
                    <Link
                      to="/runs/$runId"
                      params={{ runId: run.sealedRunId }}
                      className="text-bny-teal hover:underline font-mono"
                      data-testid="open-sealed-run"
                    >
                      {run.sealedRunId} →
                    </Link>
                  }
                />
              )}
              {run.error && (
                <div className="mt-2 text-red-600 whitespace-pre-wrap" data-testid="run-error">
                  {run.error}
                </div>
              )}
            </dl>
          ) : (
            <p className="text-xs text-bny-fog">No active run.</p>
          )}
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold mb-2">Recent submissions</h2>
        <div className="border border-bny-mist rounded-lg bg-white overflow-hidden">
          <table className="w-full text-sm" data-testid="history-table">
            <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
              <tr>
                <Th>Submitted</Th>
                <Th>Framework</Th>
                <Th>Question</Th>
                <Th>Status</Th>
                <Th>Sealed run</Th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-3 text-xs text-bny-fog">
                    No submissions yet.
                  </td>
                </tr>
              ) : (
                history.map((r) => (
                  <tr
                    key={r.runId}
                    className="border-t border-bny-mist"
                    data-testid={`history-row-${r.runId}`}
                  >
                    <Td className="text-xs text-bny-fog">
                      {new Date(r.submittedAt).toLocaleTimeString()}
                    </Td>
                    <Td className="text-xs">{r.framework}</Td>
                    <Td className="text-xs">{r.question.slice(0, 80)}{r.question.length > 80 ? "…" : ""}</Td>
                    <Td>
                      <StatusPill s={r.status} />
                    </Td>
                    <Td className="text-xs font-mono">
                      {r.sealedRunId ? (
                        <Link
                          to="/runs/$runId"
                          params={{ runId: r.sealedRunId }}
                          className="text-bny-teal hover:underline"
                        >
                          {r.sealedRunId} →
                        </Link>
                      ) : (
                        "—"
                      )}
                    </Td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <dt className="text-bny-fog w-20">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function StatusPill({ s }: { s: PlaygroundRun["status"] }) {
  const colors: Record<PlaygroundRun["status"], string> = {
    queued: "bg-bny-mist text-bny-slate",
    running: "bg-bny-tealLight text-bny-ink animate-pulse",
    succeeded: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };
  return (
    <span
      className={`text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide ${colors[s]}`}
      data-testid={`status-${s}`}
    >
      {s}
    </span>
  );
}

const Th = ({ children }: { children: React.ReactNode }) => (
  <th className="text-left font-medium px-3 py-2">{children}</th>
);
const Td = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <td className={`px-3 py-2 align-middle ${className}`}>{children}</td>
);

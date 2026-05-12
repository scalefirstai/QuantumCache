import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { listAgents } from "@/api/agents";
import type { AgentSummary } from "@/types/agent";

export function AgentsRoute() {
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    listAgents().then(setAgents).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <Error msg={err} />;
  if (!agents) return <Loading />;

  return (
    <div className="px-6 py-5" data-testid="agents-root">
      <header className="mb-4">
        <h1 className="text-xl font-semibold leading-tight">Agents · L06 roster</h1>
        <p className="text-sm text-bny-fog mt-1">
          The 8 agents that respond to a DDQ question. Editable prompts live behind each LLM-backed
          row; rule-based agents have their logic in <code className="text-xs">services/&lt;svc&gt;/agent.py</code>.
        </p>
      </header>
      <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm" data-testid="agents-table">
          <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
            <tr>
              <Th>Name</Th>
              <Th>Kind</Th>
              <Th>Model</Th>
              <Th className="text-right">Temp</Th>
              <Th className="text-right">Max tok</Th>
              <Th>Tools</Th>
              <Th>Active</Th>
              <Th>Edited</Th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr
                key={a.id}
                className="border-t border-bny-mist hover:bg-bny-paper/60"
                data-testid={`agent-row-${a.id}`}
              >
                <Td>
                  <Link
                    to="/agents/$agentId"
                    params={{ agentId: a.id }}
                    className="text-bny-teal hover:underline font-medium"
                  >
                    {a.name}
                  </Link>
                </Td>
                <Td>
                  <span
                    className={
                      "text-[11px] px-1.5 py-0.5 rounded uppercase tracking-wide " +
                      (a.kind === "llm"
                        ? "bg-bny-tealLight text-bny-ink"
                        : "bg-bny-mist text-bny-slate")
                    }
                  >
                    {a.kind}
                  </span>
                </Td>
                <Td className="font-mono text-xs">{a.model ?? "—"}</Td>
                <Td className="text-right font-mono text-xs">
                  {a.temperature !== null ? a.temperature.toFixed(2) : "—"}
                </Td>
                <Td className="text-right font-mono text-xs">{a.maxTokens ?? "—"}</Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {(a.tools ?? []).map((t) => (
                      <span
                        key={t}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-bny-paper border border-bny-mist text-bny-slate font-mono"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </Td>
                <Td className="font-mono text-xs">{a.activeVersion ?? "—"}</Td>
                <Td className="text-xs text-bny-fog">
                  {a.lastEditedAt ? new Date(a.lastEditedAt).toLocaleString() : "—"}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const Th = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <th className={`text-left font-medium px-3 py-2 ${className}`}>{children}</th>
);
const Td = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <td className={`px-3 py-2 align-middle ${className}`}>{children}</td>
);
const Loading = () => <div className="px-6 py-5 text-sm text-bny-fog">Loading…</div>;
const Error = ({ msg }: { msg: string }) => (
  <div className="px-6 py-5 max-w-xl">
    <div className="border border-bny-mist rounded-lg bg-white p-4 text-sm">
      <div className="font-medium mb-1">Failed to load agents.</div>
      <pre className="text-xs text-bny-fog whitespace-pre-wrap">{msg}</pre>
    </div>
  </div>
);

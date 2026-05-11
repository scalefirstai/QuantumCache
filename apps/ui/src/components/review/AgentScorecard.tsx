import type { AgentScorecardRow } from "@/types/review";

const statusColor: Record<AgentScorecardRow["status"], string> = {
  ok: "text-bny-ok",
  warn: "text-bny-ochre",
  danger: "text-bny-danger",
};

const costToneClass: Record<AgentScorecardRow["costTone"], string> = {
  ok: "text-bny-ok",
  warn: "text-bny-ochre",
  danger: "text-bny-danger",
  neutral: "text-bny-slate",
};

export function AgentScorecard({ rows }: { rows: AgentScorecardRow[] }) {
  return (
    <section
      data-testid="agent-scorecard"
      className="bg-white border border-bny-mist rounded-lg p-4 mb-3.5"
    >
      <h2 className="text-[13px] font-medium text-bny-ink mb-3 m-0">
        Per-agent scorecard
      </h2>
      <table
        className="w-full text-xs border-collapse"
        style={{ tableLayout: "fixed" }}
      >
        <thead>
          <tr className="border-b border-bny-mist">
            <Th className="w-[30%] text-left">Agent</Th>
            <Th className="text-right">Calls</Th>
            <Th className="text-right">P95</Th>
            <Th className="text-right">Eval pass</Th>
            <Th className="text-right">Cost</Th>
            <Th className="w-[12%] text-center">Status</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} data-agent={r.name} className="border-b border-bny-mist">
              <td className="px-1 py-2 text-bny-ink">{r.name}</td>
              <td className="px-1 py-2 text-right text-bny-slate">{r.calls}</td>
              <td className="px-1 py-2 text-right text-bny-slate">{r.p95}</td>
              <td className="px-1 py-2 text-right text-bny-ink">{r.evalPass}</td>
              <td
                data-cost-tone={r.costTone}
                className={`px-1 py-2 text-right ${costToneClass[r.costTone]}`}
              >
                {r.cost}
              </td>
              <td className="px-1 py-2 text-center">
                <span aria-label={r.status} className={statusColor[r.status]}>
                  ●
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Th({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <th
      className={`px-1 py-1.5 text-bny-fog font-normal ${className ?? ""}`}
    >
      {children}
    </th>
  );
}

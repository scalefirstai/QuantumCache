import type { Agent } from "@/types/employee";

export function AgentRoster({ agents }: { agents: Agent[] }) {
  return (
    <section
      data-testid="agent-roster"
      className="bg-white border border-bny-mist rounded-lg px-4 py-3.5"
    >
      <div className="flex justify-between items-baseline mb-3">
        <h2 className="text-[13px] font-medium text-bny-ink m-0">
          Agents · L06 roster
        </h2>
        <div className="text-[11px] text-bny-fog">
          {agents.length} specialists · single responsibility each
        </div>
      </div>

      <ul className="flex flex-col gap-2">
        {agents.map((a) => (
          <li
            key={a.name}
            data-agent={a.name}
            className="grid items-start gap-2.5"
            style={{ gridTemplateColumns: "12px 1fr" }}
          >
            <span
              aria-hidden="true"
              className={[
                "w-2 h-2 rounded-full mt-2",
                a.tone === "primary" ? "bg-bny-teal" : "bg-bny-sky",
              ].join(" ")}
            />
            <div>
              <div className="flex justify-between items-baseline gap-3">
                <span className="text-[13px] text-bny-ink font-medium">
                  {a.name}
                </span>
                <span className="text-[10px] text-bny-fog font-mono">
                  {a.modelLine}
                </span>
              </div>
              <div className="text-[11px] text-bny-slate mt-0.5">
                {a.description}
              </div>
              <div className="flex flex-wrap gap-1 mt-1">
                {a.skills.map((s) => (
                  <span
                    key={s}
                    className="bg-bny-tealLight text-bny-ink text-[10px] px-1.5 py-px rounded"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

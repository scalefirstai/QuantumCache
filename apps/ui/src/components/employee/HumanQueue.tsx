import type { DecisionRight, QueueItem } from "@/types/employee";

const decisionIcon: Record<DecisionRight["icon"], { glyph: string; color: string }> = {
  check: { glyph: "✓", color: "text-bny-teal" },
  "user-check": { glyph: "👤", color: "text-bny-ochre" },
  "shield-x": { glyph: "✕", color: "text-bny-danger" },
};

export function HumanQueue({
  items,
  awaiting,
  decisionRights,
}: {
  items: QueueItem[];
  awaiting: number;
  decisionRights: DecisionRight[];
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <section
        data-testid="human-queue"
        className="bg-white border border-bny-ochre rounded-lg p-3.5"
      >
        <div className="flex items-center gap-1.5 mb-1">
          <span aria-hidden="true" className="text-bny-ochre">
            ✓
          </span>
          <h2 className="text-[13px] font-medium text-bny-ink m-0">
            Human in the loop
          </h2>
        </div>
        <div className="text-[11px] text-bny-fog mb-3">
          {awaiting} awaiting decision
        </div>

        <ul className="flex flex-col gap-2.5">
          {items.map((it) => (
            <li
              key={it.domain}
              data-status={it.status}
              className={[
                "border-l-2 pl-2.5 py-0.5 rounded-r",
                it.status === "halted"
                  ? "border-bny-danger bg-[#FCEBEB]"
                  : "border-bny-ochre",
              ].join(" ")}
            >
              <div className="text-[12px] text-bny-ink font-medium">
                {it.domain}
              </div>
              <div className="text-[11px] text-bny-slate mt-px">{it.scope}</div>
              <div
                className={[
                  "text-[10px] mt-1",
                  it.status === "halted" ? "text-bny-danger" : "text-bny-fog",
                ].join(" ")}
              >
                {it.caption}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="bg-white border border-bny-mist rounded-lg p-3.5">
        <div className="text-[11px] text-bny-fog tracking-wider mb-2">
          DECISION RIGHTS
        </div>
        <ul className="text-[11px] text-bny-ink space-y-1">
          {decisionRights.map((d) => (
            <li key={d.text} className="flex gap-1.5 items-start">
              <span
                aria-hidden="true"
                className={`shrink-0 ${decisionIcon[d.icon].color}`}
              >
                {decisionIcon[d.icon].glyph}
              </span>
              <span>{d.text}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

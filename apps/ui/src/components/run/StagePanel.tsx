import type { Stage } from "@/types/run";
import { Tokens } from "../shell/Tokens";
import { LanePill } from "./LanePill";

export function StagePanel({ stage }: { stage: Stage }) {
  return (
    <div
      role="tabpanel"
      id={`stage-panel-${stage.id}`}
      aria-labelledby={`stage-tab-${stage.id}`}
      data-stage={stage.id}
    >
      <header className="mb-4">
        <h2 className="text-lg font-medium m-0">{stage.title}</h2>
        <p className="text-[13px] text-[var(--color-text-secondary)] m-0">{stage.sub}</p>
      </header>

      <Lane label="User perspective">
        <Tokens value={stage.user} />
      </Lane>
      <Lane label="System action">
        <Tokens value={stage.system} />
      </Lane>

      <div className="bg-[var(--color-background-secondary)] rounded-md px-4 py-3 mb-2.5">
        <p className="text-[11px] uppercase tracking-wider text-[var(--color-text-tertiary)] m-0 mb-2 font-medium">
          Data layer
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
          {stage.data.map((d, i) => (
            <div
              key={i}
              data-cell-index={i}
              className="bg-white px-3 py-2.5 rounded-md border border-[var(--color-border-tertiary)]"
            >
              <p className="text-[11px] font-medium m-0 mb-1">
                <LanePill lane={d.lane} />
              </p>
              <p className="text-[12px] leading-[1.5] m-0">
                <strong className="font-medium">{d.label}.</strong>{" "}
                <Tokens value={d.body} />
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Lane({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-[var(--color-background-secondary)] rounded-md px-4 py-3 mb-2.5">
      <p className="text-[11px] uppercase tracking-wider text-[var(--color-text-tertiary)] m-0 mb-2 font-medium">
        {label}
      </p>
      <p className="text-sm leading-[1.6] m-0">{children}</p>
    </section>
  );
}

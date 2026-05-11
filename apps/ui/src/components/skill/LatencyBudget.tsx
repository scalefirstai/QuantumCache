import type { LatencyBar } from "@/types/skill";

const toneClass: Record<LatencyBar["tone"], string> = {
  step: "bg-bny-teal",
  filter: "bg-bny-ochre",
  total: "bg-bny-ink",
  cached: "bg-bny-ok",
};

interface Props {
  bars: LatencyBar[];
  max: number;
}

export function LatencyBudget({ bars, max }: Props) {
  return (
    <section
      data-testid="latency-budget"
      className="bg-white border border-bny-mist rounded-lg px-4 py-3.5"
    >
      <h2 className="text-[13px] font-medium text-bny-ink m-0">Latency budget</h2>
      <div className="text-[11px] text-bny-fog mb-3">
        P95 · 30-day rolling · ms
      </div>
      <ul className="flex flex-col gap-2">
        {bars.map((b) => {
          const pct = Math.min(100, Math.round((b.ms / max) * 100));
          const emphasized = b.tone === "total" || b.tone === "cached";
          return (
            <li key={b.label}>
              <div
                role="progressbar"
                aria-label={b.label}
                aria-valuenow={b.ms}
                aria-valuemin={0}
                aria-valuemax={max}
                data-tone={b.tone}
              >
                <div className="flex justify-between text-[11px] text-bny-slate mb-1">
                  <span>{b.label}</span>
                  <span
                    className={[
                      "text-bny-ink",
                      emphasized ? "font-medium" : "",
                    ].join(" ")}
                  >
                    {b.ms}ms
                  </span>
                </div>
                <div className="h-1.5 bg-bny-haze rounded-sm overflow-hidden">
                  <div
                    className={`h-full ${toneClass[b.tone]}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

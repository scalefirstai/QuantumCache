import type { ReviewKpi } from "@/types/review";

const toneClass: Record<ReviewKpi["tone"], string> = {
  ok: "text-bny-ok",
  warn: "text-bny-ochre",
  danger: "text-bny-danger",
  neutral: "text-bny-fog",
};

export function ReviewKpiStrip({ kpis }: { kpis: ReviewKpi[] }) {
  return (
    <div
      data-testid="review-kpi-strip"
      className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mb-4"
    >
      {kpis.map((k) => (
        <div
          key={k.label}
          data-tone={k.tone}
          className="bg-white border border-bny-mist rounded-md px-3 py-2.5"
        >
          <div className="text-[10px] text-bny-fog">{k.label}</div>
          <div className="text-lg font-medium text-bny-ink mt-0.5">
            {k.value}
          </div>
          <div className={`text-[10px] mt-px ${toneClass[k.tone]}`}>
            {k.delta}
          </div>
        </div>
      ))}
    </div>
  );
}

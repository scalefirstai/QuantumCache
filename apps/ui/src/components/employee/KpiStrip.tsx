import type { Kpi } from "@/types/employee";

export function KpiStrip({ kpis }: { kpis: Kpi[] }) {
  return (
    <div
      data-testid="kpi-strip"
      className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-5"
    >
      {kpis.map((k) => (
        <div
          key={k.label}
          className="bg-white border border-bny-mist rounded-md px-3 py-2.5"
        >
          <div className="text-[10px] text-bny-fog">{k.label}</div>
          <div className="text-lg font-medium text-bny-ink mt-0.5">
            {k.value}
          </div>
        </div>
      ))}
    </div>
  );
}

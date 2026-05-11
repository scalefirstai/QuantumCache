import { Chart } from "react-chartjs-2";
import type { QualitySeries } from "@/types/review";
import { ensureRegistered } from "./charts";

ensureRegistered();

export function QualityTrendChart({ data }: { data: QualitySeries }) {
  const tertiaryLabel = data.tertiaryLabel ?? "Hallucination % ×10";
  return (
    <div className="bg-white border border-bny-mist rounded-lg p-4">
      <div className="flex justify-between items-baseline mb-1">
        <h2 className="text-[13px] font-medium text-bny-ink m-0">
          Quality KPIs · 6-month trend
        </h2>
        <div className="text-[11px] text-bny-fog">
          monthly · target lines dashed
        </div>
      </div>
      <div className="flex flex-wrap gap-3.5 my-2 text-[11px] text-bny-slate">
        <Legend swatch="#2B9CAE" label="Library hit %" />
        <Legend swatch="#04243C" label="Auto-pass %" />
        <Legend swatch="#BA7517" label={tertiaryLabel} />
      </div>
      <div className="relative w-full h-60">
        <Chart
          type="line"
          aria-label="Six-month trend of library hit rate, auto-pass rate, and hallucination rate."
          data-testid="quality-chart"
          data={{
            labels: data.months,
            datasets: [
              {
                label: "Library hit %",
                data: data.libraryHit,
                borderColor: "#2B9CAE",
                backgroundColor: "#2B9CAE",
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 3,
              },
              {
                label: "Auto-pass %",
                data: data.autoPass,
                borderColor: "#04243C",
                backgroundColor: "#04243C",
                borderWidth: 2,
                borderDash: [4, 3],
                tension: 0.3,
                pointRadius: 3,
              },
              {
                label: tertiaryLabel,
                data: data.hallucinationX10,
                borderColor: "#BA7517",
                backgroundColor: "#BA7517",
                borderWidth: 2,
                borderDash: [2, 2],
                tension: 0.3,
                pointRadius: 3,
              },
              {
                label: "Library hit target",
                data: Array(data.months.length).fill(data.libraryHitTarget),
                borderColor: "#7FCAD5",
                borderWidth: 1,
                borderDash: [3, 3],
                pointRadius: 0,
                fill: false,
              },
            ],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              y: {
                beginAtZero: false,
                min: 0,
                max: 100,
                ticks: { color: "#7B8E9D", font: { size: 11 } },
                grid: { color: "rgba(0,0,0,0.05)" },
              },
              x: {
                ticks: { color: "#7B8E9D", font: { size: 11 } },
                grid: { display: false },
              },
            },
          }}
        />
      </div>
    </div>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        aria-hidden="true"
        className="w-2.5 h-2.5 rounded-sm"
        style={{ backgroundColor: swatch }}
      />
      {label}
    </span>
  );
}

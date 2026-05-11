import { Chart } from "react-chartjs-2";
import type { CostSeries } from "@/types/review";
import { ensureRegistered } from "./charts";

ensureRegistered();

export function CostVsBudgetChart({ data }: { data: CostSeries }) {
  return (
    <div className="bg-white border border-bny-mist rounded-lg p-4">
      <h2 className="text-[13px] font-medium text-bny-ink m-0">Cost vs budget</h2>
      <div className="text-[11px] text-bny-fog mb-2.5">
        stacked by model tier · monthly $
      </div>
      <div className="flex flex-wrap gap-3 mb-2 text-[11px] text-bny-slate">
        <Swatch color="#04243C" label="Opus 4.7" />
        <Swatch color="#2B9CAE" label="Sonnet 4.6" />
        <Swatch color="#7FCAD5" label="Haiku 4.5" />
      </div>
      <div className="relative w-full h-52">
        <Chart
          type="bar"
          aria-label={`Stacked monthly cost by model tier with budget line at $${data.budget}.`}
          data-testid="cost-chart"
          data={{
            labels: data.months,
            datasets: [
              {
                label: "Opus",
                data: data.opus,
                backgroundColor: "#04243C",
                stack: "s",
                barPercentage: 0.7,
              },
              {
                label: "Sonnet",
                data: data.sonnet,
                backgroundColor: "#2B9CAE",
                stack: "s",
                barPercentage: 0.7,
              },
              {
                label: "Haiku",
                data: data.haiku,
                backgroundColor: "#7FCAD5",
                stack: "s",
                barPercentage: 0.7,
              },
              {
                label: "Budget",
                type: "line",
                data: Array(data.months.length).fill(data.budget),
                borderColor: "#A32D2D",
                borderWidth: 1.5,
                borderDash: [4, 3],
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
                beginAtZero: true,
                ticks: {
                  color: "#7B8E9D",
                  font: { size: 11 },
                  callback: (v) => `$${(Number(v) / 1000).toFixed(0)}k`,
                },
                grid: { color: "rgba(0,0,0,0.05)" },
              },
              x: {
                stacked: true,
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

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        aria-hidden="true"
        className="w-2.5 h-2.5 rounded-sm"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );
}

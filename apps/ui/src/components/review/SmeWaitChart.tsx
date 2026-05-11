import { Chart } from "react-chartjs-2";
import type { WaitSeries } from "@/types/review";
import { ensureRegistered } from "./charts";

ensureRegistered();

const toneColor: Record<WaitSeries["toneByDomain"][number], string> = {
  ok: "#3B6D11",
  warn: "#2B9CAE",
  danger: "#A32D2D",
  neutral: "#7B8E9D",
};

export function SmeWaitChart({ data }: { data: WaitSeries }) {
  return (
    <div className="bg-white border border-bny-mist rounded-lg p-4">
      <h2 className="text-[13px] font-medium text-bny-ink m-0">
        SME wait time P95
      </h2>
      <div className="text-[11px] text-bny-fog mb-2.5">
        hours · by domain · target dashed
      </div>
      <div className="relative w-full h-56">
        <Chart
          type="bar"
          aria-label={`SME wait time P95 in hours by domain. Target line at ${data.target} hours.`}
          data-testid="wait-chart"
          data={{
            labels: data.domains,
            datasets: [
              {
                label: "Wait P95",
                data: data.values,
                backgroundColor: data.toneByDomain.map((t) => toneColor[t]),
              },
              {
                label: "Target",
                type: "line",
                data: Array(data.domains.length).fill(data.target),
                borderColor: "#7B8E9D",
                borderWidth: 1.5,
                borderDash: [4, 3],
                pointRadius: 0,
                fill: false,
              },
            ],
          }}
          options={{
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: {
                beginAtZero: true,
                ticks: {
                  color: "#7B8E9D",
                  font: { size: 11 },
                  callback: (v) => `${v}h`,
                },
                grid: { color: "rgba(0,0,0,0.05)" },
              },
              y: {
                ticks: { color: "#04243C", font: { size: 11 } },
                grid: { display: false },
              },
            },
          }}
        />
      </div>
    </div>
  );
}

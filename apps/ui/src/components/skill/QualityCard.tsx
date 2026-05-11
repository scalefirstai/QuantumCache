import type { QualityCard as QualityCardModel } from "@/types/skill";

const toneClass: Record<QualityCardModel["tone"], string> = {
  ok: "text-bny-ok",
  warn: "text-bny-ochre",
  neutral: "text-bny-fog",
};

export function QualityCardGrid({ items }: { items: QualityCardModel[] }) {
  return (
    <section
      data-testid="quality-grid"
      className="bg-white border border-bny-mist rounded-lg px-4 py-3.5"
    >
      <h2 className="text-[13px] font-medium text-bny-ink m-0">
        Quality · last 30 days
      </h2>
      <div className="text-[11px] text-bny-fog mb-3">
        measured against eval set v0
      </div>
      <div className="grid grid-cols-2 gap-2.5">
        {items.map((q) => (
          <div
            key={q.label}
            className="bg-bny-paper rounded-md px-3 py-2.5"
          >
            <div className="text-[10px] text-bny-fog">{q.label}</div>
            <div className="text-lg font-medium text-bny-ink mt-0.5">
              {q.value}
            </div>
            <div className={`text-[10px] mt-px ${toneClass[q.tone]}`}>
              {q.target}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

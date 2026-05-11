import type { PipelineQuestion } from "@/types/pipeline";

const ROUTE_BADGE: Record<string, string> = {
  auto_approve: "bg-[#E1F5EE] text-bny-ok",
  sme_queue:    "bg-[#FAEEDA] text-bny-ochre",
  halt:         "bg-[#FCEBEB] text-bny-danger",
};

export function QuestionPicker({
  questions,
  activeQuestionId,
  onSelect,
}: {
  questions: PipelineQuestion[];
  activeQuestionId: string;
  onSelect: (questionId: string) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="DDQ questions"
      className="flex flex-wrap gap-1.5"
      data-testid="pipeline-question-picker"
    >
      {questions.map((q) => {
        const active = q.questionId === activeQuestionId;
        const badge = ROUTE_BADGE[q.route] ?? "bg-bny-haze text-bny-slate";
        return (
          <button
            key={q.questionId}
            type="button"
            role="tab"
            aria-selected={active}
            data-question={q.questionId}
            onClick={() => onSelect(q.questionId)}
            className={[
              "text-xs px-3 py-2 rounded-md border transition-colors text-left min-w-[180px] max-w-[260px]",
              active
                ? "bg-bny-tealLight border-bny-teal text-bny-ink"
                : "bg-white border-bny-mist text-bny-slate hover:border-bny-teal",
            ].join(" ")}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono font-medium text-bny-ink">
                {q.questionId} · {q.framework}
              </span>
              <span
                className={[
                  "text-[10px] uppercase tracking-wider px-1.5 py-px rounded font-medium",
                  badge,
                ].join(" ")}
              >
                {q.route.replace("_", " ")}
              </span>
            </div>
            <div className="mt-0.5 text-[11px] text-bny-slate truncate">
              {q.text}
            </div>
          </button>
        );
      })}
    </div>
  );
}

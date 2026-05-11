import type { TimelineStep } from "@/types/employee";

const tone: Record<TimelineStep["tone"], string> = {
  ink: "bg-bny-ink",
  teal: "bg-bny-teal",
  ochre: "bg-bny-ochre",
};

export function QuestionTimeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <section
      data-testid="question-timeline"
      className="bg-white border border-bny-mist rounded-lg p-4 mt-4"
    >
      <h2 className="text-[13px] font-medium text-bny-ink mb-3 m-0">
        A question through Aria's hands
      </h2>
      <ol
        className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-2"
        data-testid="timeline-steps"
      >
        {steps.map((s) => (
          <li key={s.title} className="text-center">
            <div
              className={`${tone[s.tone]} text-white h-8 rounded flex items-center justify-center text-[11px] font-medium`}
            >
              {s.title}
            </div>
            <div className="text-[10px] text-bny-fog mt-1">{s.caption}</div>
            <div className="text-[10px] text-bny-ink font-medium">
              {s.duration}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

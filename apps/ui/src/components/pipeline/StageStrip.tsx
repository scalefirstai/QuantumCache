import type { PipelineStage, PipelineStageId } from "@/types/pipeline";
import { StageStatusDot } from "./StageStatusDot";

const KIND_LABEL: Record<PipelineStage["kind"], string> = {
  system: "system",
  agent:  "Claude agent",
  rule:   "rule-based",
};

export function StageStrip({
  stages,
  current,
  onSelect,
}: {
  stages: PipelineStage[];
  current: PipelineStageId;
  onSelect: (id: PipelineStageId) => void;
}) {
  return (
    <ol
      role="tablist"
      aria-label="Per-question pipeline stages"
      className="flex flex-wrap gap-1.5"
      data-testid="pipeline-stage-strip"
    >
      {stages.map((s, i) => {
        const active = s.id === current;
        return (
          <li key={s.id}>
            <button
              type="button"
              role="tab"
              aria-selected={active}
              data-stage={s.id}
              data-status={s.status}
              onClick={() => onSelect(s.id)}
              title={`${KIND_LABEL[s.kind]} — ${s.summary}`}
              className={[
                "group flex items-center gap-2 text-xs px-2.5 py-2 rounded-md border transition-colors min-w-[170px]",
                active
                  ? "bg-bny-tealLight border-bny-teal"
                  : "bg-white border-bny-mist hover:border-bny-teal",
              ].join(" ")}
            >
              <span className="inline-block w-4 text-center text-[10px] font-mono text-bny-fog">
                {i + 1}
              </span>
              <StageStatusDot status={s.status} size="sm" />
              <span className="flex-1 text-left leading-tight">
                <span className="block font-medium text-[12px] text-bny-ink">
                  {s.title}
                </span>
                <span className="block text-[10px] text-bny-slate truncate max-w-[150px]">
                  {s.summary}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

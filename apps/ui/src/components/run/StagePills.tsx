import type { Stage, StageId } from "@/types/run";

interface Props {
  stages: Stage[];
  current: StageId;
  onSelect: (id: StageId) => void;
}

export function StagePills({ stages, current, onSelect }: Props) {
  return (
    <div className="flex flex-wrap gap-1.5 mb-5" role="tablist" aria-label="DDQ workflow stages">
      {stages.map((s, i) => {
        const active = s.id === current;
        return (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={active}
            aria-current={active ? "step" : undefined}
            id={`stage-tab-${s.id}`}
            aria-controls={`stage-panel-${s.id}`}
            onClick={() => onSelect(s.id)}
            data-stage={s.id}
            className={[
              "text-xs px-2.5 py-1.5 rounded-md border transition-colors",
              active
                ? "bg-[var(--color-background-info)] text-[var(--color-text-info)] border-[var(--color-border-info)] font-medium"
                : "bg-transparent text-[var(--color-text-secondary)] border-[var(--color-border-tertiary)] hover:bg-[var(--color-background-secondary)]",
            ].join(" ")}
          >
            <span
              className={[
                "inline-block w-[18px] h-[18px] rounded-full text-center leading-[18px] mr-1.5 text-[11px]",
                active
                  ? "bg-white/30"
                  : "bg-[var(--color-background-secondary)]",
              ].join(" ")}
            >
              {i + 1}
            </span>
            {s.title}
          </button>
        );
      })}
    </div>
  );
}

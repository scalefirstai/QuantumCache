interface Props {
  currentIndex: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}

export function StagePagination({ currentIndex, total, onPrev, onNext }: Props) {
  return (
    <div className="flex justify-between gap-2 mt-5">
      <button
        type="button"
        onClick={onPrev}
        disabled={currentIndex === 0}
        className="text-[13px] px-3.5 py-2 rounded-md border border-[var(--color-border-secondary)] bg-transparent disabled:opacity-40 disabled:cursor-not-allowed hover:enabled:bg-[var(--color-background-secondary)]"
      >
        ← Previous
      </button>
      <button
        type="button"
        onClick={onNext}
        disabled={currentIndex >= total - 1}
        className="text-[13px] px-3.5 py-2 rounded-md border border-[var(--color-border-secondary)] bg-transparent disabled:opacity-40 disabled:cursor-not-allowed hover:enabled:bg-[var(--color-background-secondary)]"
      >
        Next →
      </button>
    </div>
  );
}

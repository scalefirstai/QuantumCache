import { Link } from "@tanstack/react-router";
import type { RunIndexEntry } from "@/api/runs";

interface Props {
  runs: RunIndexEntry[];
  activeRunId: string;
}

export function RunPicker({ runs, activeRunId }: Props) {
  return (
    <nav
      aria-label="sealed runs"
      data-testid="run-picker"
      className="flex flex-wrap gap-2 mb-5"
    >
      {runs.map((r) => {
        const active = r.runId === activeRunId;
        return (
          <Link
            key={r.runId}
            to="/runs/$runId"
            params={{ runId: r.runId }}
            data-run={r.runId}
            data-verdict={r.verdict}
            className={[
              "text-[11px] px-2 py-1 rounded-md border max-w-[280px] truncate",
              active
                ? "bg-bny-ink text-white border-bny-ink"
                : "bg-white text-bny-slate border-bny-mist hover:border-bny-teal",
            ].join(" ")}
            title={r.questionPreview}
          >
            <span
              aria-hidden="true"
              className={[
                "inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle",
                r.verdict === "halt" ? "bg-bny-danger" : "bg-bny-ok",
              ].join(" ")}
            />
            {r.framework}
          </Link>
        );
      })}
    </nav>
  );
}

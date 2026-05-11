import { useEffect, useMemo, useCallback } from "react";
import {
  useNavigate,
  useParams,
  useSearch,
} from "@tanstack/react-router";
import { useRunQuery, useRunsIndexQuery } from "@/api/queries";
import { ApiError } from "@/api/client";
import { StagePills } from "@/components/run/StagePills";
import { StagePanel } from "@/components/run/StagePanel";
import { StagePagination } from "@/components/run/StagePagination";
import { RunPicker } from "@/components/run/RunPicker";
import {
  Loading,
  ErrorBox,
  EmptyBox,
} from "@/components/shell/StateMessages";
import type { StageId } from "@/types/run";

function shortHash(h: string | undefined): string {
  if (!h) return "—";
  return h.split(":", 2).pop()!.slice(0, 12);
}

export function RunWalkthroughRoute() {
  const { runId } = useParams({ from: "/runs/$runId" });
  const search = useSearch({ from: "/runs/$runId" });
  const navigate = useNavigate({ from: "/runs/$runId" });
  const { data, isLoading, error, refetch } = useRunQuery(runId);
  const { data: runsIndex } = useRunsIndexQuery();

  const stages = data?.stages ?? [];
  const currentIndex = useMemo(() => {
    if (!data) return 0;
    const i = stages.findIndex((s) => s.id === search.stage);
    return i >= 0 ? i : 0;
  }, [data, stages, search.stage]);

  const goto = useCallback(
    (i: number) => {
      if (i < 0 || i >= stages.length) return;
      const next = stages[i];
      if (!next) return;
      navigate({
        to: "/runs/$runId",
        params: { runId },
        search: { stage: next.id },
        replace: false,
      });
    },
    [navigate, runId, stages],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowRight") goto(currentIndex + 1);
      if (e.key === "ArrowLeft") goto(currentIndex - 1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goto, currentIndex]);

  if (isLoading) return <Loading label="Loading run…" />;
  if (error instanceof ApiError && error.status === 404) {
    return <EmptyBox>Run not found.</EmptyBox>;
  }
  if (error) {
    return (
      <ErrorBox
        title="Failed to load run"
        detail={(error as Error).message}
        onRetry={() => void refetch()}
      />
    );
  }
  if (!data) return null;

  const stage = stages[currentIndex];
  if (!stage) return <EmptyBox>This run has no stages.</EmptyBox>;

  return (
    <div data-testid="run-walkthrough">
      <header className="mb-4">
        <div className="flex items-center gap-2 text-xs text-bny-fog">
          <span className="font-mono">{data.runId}</span>
          {data.verdict && (
            <span
              data-verdict={data.verdict}
              className={[
                "px-1.5 py-px rounded uppercase tracking-wider text-[10px] font-medium",
                data.verdict === "halt"
                  ? "bg-[#FCEBEB] text-bny-danger"
                  : "bg-[#E1F5EE] text-bny-ok",
              ].join(" ")}
            >
              {data.verdict}
            </span>
          )}
          {data.sealedAt && <span>sealed {data.sealedAt.slice(0, 19)}Z</span>}
        </div>
        <h1 className="text-xl font-medium m-0 mt-1">{data.framework}</h1>
        {data.rawQuestion && (
          <p className="text-sm text-bny-slate m-0 mt-1 max-w-3xl">
            {data.rawQuestion}
          </p>
        )}
        {data.merkleRoot && (
          <p className="text-[11px] text-bny-fog font-mono mt-1">
            merkle_root · {shortHash(data.merkleRoot)}
          </p>
        )}
      </header>

      <h2 className="sr-only">
        Interactive walkthrough of the DDQ workflow showing user actions, system
        actions, and data layer activity at each of seven stages.
      </h2>

      {runsIndex && runsIndex.length > 1 && (
        <RunPicker runs={runsIndex} activeRunId={data.runId} />
      )}

      <StagePills
        stages={stages}
        current={stage.id as StageId}
        onSelect={(id) => goto(stages.findIndex((s) => s.id === id))}
      />

      <StagePanel stage={stage} />

      <StagePagination
        currentIndex={currentIndex}
        total={stages.length}
        onPrev={() => goto(currentIndex - 1)}
        onNext={() => goto(currentIndex + 1)}
      />
    </div>
  );
}

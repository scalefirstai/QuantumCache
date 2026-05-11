import { useCallback, useEffect, useMemo } from "react";
import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { usePipelineQuery } from "@/api/queries";
import { ApiError } from "@/api/client";
import { EmailHeader } from "@/components/pipeline/EmailHeader";
import { QuestionPicker } from "@/components/pipeline/QuestionPicker";
import { StageStrip } from "@/components/pipeline/StageStrip";
import { DataInspector } from "@/components/pipeline/DataInspector";
import {
  Loading,
  ErrorBox,
  EmptyBox,
} from "@/components/shell/StateMessages";
import type { PipelineStageId } from "@/types/pipeline";

export function PipelineRoute() {
  const { ddqId } = useParams({ from: "/pipeline/$ddqId" });
  const search = useSearch({ from: "/pipeline/$ddqId" });
  const navigate = useNavigate({ from: "/pipeline/$ddqId" });
  const { data, isLoading, error, refetch } = usePipelineQuery(ddqId);

  const activeQuestionId = search.q ?? data?.questions[0]?.questionId ?? "";
  const activeStageId = search.stage ?? "intake";

  const activeQuestion = useMemo(
    () =>
      data?.questions.find((q) => q.questionId === activeQuestionId) ??
      data?.questions[0],
    [data, activeQuestionId],
  );

  const activeStage = useMemo(
    () =>
      activeQuestion?.stages.find((s) => s.id === activeStageId) ??
      activeQuestion?.stages[0],
    [activeQuestion, activeStageId],
  );

  const setQuestion = useCallback(
    (questionId: string) => {
      navigate({
        to: "/pipeline/$ddqId",
        params: { ddqId },
        search: { q: questionId, stage: "intake" },
        replace: false,
      });
    },
    [navigate, ddqId],
  );

  const setStage = useCallback(
    (stageId: PipelineStageId) => {
      navigate({
        to: "/pipeline/$ddqId",
        params: { ddqId },
        search: { q: activeQuestionId, stage: stageId },
        replace: false,
      });
    },
    [navigate, ddqId, activeQuestionId],
  );

  // Keyboard nav: ← → cycle stages.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!activeQuestion) return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      const stages = activeQuestion.stages;
      const idx = stages.findIndex((s) => s.id === activeStageId);
      if (idx < 0) return;
      if (e.key === "ArrowRight" && idx < stages.length - 1) {
        setStage(stages[idx + 1]!.id);
      }
      if (e.key === "ArrowLeft" && idx > 0) {
        setStage(stages[idx - 1]!.id);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeQuestion, activeStageId, setStage]);

  if (isLoading) return <Loading label="Loading pipeline…" />;
  if (error instanceof ApiError && error.status === 404) {
    return <EmptyBox>Pipeline not found.</EmptyBox>;
  }
  if (error) {
    return (
      <ErrorBox
        title="Failed to load pipeline"
        detail={(error as Error).message}
        onRetry={() => void refetch()}
      />
    );
  }
  if (!data || !activeQuestion || !activeStage) return null;

  return (
    <div
      data-testid="pipeline-view"
      className="flex flex-col gap-3 h-[calc(100vh-7rem)] min-h-[640px]"
    >
      {/* TOP HALF */}
      <div className="flex flex-col gap-3 shrink-0">
        <EmailHeader pipeline={data} />
        <QuestionPicker
          questions={data.questions}
          activeQuestionId={activeQuestion.questionId}
          onSelect={setQuestion}
        />
        <div className="bg-white border border-bny-mist rounded-lg p-3">
          <div className="flex items-baseline justify-between gap-2 mb-2">
            <div className="text-[11px] uppercase tracking-wider text-bny-fog font-medium">
              Pipeline · email → 8-agent roster → sealed
            </div>
            <div className="text-[11px] text-bny-fog">
              {activeQuestion.elapsedMs} ms · {activeQuestion.stages.length} stages ·
              verdict <span className="font-mono">{activeQuestion.verdict}</span>
            </div>
          </div>
          <StageStrip
            stages={activeQuestion.stages}
            current={activeStage.id}
            onSelect={setStage}
          />
        </div>
      </div>

      {/* BOTTOM HALF */}
      <div className="flex-1 min-h-0">
        <DataInspector question={activeQuestion} stage={activeStage} />
      </div>
    </div>
  );
}

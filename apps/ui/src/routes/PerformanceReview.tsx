import { lazy, Suspense } from "react";
import { useParams } from "@tanstack/react-router";
import { ApiError } from "@/api/client";
import { useReviewQuery } from "@/api/queries";
import { ReviewHeader } from "@/components/review/ReviewHeader";
import { ReviewSummary } from "@/components/review/ReviewSummary";
import { ReviewKpiStrip } from "@/components/review/ReviewKpiStrip";
import { AgentScorecard } from "@/components/review/AgentScorecard";
import { Highlights } from "@/components/review/Highlights";
import {
  Loading,
  ErrorBox,
  EmptyBox,
} from "@/components/shell/StateMessages";

const QualityTrendChart = lazy(() =>
  import("@/components/review/QualityTrendChart").then((m) => ({
    default: m.QualityTrendChart,
  })),
);
const CostVsBudgetChart = lazy(() =>
  import("@/components/review/CostVsBudgetChart").then((m) => ({
    default: m.CostVsBudgetChart,
  })),
);
const SmeWaitChart = lazy(() =>
  import("@/components/review/SmeWaitChart").then((m) => ({
    default: m.SmeWaitChart,
  })),
);

export function PerformanceReviewRoute() {
  const { de, period } = useParams({
    from: "/employees/$de/review/$period",
  });
  const { data, isLoading, error, refetch } = useReviewQuery(de, period);

  if (isLoading) return <Loading label="Loading review…" />;
  if (error instanceof ApiError && error.status === 404) {
    return <EmptyBox>Review not found.</EmptyBox>;
  }
  if (error) {
    return (
      <ErrorBox
        title="Failed to load review"
        detail={(error as Error).message}
        onRetry={() => void refetch()}
      />
    );
  }
  if (!data) return null;

  return (
    <div data-testid="performance-review" className="font-sans text-bny-ink">
      <ReviewHeader data={data} />
      <div className="bg-bny-paper border border-bny-mist border-t-0 rounded-b-lg p-4">
        <ReviewSummary summary={data.summary} />
        <ReviewKpiStrip kpis={data.kpis} />
        <div className="mb-3.5">
          <Suspense fallback={<Loading label="Loading chart…" />}>
            <QualityTrendChart data={data.quality} />
          </Suspense>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 mb-3.5">
          <Suspense fallback={<Loading label="Loading chart…" />}>
            <CostVsBudgetChart data={data.cost} />
          </Suspense>
          <Suspense fallback={<Loading label="Loading chart…" />}>
            <SmeWaitChart data={data.wait} />
          </Suspense>
        </div>
        <AgentScorecard rows={data.scorecard} />
        <Highlights whatWentWell={data.whatWentWell} goals={data.goals} />
      </div>
    </div>
  );
}

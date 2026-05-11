import { useParams } from "@tanstack/react-router";
import { ApiError } from "@/api/client";
import { useEmployeeQuery } from "@/api/queries";
import { IdentityCard } from "@/components/employee/IdentityCard";
import { KpiStrip } from "@/components/employee/KpiStrip";
import { AgentRoster } from "@/components/employee/AgentRoster";
import { HumanQueue } from "@/components/employee/HumanQueue";
import { QuestionTimeline } from "@/components/employee/QuestionTimeline";
import {
  Loading,
  ErrorBox,
  EmptyBox,
} from "@/components/shell/StateMessages";

export function EmployeeConsoleRoute() {
  const { de } = useParams({ from: "/employees/$de" });
  const { data, isLoading, error, refetch } = useEmployeeQuery(de);

  if (isLoading) return <Loading label="Loading employee…" />;
  if (error instanceof ApiError && error.status === 404) {
    return <EmptyBox>Employee not found.</EmptyBox>;
  }
  if (error) {
    return (
      <ErrorBox
        title="Failed to load employee"
        detail={(error as Error).message}
        onRetry={() => void refetch()}
      />
    );
  }
  if (!data) return null;

  return (
    <div data-testid="employee-console" className="font-sans text-bny-ink">
      <IdentityCard data={data} />
      <div className="bg-bny-paper border border-bny-mist border-t-0 rounded-b-lg p-4">
        <KpiStrip kpis={data.kpis} />
        <div
          className="grid gap-4"
          style={{ gridTemplateColumns: "minmax(0, 1fr) 240px" }}
        >
          <AgentRoster agents={data.agents} />
          <HumanQueue
            items={data.queue.items}
            awaiting={data.queue.awaiting}
            decisionRights={data.decisionRights}
          />
        </div>
        <QuestionTimeline steps={data.timeline} />
      </div>
    </div>
  );
}

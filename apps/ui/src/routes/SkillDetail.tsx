import { useParams } from "@tanstack/react-router";
import { ApiError } from "@/api/client";
import { useSkillQuery } from "@/api/queries";
import { SkillHeader } from "@/components/skill/SkillHeader";
import { SkillSignature } from "@/components/skill/SkillSignature";
import { PipelineDiagram } from "@/components/skill/PipelineDiagram";
import { SkillIOTable } from "@/components/skill/SkillIO";
import { LatencyBudget } from "@/components/skill/LatencyBudget";
import { QualityCardGrid } from "@/components/skill/QualityCard";
import { FailureModes } from "@/components/skill/FailureModes";
import {
  Loading,
  ErrorBox,
  EmptyBox,
} from "@/components/shell/StateMessages";

export function SkillDetailRoute() {
  const { skillId } = useParams({ from: "/skills/$skillId" });
  const { data, isLoading, error, refetch } = useSkillQuery(skillId);

  if (isLoading) return <Loading label="Loading skill…" />;
  if (error instanceof ApiError && error.status === 404) {
    return <EmptyBox>Skill not found.</EmptyBox>;
  }
  if (error) {
    return (
      <ErrorBox
        title="Failed to load skill"
        detail={(error as Error).message}
        onRetry={() => void refetch()}
      />
    );
  }
  if (!data) return null;

  return (
    <div data-testid="skill-detail" className="font-sans text-bny-ink">
      <SkillHeader name={data.name} tagline={data.tagline} />
      <div className="bg-bny-paper border border-bny-mist border-t-0 rounded-b-lg p-4">
        <SkillSignature rows={data.signature} />

        <section
          data-testid="pipeline"
          className="bg-white border border-bny-mist rounded-lg px-4 py-3.5 mb-3.5"
        >
          <h2 className="text-[13px] font-medium text-bny-ink m-0">
            Internal pipeline
          </h2>
          <div className="text-[11px] text-bny-fog mb-2.5">
            BM25 ∪ dense → rerank → top-k
          </div>
          <PipelineDiagram
            nodes={data.pipeline.nodes}
            edges={data.pipeline.edges}
            cache={data.pipeline.cache}
          />
        </section>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 mb-3.5">
          <SkillIOTable title="Inputs" items={data.inputs} />
          <SkillIOTable
            title={`Output · ${data.output.typeName}`}
            items={data.output.fields}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 mb-3.5">
          <LatencyBudget bars={data.latency.budget} max={data.latency.max} />
          <QualityCardGrid items={data.quality} />
        </div>

        <FailureModes items={data.failureModes} />
      </div>
    </div>
  );
}

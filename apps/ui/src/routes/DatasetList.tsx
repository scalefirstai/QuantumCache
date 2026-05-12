import { useParams } from "@tanstack/react-router";
import { ErrorBox } from "@/components/shell/StateMessages";
import { KnowledgeListRoute } from "./KnowledgeList";
import { CanonicalListRoute } from "./CanonicalList";
import { AuditListRoute } from "./AuditList";

/**
 * `/datasets/$type` dispatcher. Splits to the dataset-specific list view
 * so each underlying page can own its own filters/state without
 * conditional spaghetti.
 */
export function DatasetListRoute() {
  const { type } = useParams({ from: "/datasets/$type" });
  switch (type) {
    case "knowledge":
      return <KnowledgeListRoute />;
    case "canonical":
      return <CanonicalListRoute />;
    case "audit":
      return <AuditListRoute />;
    default:
      return (
        <ErrorBox
          title="Unknown dataset"
          detail={`No view for "${type}". Try /datasets.`}
        />
      );
  }
}

import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from "@tanstack/react-router";
import { AppShell } from "./components/shell/AppShell";
import { AgentsRoute } from "./routes/Agents";
import { AgentDetailRoute } from "./routes/AgentDetail";
import { RunWalkthroughRoute } from "./routes/RunWalkthrough";
import { PipelineRoute } from "./routes/Pipeline";
import { EmployeeConsoleRoute } from "./routes/EmployeeConsole";
import { PerformanceReviewRoute } from "./routes/PerformanceReview";
import { SkillDetailRoute } from "./routes/SkillDetail";
import { ModelsRoute } from "./routes/Models";
import { SkillsRoute } from "./routes/Skills";
import { PlaygroundRoute } from "./routes/Playground";
import { HomeRoute } from "./routes/Home";
import { DatasetsRoute } from "./routes/Datasets";
import { DatasetListRoute } from "./routes/DatasetList";
import { KnowledgeDetailRoute } from "./routes/KnowledgeDetail";
import { CanonicalDetailRoute } from "./routes/CanonicalDetail";
import { AuditDetailRoute } from "./routes/AuditDetail";
import { RulesListRoute } from "./routes/RulesList";
import { RuleDetailRoute } from "./routes/RuleDetail";
import { RuleQueueRoute } from "./routes/RuleQueue";

const rootRoute = createRootRoute({
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: HomeRoute,
});

const runRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs/$runId",
  validateSearch: (search: Record<string, unknown>): { stage?: string } => ({
    stage: typeof search.stage === "string" ? search.stage : undefined,
  }),
  component: RunWalkthroughRoute,
});

const pipelineRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/pipeline/$ddqId",
  validateSearch: (
    search: Record<string, unknown>,
  ): { q?: string; stage?: import("./types/pipeline").PipelineStageId } => ({
    q: typeof search.q === "string" ? search.q : undefined,
    stage:
      typeof search.stage === "string"
        ? (search.stage as import("./types/pipeline").PipelineStageId)
        : undefined,
  }),
  component: PipelineRoute,
});

const employeeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/employees/$de",
  component: EmployeeConsoleRoute,
});

const reviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/employees/$de/review/$period",
  component: PerformanceReviewRoute,
});

const skillRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/skills/$skillId",
  component: SkillDetailRoute,
});

const agentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/agents",
  component: AgentsRoute,
});

const agentDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/agents/$agentId",
  component: AgentDetailRoute,
});

const modelsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/models",
  component: ModelsRoute,
});

const skillsListRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/skills",
  component: SkillsRoute,
});

const playgroundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/playground",
  component: PlaygroundRoute,
});

const datasetsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/datasets",
  component: DatasetsRoute,
});

const datasetListRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/datasets/$type",
  component: DatasetListRoute,
});

const knowledgeDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/datasets/knowledge/$docId",
  component: KnowledgeDetailRoute,
});

const canonicalDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/datasets/canonical/$canonicalId",
  component: CanonicalDetailRoute,
});

const auditDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/datasets/audit/$runId",
  component: AuditDetailRoute,
});

const rulesListRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/rules",
  component: RulesListRoute,
});

const ruleQueueRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/rules/queue",
  component: RuleQueueRoute,
});

const ruleDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/rules/$ruleId",
  component: RuleDetailRoute,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  runRoute,
  pipelineRoute,
  employeeRoute,
  reviewRoute,
  skillRoute,
  agentsRoute,
  agentDetailRoute,
  modelsRoute,
  skillsListRoute,
  playgroundRoute,
  datasetsRoute,
  datasetListRoute,
  knowledgeDetailRoute,
  canonicalDetailRoute,
  auditDetailRoute,
  rulesListRoute,
  ruleQueueRoute,
  ruleDetailRoute,
]);

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
});

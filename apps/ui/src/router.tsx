import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from "@tanstack/react-router";
import { AppShell } from "./components/shell/AppShell";
import { RunWalkthroughRoute } from "./routes/RunWalkthrough";
import { PipelineRoute } from "./routes/Pipeline";
import { EmployeeConsoleRoute } from "./routes/EmployeeConsole";
import { PerformanceReviewRoute } from "./routes/PerformanceReview";
import { SkillDetailRoute } from "./routes/SkillDetail";
import { HomeRoute } from "./routes/Home";

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

const routeTree = rootRoute.addChildren([
  indexRoute,
  runRoute,
  pipelineRoute,
  employeeRoute,
  reviewRoute,
  skillRoute,
]);

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
});

import { http, HttpResponse } from "msw";
import employeeFixture from "@/mocks/fixtures/employee.json";
import reviewFixture from "@/mocks/fixtures/review-q1.json";
import skillFixture from "@/mocks/fixtures/skill-retrieval.json";
import runsIndex from "@/mocks/fixtures/runs-index.json";

const base = "http://localhost";

// Eagerly import every sealed-run fixture so the handler can dispatch by id.
// import.meta.glob is Vite/Vitest only; safe in test environment.
const runModules = import.meta.glob<{ default: unknown }>(
  "@/mocks/fixtures/runs/*.json",
  { eager: true },
);
const runsById = new Map<string, unknown>(
  Object.entries(runModules).map(([path, mod]) => {
    const id = path.split("/").pop()!.replace(/\.json$/, "");
    return [id, mod.default];
  }),
);

export const handlers = [
  http.get(`${base}/api/v1/runs`, () => HttpResponse.json(runsIndex)),
  http.get(`${base}/api/v1/runs/:id`, ({ params }) => {
    const id = String(params.id);
    const view = runsById.get(id);
    if (!view) {
      return HttpResponse.json({ error: "not found" }, { status: 404 });
    }
    return HttpResponse.json(view);
  }),
  http.get(`${base}/api/v1/employees/:id`, ({ params }) => {
    if (params.id !== "aria") {
      return HttpResponse.json({ error: "not found" }, { status: 404 });
    }
    return HttpResponse.json(employeeFixture);
  }),
  http.get(
    `${base}/api/v1/employees/:id/reviews/:period`,
    ({ params }) => {
      if (params.id !== "aria" || params.period !== "q1-2026") {
        return HttpResponse.json({ error: "not found" }, { status: 404 });
      }
      return HttpResponse.json(reviewFixture);
    },
  ),
  http.get(`${base}/api/v1/skills/:id`, ({ params }) => {
    if (params.id !== "retrieval-hybrid") {
      return HttpResponse.json({ error: "not found" }, { status: 404 });
    }
    return HttpResponse.json(skillFixture);
  }),
];

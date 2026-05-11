import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithRouter } from "../utils/renderRoute";
import { RunWalkthroughRoute } from "@/routes/RunWalkthrough";
import { EmployeeConsoleRoute } from "@/routes/EmployeeConsole";
import * as runs from "@/api/runs";
import * as employees from "@/api/employees";
import { ApiError } from "@/api/client";

describe("Integration · loading, errors, empty states", () => {
  it("T-I1 shows a loading state while fetching", async () => {
    let resolve: ((v: never) => void) | undefined;
    vi.spyOn(runs, "getRun").mockImplementation(
      () => new Promise<never>((r) => {
        resolve = r;
      }),
    );
    renderWithRouter({
      initialEntries: ["/runs/run_01HQK4M9"],
      routes: [
        {
          path: "/runs/$runId",
          Component: RunWalkthroughRoute,
          validateSearch: (s) => ({
            stage: typeof s.stage === "string" ? s.stage : undefined,
          }),
        },
      ],
    });
    expect(await screen.findByText(/Loading run/)).toBeInTheDocument();
    if (resolve) resolve(null as never);
  });

  it("T-I2 renders error card with retry that refetches", async () => {
    const spy = vi
      .spyOn(employees, "getEmployee")
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce({
        id: "aria",
        name: "Aria",
        role: "DDQ specialist",
        runId: "run_01",
        runDescription: "ok",
        reportingLine: "ok",
        progressPct: 50,
        kpis: [],
        agents: [],
        queue: { awaiting: 0, items: [] },
        decisionRights: [],
        timeline: [],
      });
    renderWithRouter({
      initialEntries: ["/employees/aria"],
      routes: [{ path: "/employees/$de", Component: EmployeeConsoleRoute }],
    });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Failed to load employee");
    await userEvent.click(screen.getByRole("button", { name: /Retry/ }));
    await waitFor(() =>
      expect(screen.getByTestId("employee-console")).toBeInTheDocument(),
    );
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("T-I3 unknown :runId shows 'Run not found' empty state", async () => {
    vi.spyOn(runs, "getRun").mockRejectedValue(
      new ApiError("Run not found", 404, "/api/v1/runs/none"),
    );
    renderWithRouter({
      initialEntries: ["/runs/missing"],
      routes: [
        {
          path: "/runs/$runId",
          Component: RunWalkthroughRoute,
          validateSearch: (s) => ({
            stage: typeof s.stage === "string" ? s.stage : undefined,
          }),
        },
      ],
    });
    expect(await screen.findByText(/Run not found/)).toBeInTheDocument();
  });
});

import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { renderWithRouter } from "../utils/renderRoute";
import { EmployeeConsoleRoute } from "@/routes/EmployeeConsole";
function renderConsole() {
    return renderWithRouter({
        initialEntries: ["/employees/aria"],
        routes: [{ path: "/employees/$de", Component: EmployeeConsoleRoute }],
    });
}
describe("Digital employee console", () => {
    it("T-E1 KPI strip shows four cards driven by real wire-up data", async () => {
        renderConsole();
        const strip = await screen.findByTestId("kpi-strip");
        const values = within(strip)
            .getAllByText(/^(\d|0\.).*(%|s|ms)$/)
            .map((el) => el.textContent);
        expect(values).toEqual(["80.0%", "20.0%", "20.0%", "2379ms"]);
    });
    it("T-E2 agent roster renders 8 specialists with model lines", async () => {
        renderConsole();
        const roster = await screen.findByTestId("agent-roster");
        const items = within(roster).getAllByRole("listitem");
        expect(items).toHaveLength(8);
        expect(within(items[0]).getByText(/QuestionMapper/)).toBeInTheDocument();
        expect(within(items[0]).getByText(/Haiku 4\.5 · v1\.2\.0/)).toBeInTheDocument();
    });
    it("T-E3 human queue surfaces SME rows including Legal halted", async () => {
        renderConsole();
        const queue = await screen.findByTestId("human-queue");
        const items = within(queue).getAllByRole("listitem");
        // Bootstrap data: 4 SME rows + Legal review (halted) since ADVERSARIAL run halted.
        expect(items.length).toBeGreaterThanOrEqual(4);
        const legal = items.find((el) => /Legal review/.test(el.textContent ?? ""));
        expect(legal).toBeDefined();
        expect(legal.getAttribute("data-status")).toBe("halted");
    });
    it("T-E4 timeline collapses to mobile grid on narrow viewports", async () => {
        renderConsole();
        const tl = await screen.findByTestId("timeline-steps");
        expect(tl.className).toMatch(/grid-cols-1/);
        expect(tl.className).toMatch(/lg:grid-cols-5/);
    });
    it("T-E5 identity card shows progress from fixture", async () => {
        renderConsole();
        await waitFor(() => screen.getByTestId("employee-console"));
        // Bootstrap state: all 5 runs sealed → 100%.
        expect(screen.getByTestId("run-progress")).toHaveTextContent("100%");
    });
});

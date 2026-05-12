import { jsx as _jsx } from "react/jsx-runtime";
import { describe, expect, it, vi, beforeAll } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithRouter } from "../utils/renderRoute";
import { PerformanceReviewRoute } from "@/routes/PerformanceReview";
// jsdom doesn't ship a usable canvas; stub Chart.js and react-chartjs-2 so the
// route renders without exercising the real renderer.
vi.mock("chart.js", () => ({
    Chart: { register: () => undefined },
    CategoryScale: {},
    LinearScale: {},
    PointElement: {},
    LineElement: {},
    BarElement: {},
    LineController: {},
    BarController: {},
    Tooltip: {},
    Legend: {},
    Title: {},
}));
vi.mock("react-chartjs-2", () => ({
    Chart: (props) => (_jsx("canvas", { "data-testid": `chartjs-${props.type}`, "data-datasets": Array.isArray(props.data.datasets)
            ? props.data.datasets.length
            : 0 })),
}));
function renderReview() {
    return renderWithRouter({
        initialEntries: ["/employees/aria/review/q1-2026"],
        routes: [
            {
                path: "/employees/$de/review/$period",
                Component: PerformanceReviewRoute,
            },
        ],
    });
}
beforeAll(() => {
    // jsdom needs this for chart.js even when stubbed
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    HTMLCanvasElement.prototype.getContext = () => null;
});
describe("Performance review", () => {
    it("T-P1 renders three lazy-loaded chart canvases", async () => {
        renderReview();
        await waitFor(() => screen.getByTestId("performance-review"));
        const canvases = await screen.findAllByTestId(/chartjs-/);
        expect(canvases).toHaveLength(3);
        const types = canvases.map((c) => c.getAttribute("data-testid")).sort();
        expect(types).toEqual(["chartjs-bar", "chartjs-bar", "chartjs-line"]);
    });
    it("T-P2 KPI strip renders with status tone per metric (real data)", async () => {
        renderReview();
        const strip = await screen.findByTestId("review-kpi-strip");
        const cards = strip.querySelectorAll("[data-tone]");
        expect(cards).toHaveLength(5);
        // Real-data tones derived from bootstrap metrics:
        //   Auto-pass 80% ≥ 70% target              → ok
        //   Library hit 20% well under 92% target   → danger
        //   Recall@10 0.56 under 0.85               → warn
        //   Halt rate 35.6% well above 10% target   → danger
        //   P95 2379ms above 2000ms                 → danger
        expect(cards[0].getAttribute("data-tone")).toBe("ok");
        expect(cards[1].getAttribute("data-tone")).toBe("danger");
        expect(cards[2].getAttribute("data-tone")).toBe("warn");
        expect(cards[3].getAttribute("data-tone")).toBe("danger");
        expect(cards[4].getAttribute("data-tone")).toBe("danger");
    });
    it("T-P3 agent scorecard shows 8 rows with real call counts", async () => {
        renderReview();
        const card = await screen.findByTestId("agent-scorecard");
        const rows = card.querySelectorAll("tbody tr");
        expect(rows).toHaveLength(8);
        const draft = card.querySelector('tr[data-agent="DraftComposer"] td:nth-child(2)');
        // DraftComposer is called once per run (5 sealed runs).
        expect(draft?.textContent).toBe("5");
    });
    it("T-P4 quality chart instance has 4 datasets (3 series + target)", async () => {
        renderReview();
        const line = await screen.findByTestId("chartjs-line");
        expect(line.getAttribute("data-datasets")).toBe("4");
    });
});

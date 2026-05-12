import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { renderWithRouter } from "../utils/renderRoute";
import { SkillDetailRoute } from "@/routes/SkillDetail";
function renderSkill() {
    return renderWithRouter({
        initialEntries: ["/skills/retrieval-hybrid"],
        routes: [{ path: "/skills/$skillId", Component: SkillDetailRoute }],
    });
}
describe("Skill detail", () => {
    it("T-S1 header shows Retrieval.hybrid and the SKILL pill", async () => {
        renderSkill();
        await waitFor(() => screen.getByTestId("skill-detail"));
        expect(screen.getByText("Retrieval.hybrid")).toBeInTheDocument();
        expect(screen.getByText("SKILL")).toBeInTheDocument();
    });
    it("T-S2 signature row renders five (label, value) pairs from real data", async () => {
        renderSkill();
        const sig = await screen.findByTestId("skill-signature");
        const dts = sig.querySelectorAll("dt");
        const dds = sig.querySelectorAll("dd");
        expect(dts).toHaveLength(5);
        expect(dds).toHaveLength(5);
        expect(dts[0].textContent).toBe("Signature");
        expect(dds[0].textContent).toContain("hybrid(question, k=10)");
        // Corpus row reflects the real 13,466-span index.
        expect(sig.textContent).toContain("13466 spans");
    });
    it("T-S3 pipeline SVG exposes data-stage-id hooks for each node", async () => {
        renderSkill();
        const svg = await screen.findByTestId("pipeline-diagram");
        const ids = Array.from(svg.querySelectorAll("[data-stage-id]")).map((g) => g.getAttribute("data-stage-id"));
        expect(ids).toEqual([
            "query",
            "bm25",
            "dense",
            "merge",
            "filter",
            "rerank",
            "output",
        ]);
    });
    it("T-S4 cache callout reflects bootstrap state (cache not yet wired)", async () => {
        renderSkill();
        const cache = await screen.findByTestId("pipeline-cache-callout");
        expect(cache.textContent).toContain("HIT RATE · n/a");
    });
    it("T-S5 latency bars carry aria values; total uncached equals 650ms", async () => {
        renderSkill();
        const budget = await screen.findByTestId("latency-budget");
        const bars = within(budget).getAllByRole("progressbar");
        expect(bars.length).toBe(6);
        bars.forEach((bar) => {
            expect(bar).toHaveAttribute("aria-valuemin", "0");
            expect(bar).toHaveAttribute("aria-valuemax", "1200");
        });
        const total = within(budget).getByLabelText("Total uncached");
        expect(total).toHaveAttribute("aria-valuenow", "650");
    });
});

import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithRouter } from "../utils/renderRoute";
import { RunWalkthroughRoute } from "@/routes/RunWalkthrough";

const titles = [
  "Intake",
  "Classify",
  "Retrieve",
  "Draft",
  "Validate",
  "Approve",
  "Respond",
];

const RUN_ID = "run_20260510T125906_2b46b0fd";

function renderRun(initial = `/runs/${RUN_ID}`) {
  return renderWithRouter({
    initialEntries: [initial],
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
}

describe("Run walkthrough", () => {
  it("T-R1 renders the seven stage pills with correct titles", async () => {
    renderRun();
    await waitFor(() =>
      expect(screen.getByTestId("run-walkthrough")).toBeInTheDocument(),
    );
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(7);
    tabs.forEach((tab, i) => {
      expect(tab).toHaveTextContent(titles[i]!);
    });
  });

  it("T-R2 stage 1 has aria-current=step on initial load", async () => {
    renderRun();
    await waitFor(() => screen.getByTestId("run-walkthrough"));
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAttribute("aria-current", "step");
    expect(tabs[1]).not.toHaveAttribute("aria-current", "step");
  });

  it("T-R3 clicking pill 4 swaps the active panel", async () => {
    const user = userEvent.setup();
    renderRun();
    await waitFor(() => screen.getByTestId("run-walkthrough"));

    const tab = screen.getByRole("tab", { name: /Draft/ });
    await user.click(tab);

    const panel = await screen.findByRole("tabpanel");
    expect(panel).toHaveAttribute("data-stage", "draft");
    expect(screen.getByRole("button", { name: /Previous/ })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: /Next/ })).not.toBeDisabled();
  });

  it("T-R4 ArrowRight advances; ArrowLeft on stage 1 is a no-op", async () => {
    const user = userEvent.setup();
    renderRun();
    await waitFor(() => screen.getByTestId("run-walkthrough"));

    expect(screen.getByRole("button", { name: /Previous/ })).toBeDisabled();
    await user.keyboard("{ArrowLeft}");
    let panel = await screen.findByRole("tabpanel");
    expect(panel).toHaveAttribute("data-stage", "intake");

    await user.keyboard("{ArrowRight}");
    panel = await screen.findByRole("tabpanel");
    expect(panel).toHaveAttribute("data-stage", "classify");
  });

  it("T-R5 ArrowRight at last stage is a no-op and Next is disabled", async () => {
    const user = userEvent.setup();
    renderRun("/runs/run_20260510T125906_2b46b0fd?stage=respond");
    await waitFor(() => screen.getByTestId("run-walkthrough"));

    expect(screen.getByRole("button", { name: /Next/ })).toBeDisabled();
    await user.keyboard("{ArrowRight}");
    const panel = await screen.findByRole("tabpanel");
    expect(panel).toHaveAttribute("data-stage", "respond");
  });

  it("T-R6 deep link ?stage=validate opens stage 5", async () => {
    renderRun("/runs/run_20260510T125906_2b46b0fd?stage=validate");
    const panel = await screen.findByRole("tabpanel");
    expect(panel).toHaveAttribute("data-stage", "validate");
  });

  it("T-R7 each stage renders 3 data cells with correct lane pills", async () => {
    renderRun();
    await waitFor(() => screen.getByTestId("run-walkthrough"));
    const panel = await screen.findByRole("tabpanel");
    const cells = within(panel).getAllByText(/^(knowledge|canonical|audit)$/);
    expect(cells.length).toBeGreaterThanOrEqual(3);
    const lanes = cells
      .slice(0, 3)
      .map((el) => el.getAttribute("data-lane"));
    expect(lanes).toEqual(["knowledge", "audit", "canonical"]);
  });

  it("T-R8 token rendering produces inline code without injecting raw HTML", async () => {
    renderRun();
    await waitFor(() => screen.getByTestId("run-walkthrough"));
    const panel = await screen.findByRole("tabpanel");
    const code = within(panel).getAllByText("run_id")[0]!;
    expect(code.tagName).toBe("CODE");
    // No script tags anywhere in the rendered tree
    expect(panel.querySelector("script")).toBeNull();
  });

  it("T-R9 header shows verdict pill and merkle root short hash", async () => {
    renderRun();
    await waitFor(() => screen.getByTestId("run-walkthrough"));
    const verdict = await screen.findByText(/^pass$/);
    expect(verdict.getAttribute("data-verdict")).toBe("pass");
    expect(screen.getByText(/merkle_root · /)).toHaveTextContent(
      "merkle_root · f1468f1b6765",
    );
  });

  it("T-R10 run picker lists all five sealed runs", async () => {
    renderRun();
    const picker = await screen.findByTestId("run-picker");
    const links = within(picker).getAllByRole("link");
    expect(links).toHaveLength(5);
    const verdicts = links.map((l) => l.getAttribute("data-verdict")).sort();
    expect(verdicts).toEqual(["halt", "pass", "pass", "pass", "pass"]);
  });
});

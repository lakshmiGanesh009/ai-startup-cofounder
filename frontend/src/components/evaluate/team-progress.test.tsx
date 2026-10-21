import { render, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { TeamProgress } from "@/components/evaluate/team-progress";
import type { Step } from "@/lib/api";

describe("the team's progress", () => {
  test("before a request it explains the stages", () => {
    render(<TeamProgress steps={[]} live={false} />);

    expect(screen.getByRole("heading", { name: "How the team works" })).toBeTruthy();
    expect(screen.getByLabelText("Plan: Waiting").textContent).toContain(
      "Turns the brief into the decision to make, and assigns the specialists it needs.",
    );
    expect(screen.queryByText("Writing")).toBeNull();
  });

  test("a specialist that failed is marked, and a cross-check with one report is skipped", () => {
    const steps: Step[] = [
      { type: "start", node: "plan", at: 0 },
      { type: "done", node: "plan", at: 8, summary: "Planned the work.", assigned: ["finance", "risk"] },
      { type: "start", node: "finance", at: 8.1 },
      { type: "start", node: "risk", at: 8.1 },
      { type: "done", node: "risk", at: 20, summary: "Could not write its report: the LLM call failed.", failed: true },
      { type: "done", node: "finance", at: 25, summary: "Wrote its report (500 words)." },
      { type: "start", node: "review", at: 25.1 },
      { type: "done", node: "review", at: 33, summary: "Reviewed 1 report: approved 1." },
      { type: "start", node: "synthesis", at: 33.1 },
    ];

    render(<TeamProgress steps={steps} live />);

    expect(screen.getByRole("heading", { name: "The team at work" })).toBeTruthy();
    const reports = screen.getByLabelText("Reports: Done");
    expect(within(reports).getByText("Failed")).toBeTruthy();
    expect(within(reports).getAllByText("Not needed")).toHaveLength(2);
    expect(screen.getByLabelText("Review: Done").textContent).toContain("Reviewed 1 report: approved 1.");
    expect(screen.getByLabelText("Cross-check: Skipped")).toBeTruthy();
    expect(screen.getByLabelText("Strategy: Working")).toBeTruthy();
  });

  test("each stage and specialist wears the colour of the agent who does it", () => {
    const steps: Step[] = [
      { type: "start", node: "plan", at: 0 },
      { type: "done", node: "plan", at: 8, summary: "Planned the work.", assigned: ["marketing", "finance"] },
      { type: "start", node: "marketing", at: 8.1 },
      { type: "start", node: "finance", at: 8.1 },
      { type: "done", node: "marketing", at: 20, summary: "Wrote its report (400 words)." },
    ];

    const { container } = render(<TeamProgress steps={steps} live />);

    // The plan is the Chief of Staff's, done: a filled mark in its colour.
    const plan = screen.getByLabelText("Plan: Done");
    expect(plan.querySelector(".agent-chief.bg-agent-solid")).toBeTruthy();
    // The reports are shared: a ring of the specialists' colours, turning while they write.
    const ring = screen.getByLabelText("Reports: Working").querySelector(".stage-turning") as HTMLElement;
    expect(ring.style.background).toContain("var(--agent-marketing)");
    expect(ring.style.background).toContain("var(--agent-risk)");
    // Each specialist's row is in its colour, and says where it is.
    const finance = container.querySelector("li.agent-finance");
    expect(finance?.textContent).toContain("Writing");
    expect(container.querySelector("li.agent-marketing")?.textContent).toContain("Done");
  });
});

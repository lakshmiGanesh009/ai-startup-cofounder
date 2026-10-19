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
});

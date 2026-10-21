import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { EvaluateApp } from "@/components/evaluate/evaluate-app";
import { Markdown } from "@/components/markdown";
import type { EconomicData, EvaluateResponse, Step } from "@/lib/api";
import { BackendProvider } from "@/lib/backend";
import { activity, nodeStates, STAGES, stageState } from "@/lib/team";
import { fakeBackend, RESULT, sse, STEPS } from "@/test/backend";

const ECONOMIC: EconomicData = {
  figures: [
    {
      id: "DGS10",
      title: "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity",
      units: "Percent",
      frequency: "Daily",
      date: "2026-10-17",
      value: 4.12,
      year_ago: 3.98,
      change: "up 0.14 points",
      why: "The usual risk-free rate a discount rate starts from.",
      link: "https://fred.stlouisfed.org/series/DGS10",
    },
    {
      id: "CES6562000001",
      title: "Average Hourly Earnings of All Employees, Health Care",
      units: "Dollars per Hour",
      frequency: "Monthly",
      date: "2026-09-01",
      value: 36.4,
      year_ago: null,
      change: "",
      why: 'Found for "health care wages".',
      link: "https://fred.stlouisfed.org/series/CES6562000001",
    },
  ],
  searches: ["health care wages"],
  note: "Left out: CPIAUCSL could not be read.",
};

describe("official figures from FRED", () => {
  test("a figure the agents cite links to its page on FRED", () => {
    const { container } = render(<Markdown>{"Borrowing costs 4.12% [FRED · DGS10; finance]."}</Markdown>);
    const link = container.querySelector("a.doc-cite")!;
    expect(link.getAttribute("href")).toBe("https://fred.stlouisfed.org/series/DGS10");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.textContent).toBe("FREDDGS10");
    expect(container.querySelector(".cite.agent-finance")).toBeTruthy();
  });

  test("the result lists the figures the team read, and the summary counts them", async () => {
    const result: EvaluateResponse = { ...RESULT, economic: ECONOMIC };
    fakeBackend({ "POST /evaluate/stream": () => ({ stream: sse(STEPS, { result }) }) });
    const user = userEvent.setup();
    render(
      <BackendProvider>
        <EvaluateApp />
      </BackendProvider>,
    );
    await user.type(screen.getByLabelText("The brief"), "An idea");
    await user.click(screen.getByRole("checkbox", { name: /Research it and check the brief first/ }));
    await user.click(screen.getByRole("button", { name: /^Evaluate\s*⌘↵$/ }));
    await screen.findByRole("heading", { name: "Go with conditions" });

    expect(within(screen.getByRole("complementary", { name: "The team's reviews" })).getByText("2 official figures from FRED")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Research" }));
    const figures = screen.getByRole("region", { name: "Official figures" });
    const rows = within(figures).getAllByRole("row").slice(1);
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("4.12 Percent2026-10-17up 0.14 points"),
      expect.stringContaining("36.4 Dollars per Hour2026-09-01—"),
    ]);
    expect(within(figures).getByRole("link", { name: "DGS10" }).getAttribute("href")).toBe(
      "https://fred.stlouisfed.org/series/DGS10",
    );
    expect(within(figures).getByText("Left out: CPIAUCSL could not be read.")).toBeTruthy();
  });

  test("the look-ups are part of the research stage, and say what they are doing", () => {
    const research = STAGES.find((stage) => stage.key === "research")!;
    const looking: Step[] = [
      { type: "done", node: "plan", at: 5, assigned: ["finance"] },
      { type: "start", node: "lookup", at: 5 },
    ];
    expect(stageState(research, nodeStates(looking), ["finance"])).toBe("working");
    expect(activity(looking)).toBe("Looking up the official figures on FRED.");
    const looked: Step[] = [...looking, { type: "done", node: "lookup", at: 9 }, { type: "start", node: "finance", at: 9 }];
    expect(stageState(research, nodeStates(looked), ["finance"])).toBe("done");
  });
});

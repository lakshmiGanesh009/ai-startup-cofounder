import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import ReportsPage from "@/app/reports/page";
import { BackendProvider } from "@/lib/backend";
import { fakeReports, SAMPLE_REPORT, SESSION } from "@/test/reports";

function renderPage() {
  return render(
    <BackendProvider>
      <ReportsPage />
    </BackendProvider>,
  );
}

const user = () => userEvent.setup();

const CHAPTERS = [
  "Executive summary",
  "Market & marketing",
  "Technical & operations",
  "Financial plan",
  "Risk & compliance",
  "Success metrics",
  "The team's report",
];

async function openChapter(name: string) {
  await userEvent.click(screen.getByRole("tab", { name }));
  return screen.getByRole("tabpanel", { name });
}

// The actions behind the "More actions" button.
async function moreActions(action: string) {
  await user().click(await screen.findByRole("button", { name: "More actions" }));
  await user().click(screen.getByRole("menuitem", { name: new RegExp(`^${action}`) }));
}

describe("the Reports page, before the proposal", () => {
  test("shows the team's report, each section with its source", async () => {
    fakeReports();
    renderPage();

    expect(await screen.findByRole("heading", { name: "Launch Strategy" })).toBeTruthy();
    expect(screen.getByText("Team report")).toBeTruthy();
    expect(screen.getByText("Written by the Chief of Staff")).toBeTruthy();
    expect(screen.getByText("Decided by the Chief of Staff")).toBeTruthy();
    expect(screen.getByText("Written by the Financial Planning Agent")).toBeTruthy();
    expect(screen.getByRole("option").textContent).toMatch(/team report, 19 Oct, 09:30 UTC\)$/);
    expect(screen.getByText(SESSION.slice(0, 8))).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Revise with the team" })).toBeNull();
  });

  test("the web research the team started from is a section, with its sources", async () => {
    const backend = fakeReports();
    backend.state.report.sections = [
      ...backend.state.report.sections,
      {
        key: "research",
        title: "Web Research",
        body: "- Tools cost $20-$300 per provider a month. [1]\n\n**Sources**\n\n1. [Scheduling software prices](https://prices.example)",
      },
    ];
    renderPage();

    const research = await screen.findByRole("region", { name: "Web Research" });

    expect(within(research).getByText("Found on the web with Tavily")).toBeTruthy();
    expect(within(research).getByRole("heading", { name: "Sources" })).toBeTruthy();
    expect(within(research).getByRole("link", { name: "Scheduling software prices" }).getAttribute("href")).toBe(
      "https://prices.example",
    );
  });

  test("writing the proposal shows its chapters, with the sliders' efforts sent", async () => {
    const { sent } = fakeReports();
    renderPage();
    await screen.findByRole("heading", { name: "Launch Strategy" });

    await user().click(screen.getByRole("button", { name: "Write the investment proposal" }));

    expect(await screen.findByRole("tab", { name: "Executive summary" })).toBeTruthy();
    expect(sent.at(-1)).toEqual({
      path: `/reports/${SESSION}/proposal`,
      body: { version: 1, reasoning: { specialist: "minimal", chief: "medium" } },
    });
    expect(screen.getByRole("status").textContent).toContain("The investment proposal is written.");
    expect(screen.getByRole("option").textContent).toContain("(investment proposal,");
    expect(screen.getAllByRole("tab")).toHaveLength(CHAPTERS.length);
    for (const name of CHAPTERS) expect(screen.getByRole("tab", { name })).toBeTruthy();
    expect(screen.getByText("Investment proposal")).toBeTruthy();
  });

  test("a failed write says why", async () => {
    fakeReports({ failures: { write: 502 } });
    renderPage();
    await screen.findByRole("heading", { name: "Launch Strategy" });

    await user().click(screen.getByRole("button", { name: "Write the investment proposal" }));

    expect((await screen.findByRole("alert")).textContent).toBe("The backend returned 502: It failed (502).");
  });

  test("the team's report is edited and saved", async () => {
    const { sent } = fakeReports();
    renderPage();
    await user().click(await screen.findByRole("button", { name: "Edit the team's report" }));
    const box = screen.getByLabelText("Financial Planning");

    await user().clear(box);
    await user().type(box, "Charge $199 a month.");
    await user().click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Saved your changes to the team's report.")).toBeTruthy();
    const body = sent.at(-1)?.body as { version: number; sections: { key: string; body: string }[] };
    expect(body.version).toBe(1);
    expect(body.sections.find((section) => section.key === "finance")?.body).toBe("Charge $199 a month.");
    expect(screen.getByText("Edited")).toBeTruthy();
    expect(screen.getByText("Charge $199 a month.")).toBeTruthy();
  });

  test("an edit refused because the report changed elsewhere reloads it", async () => {
    const backend = fakeReports();
    renderPage();
    await user().click(await screen.findByRole("button", { name: "Edit the team's report" }));
    backend.state.report = { ...backend.state.report, version: 5 };

    await user().click(screen.getByRole("button", { name: "Save changes" }));

    expect((await screen.findAllByText(/changed elsewhere/)).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText("Version 5")).toBeTruthy());
  });

  test("a failed save keeps the form open with the reason", async () => {
    fakeReports({ failures: { save: 500 } });
    renderPage();
    await user().click(await screen.findByRole("button", { name: "Edit the team's report" }));

    await user().click(screen.getByRole("button", { name: "Save changes" }));

    expect((await screen.findByRole("alert")).textContent).toBe("The backend returned 500: It failed (500).");
    await user().click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Edit the team's report" })).toBeTruthy();
  });

  test("an outdated report says so, and a reset, once confirmed, rebuilds it", async () => {
    const backend = fakeReports({ proposal: true });
    backend.state.report.outdated = true;
    renderPage();

    expect(await screen.findByText(/A later evaluation in this session produced newer results/)).toBeTruthy();
    await moreActions("Reset to the latest results");
    const confirm = screen.getByRole("dialog", { name: "Reset the report?" });
    await user().click(within(confirm).getByRole("button", { name: "Reset the report" }));

    expect(await screen.findByText(/rebuilt from the session's latest results/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Write the investment proposal" })).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("a failed reset says why", async () => {
    fakeReports({ failures: { reset: 500 } });
    renderPage();
    await moreActions("Reset to the latest results");

    await user().click(screen.getByRole("button", { name: "Reset the report" }));

    expect((await screen.findByRole("alert")).textContent).toContain("500");
  });

  test("the menu of more actions closes on Escape or a click elsewhere", async () => {
    fakeReports();
    renderPage();
    const more = await screen.findByRole("button", { name: "More actions" });

    await user().click(more);
    expect(more.getAttribute("aria-expanded")).toBe("true");
    // A team report has no proposal to rewrite.
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      expect.stringMatching(/^Reset to the latest results/),
    ]);
    await user().keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();

    await user().click(more);
    await user().click(screen.getByRole("heading", { name: "Reports" }));
    expect(screen.queryByRole("menu")).toBeNull();
  });
});

describe("the proposal's chapters", () => {
  test("each shows its part, with charts and its author", async () => {
    fakeReports({ proposal: true });
    renderPage();
    await screen.findByRole("tab", { name: "Executive summary" });

    const executive = screen.getByRole("tabpanel", { name: "Executive summary" });
    expect(within(executive).getByRole("heading", { name: "Executive Summary" })).toBeTruthy();
    expect(within(executive).getByText("Written by the Chief of Staff")).toBeTruthy();
    expect(within(executive).getByText("Go with conditions")).toBeTruthy();
    expect(within(executive).getByText("NPV")).toBeTruthy();
    expect(within(executive).getByText("Calculated from the financial plan")).toBeTruthy();
    expect(within(executive).getByText("What the numbers say")).toBeTruthy();

    const market = await openChapter("Market & marketing");
    expect(within(market).getByText("Written by the Marketing Strategy Agent")).toBeTruthy();
    expect(within(market).getByText("$216M")).toBeTruthy();
    expect(within(market).getByText("15% of TAM")).toBeTruthy();
    expect(within(market).getByText("Retained")).toBeTruthy();

    const technical = await openChapter("Technical & operations");
    expect(within(technical).getAllByText("Phase 1: MVP")).toHaveLength(2);
    expect(within(technical).getByText("Months 1–2")).toBeTruthy();

    const financial = await openChapter("Financial plan");
    expect(within(financial).getByText("· $12k one-off")).toBeTruthy();
    expect(within(financial).getByText("Drivers from the Financial Planning Agent")).toBeTruthy();
    expect(within(financial).getByText(/^Paid back/)).toBeTruthy();
    expect(within(financial).queryByText("Checks on the figures, calculated from them")).toBeNull();

    const risk = await openChapter("Risk & compliance");
    expect(within(risk).getAllByText("R1")).toHaveLength(2); // in the matrix and the list
    expect(within(risk).getByText("Regulatory")).toBeTruthy();
    expect(within(risk).getAllByText(/^Severity: /).length).toBe(SAMPLE_REPORT.proposal?.risk.risks.length);

    const kpis = await openChapter("Success metrics");
    expect(within(kpis).getByText("Monthly recurring revenue")).toBeTruthy();

    const team = await openChapter("The team's report");
    expect(within(team).getByRole("heading", { name: "Launch Strategy" })).toBeTruthy();
  });

  test("the Next link at a chapter's end opens the following one", async () => {
    fakeReports({ proposal: true });
    renderPage();
    const executive = await screen.findByRole("tabpanel", { name: "Executive summary" });

    await user().click(within(executive).getByRole("button", { name: /^Next/ }));

    expect(screen.getByRole("tab", { name: "Market & marketing" }).getAttribute("aria-selected")).toBe("true");
    const last = await openChapter("The team's report");
    expect(within(last).queryByRole("button", { name: /^Next/ })).toBeNull();
  });

  test("fractions of a person add up as written", async () => {
    const backend = fakeReports({ proposal: true });
    // These sum to 2.1500000000000004 in floating point.
    backend.state.report.proposal!.technical.staffing = [1, 0.6, 0.2, 0.05, 0.2, 0.1].map((count, index) => ({
      role: `Role ${index + 1}`,
      count,
      timing: "Months 1-6",
    }));
    renderPage();
    await screen.findByRole("tab", { name: "Technical & operations" });

    const technical = await openChapter("Technical & operations");

    const total = within(technical).getByText("Total").closest("tr")!;
    expect(total.textContent).toBe("Total2.15");
  });

  test("figures that fail a check are flagged", async () => {
    const backend = fakeReports({ proposal: true });
    backend.state.report.checks = ["Year 1's fixed costs ($100 a month) are below the monthly OpEx at launch ($850)."];
    renderPage();
    await screen.findByRole("tab", { name: "Financial plan" });

    const financial = await openChapter("Financial plan");

    expect(within(financial).getByText("Checks on the figures, calculated from them")).toBeTruthy();
    expect(within(financial).getByText(/Year 1's fixed costs/)).toBeTruthy();
  });

  test("a part is edited in a form and saved", async () => {
    const { sent } = fakeReports({ proposal: true });
    renderPage();
    await screen.findByRole("tab", { name: "Executive summary" });
    const executive = screen.getByRole("tabpanel", { name: "Executive summary" });

    await user().click(within(executive).getByRole("button", { name: "Edit" }));
    const overview = within(executive).getByLabelText("Project overview");
    await user().clear(overview);
    await user().type(overview, "A sharper overview.");
    await user().selectOptions(within(executive).getByLabelText("Verdict"), "Not yet");
    await user().click(within(executive).getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Saved your changes to the Executive Summary and Success Metrics part.")).toBeTruthy();
    const body = sent.at(-1)?.body as { proposal: typeof SAMPLE_REPORT.proposal };
    expect(body.proposal?.executive.overview).toBe("A sharper overview.");
    expect(body.proposal?.executive.verdict).toBe("Not yet");
    expect(body.proposal?.executive.kpis).toEqual(SAMPLE_REPORT.proposal?.executive.kpis);
    expect(body.proposal?.market).toEqual(SAMPLE_REPORT.proposal?.market);
    expect(within(screen.getByRole("tabpanel", { name: "Executive summary" })).getByText("A sharper overview.")).toBeTruthy();
  });

  test("tables in a form gain and lose rows, and numbers are numbers", async () => {
    const { sent } = fakeReports({ proposal: true });
    renderPage();
    await screen.findByRole("tab", { name: "Market & marketing" });
    const market = await openChapter("Market & marketing");

    await user().click(within(market).getByRole("button", { name: "Edit" }));
    await user().click(within(market).getByRole("button", { name: "Remove row 3 of Competitors" }));
    const addRows = within(market).getAllByRole("button", { name: "Add a row" });
    await user().click(addRows[1]); // the channels table
    await user().type(within(market).getByLabelText("Channels, row 3: Channel"), "Referrals");
    const budget = within(market).getByLabelText("Channels, row 3: Monthly budget ($)");
    await user().clear(budget);
    await user().type(budget, "150");
    const tam = within(market).getByLabelText("Value ($ a year)", { selector: "#market-tam-value" });
    await user().clear(tam);
    await user().type(tam, "300000000");
    await user().click(within(market).getByRole("button", { name: "Save changes" }));

    await screen.findByText(/Saved your changes to the Market/);
    const body = sent.at(-1)?.body as { proposal: typeof SAMPLE_REPORT.proposal };
    expect(body.proposal?.market.competitors).toHaveLength(2);
    expect(body.proposal?.market.channels[2]).toEqual({ channel: "Referrals", approach: "", monthly_budget_usd: 150 });
    expect(body.proposal?.market.tam.value_usd).toBe(300000000);
  });

  test("every part has a form that saves it as it is", async () => {
    const { sent } = fakeReports({ proposal: true });
    renderPage();
    await screen.findByRole("tab", { name: "Executive summary" });

    for (const [chapter, part] of [
      ["Technical & operations", "technical"],
      ["Financial plan", "financial"],
      ["Risk & compliance", "risk"],
      ["Success metrics", "executive"],
    ] as const) {
      const panel = await openChapter(chapter);
      await user().click(within(panel).getByRole("button", { name: "Edit" }));
      await user().click(within(screen.getByRole("tabpanel", { name: chapter })).getByRole("button", { name: "Save changes" }));
      await waitFor(() => expect(sent.at(-1)?.path).toBe(`/reports/${SESSION}/proposal`));
      const body = sent.at(-1)?.body as { proposal: Record<string, unknown> };
      expect(body.proposal[part]).toEqual(SAMPLE_REPORT.proposal?.[part]);
      await screen.findByText(/Saved your changes/);
    }
  });

  test("an edit the API rejects stays open with the reason", async () => {
    fakeReports({ proposal: true, failures: { saveProposal: 422 } });
    renderPage();
    await screen.findByRole("tab", { name: "Financial plan" });
    const financial = await openChapter("Financial plan");
    await user().click(within(financial).getByRole("button", { name: "Edit" }));

    await user().clear(within(financial).getByLabelText("Discount rate (0.30 = 30%)"));
    await user().click(within(financial).getByRole("button", { name: "Save changes" }));

    expect((await within(financial).findByRole("alert")).textContent).toContain("422");
    await user().click(within(financial).getByRole("button", { name: "Cancel" }));
    expect(within(financial).getByRole("button", { name: "Edit" })).toBeTruthy();
  });

  test("rewriting asks first, then writes again", async () => {
    const { sent } = fakeReports({ proposal: true });
    renderPage();
    await moreActions("Rewrite the proposal");
    await user().click(within(screen.getByRole("dialog", { name: "Rewrite the proposal?" })).getByRole("button", { name: "Keep it" }));
    expect(sent).toEqual([]);

    await moreActions("Rewrite the proposal");
    await user().click(screen.getByRole("button", { name: "Rewrite it" }));

    await screen.findByText(/The investment proposal is written/);
    expect(sent.at(-1)?.path).toBe(`/reports/${SESSION}/proposal`);
  });
});

describe("the PDF pop-up", () => {
  test("shows the PDF with its download, and sends an instruction to the team", async () => {
    const { sent, fetch } = fakeReports({ proposal: true });
    renderPage();
    await user().click(await screen.findByRole("button", { name: "Open PDF" }));

    const dialog = await screen.findByRole("dialog", { name: "Report PDF" });
    const viewer = await within(dialog).findByTitle("The report as a PDF");
    expect(viewer.getAttribute("src")).toBe("blob:report-pdf");
    expect(within(dialog).getByRole("link", { name: "Download PDF" }).getAttribute("download")).toBe(
      "investment-proposal-session-.pdf",
    );

    await user().click(within(dialog).getByRole("button", { name: "Revise" }));
    expect(within(dialog).getByRole("alert").textContent).toBe("Say what to change.");

    expect(within(dialog).getByRole("radio", { name: /^The whole proposal/ })).toHaveProperty("checked", true);
    await user().click(within(dialog).getByRole("radio", { name: /^Market & Marketing Strategy/ }));
    await user().type(within(dialog).getByLabelText("What to change"), "Add a referral channel.");
    await user().click(within(dialog).getByRole("button", { name: "Revise" }));

    expect((await within(dialog).findByRole("alert")).textContent).toBe(
      "Could not revise: Financial Plan & Projections. They keep their text.",
    );
    expect(sent.at(-1)).toEqual({
      path: `/reports/${SESSION}/proposal/revise`,
      body: { version: 1, instruction: "Add a referral channel.", part: "market", reasoning: { specialist: "minimal", chief: "medium" } },
    });
    expect(within(dialog).getByLabelText<HTMLTextAreaElement>("What to change").value).toBe("");
    // The new version's PDF is fetched.
    await waitFor(() => expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/pdf")).length).toBe(2));

    await user().click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("Revise with the team opens it with the prompt ready", async () => {
    fakeReports({ proposal: true });
    renderPage();

    await user().click(await screen.findByRole("button", { name: "Revise with the team" }));

    const dialog = await screen.findByRole("dialog", { name: "Report PDF" });
    await waitFor(() => expect(document.activeElement).toBe(within(dialog).getByLabelText("What to change")));
  });

  test("a revision of the whole proposal, and its failures", async () => {
    const backend = fakeReports({ proposal: true });
    renderPage();
    await user().click(await screen.findByRole("button", { name: "Open PDF" }));
    const dialog = await screen.findByRole("dialog", { name: "Report PDF" });

    backend.state.failures.revise = 502;
    await user().type(within(dialog).getByLabelText("What to change"), "Plan for a slower ramp.");
    await user().click(within(dialog).getByRole("button", { name: "Revise" }));
    expect((await within(dialog).findByRole("alert")).textContent).toBe("The backend returned 502: It failed (502).");
    expect((backend.sent.at(-1)?.body as { part: unknown }).part).toBeNull();

    delete backend.state.failures.revise;
    backend.state.report = { ...backend.state.report, version: 7 };
    await user().click(within(dialog).getByRole("button", { name: "Revise" }));
    expect((await within(dialog).findByRole("alert")).textContent).toContain("changed elsewhere");
    await waitFor(() => expect(screen.getByText("Version 7")).toBeTruthy());

    await user().click(within(dialog).getByRole("button", { name: "Revise" }));
    expect((await within(dialog).findByRole("alert")).textContent).toContain("Could not revise");
  });

  test("for a team report it explains, and a PDF that fails says so", async () => {
    fakeReports({ failures: { pdf: 500 } });
    renderPage();
    await user().click(await screen.findByRole("button", { name: "Open PDF" }));

    const dialog = await screen.findByRole("dialog", { name: "Report PDF" });
    expect(within(dialog).getByText(/This is the team's report\. Write the investment proposal/)).toBeTruthy();
    expect((await within(dialog).findByRole("alert")).textContent).toContain("The PDF could not be made.");
  });
});

describe("choosing a report", () => {
  test("there may be none yet", async () => {
    fakeReports({ extra: { "GET /reports": { body: [] } } });
    renderPage();

    expect(await screen.findByRole("heading", { name: "No reports yet" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Evaluate an idea" }).getAttribute("href")).toBe("/");
  });

  test("a report that cannot be loaded says why", async () => {
    fakeReports({ failures: { list: 503 } });
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toBe("The backend returned 503: It failed (503).");
  });

  test("the session in the address is opened first, and another can be chosen", async () => {
    const other = { ...SAMPLE_REPORT, session_id: "other-session", title: "Another idea", proposal: null, investment: null, version: 1 };
    fakeReports({
      extra: {
        "GET /reports": {
          body: [
            { ...other, has_proposal: false },
            { ...SAMPLE_REPORT, version: 1, has_proposal: false },
          ],
        },
        "GET /reports/other-session": { body: other },
      },
    });
    window.history.pushState({}, "", `/reports?session=${SESSION}`);
    renderPage();

    await screen.findByRole("heading", { name: "Launch Strategy" });
    expect(screen.getByLabelText<HTMLSelectElement>("Report").value).toBe(SESSION);
    await user().selectOptions(screen.getByLabelText("Report"), "other-session");
    await waitFor(() => expect(screen.getByText("other-se")).toBeTruthy());
    window.history.pushState({}, "", "/reports");
  });

  test("otherwise the Evaluate page's session is opened", async () => {
    window.sessionStorage.setItem(
      "cofounder-session",
      JSON.stringify({ runs: [{ prompt: "An idea", result: { session_id: SESSION } }], followUp: "" }),
    );
    fakeReports({
      extra: {
        "GET /reports": {
          body: [
            { session_id: "newer", title: "Newer", version: 1, has_proposal: false, edited: false, outdated: false, updated_at: SAMPLE_REPORT.updated_at },
            { session_id: SESSION, title: "Mine", version: 1, has_proposal: false, edited: false, outdated: false, updated_at: SAMPLE_REPORT.updated_at },
          ],
        },
      },
    });
    renderPage();

    await screen.findByRole("heading", { name: "Launch Strategy" });
    expect(screen.getByLabelText<HTMLSelectElement>("Report").value).toBe(SESSION);
  });
});

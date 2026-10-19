import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { EvaluateApp } from "@/components/evaluate/evaluate-app";
import { BackendProvider } from "@/lib/backend";
import { DEEP, fakeBackend, HEALTH, liveStream, RESULT, sse, STEPS } from "@/test/backend";

function renderPage() {
  return render(
    <BackendProvider>
      <EvaluateApp />
    </BackendProvider>,
  );
}

const deepSwitch = () => screen.getByRole<HTMLInputElement>("checkbox", { name: /Deep research for each specialist/ });

async function writeBrief(user: ReturnType<typeof userEvent.setup>, researchFirst: boolean) {
  await user.type(screen.getByLabelText("The brief"), "An idea");
  if (!researchFirst) await user.click(screen.getByRole("checkbox", { name: /Research it and check the brief first/ }));
}

describe("deep research", () => {
  test("is off until switched on, then goes with the request", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();
    await writeBrief(user, false);
    expect(deepSwitch().checked).toBe(false);
    expect(screen.getByText(/about 150-450 of your Tavily credits/)).toBeTruthy();

    await user.click(deepSwitch());
    await user.click(screen.getByRole("button", { name: /^Evaluate\s*⌘↵$/ }));

    await screen.findByRole("heading", { name: "Go with conditions" });
    expect(sent[0].body).toMatchObject({ prompt: "An idea", deep_research: true });
  });

  test("goes with the request after the brief is checked too", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();
    await writeBrief(user, true);
    await user.click(deepSwitch());
    await user.click(screen.getByRole("button", { name: /^Check the brief/ }));

    await user.click(await screen.findByRole("button", { name: /^Run the team/ }));

    await screen.findByRole("heading", { name: "Go with conditions" });
    expect(sent[0].path).toBe("/brief/prepare");
    expect(sent[1].body).toMatchObject({ deep_research: true });
  });

  test("cannot be switched on without a search key on the server", async () => {
    fakeBackend({ "GET /health": { body: { ...HEALTH, research: { available: false, provider: "Tavily" } } } });
    renderPage();

    expect(await screen.findByText("Needs a TAVILY_API_KEY on the server.")).toBeTruthy();
    expect(deepSwitch().disabled).toBe(true);
  });

  test("while it runs, the research stage and the log say so", async () => {
    const live = liveStream();
    fakeBackend({ "POST /evaluate/stream": () => ({ stream: live.stream }) });
    const user = userEvent.setup();
    renderPage();
    await writeBrief(user, false);
    await user.click(deepSwitch());
    await user.click(screen.getByRole("button", { name: /^Evaluate\s*⌘↵$/ }));
    const working = await screen.findByRole("region", { name: "The team is working" });

    await act(async () => live.send(sse([...STEPS.slice(0, 2), { type: "start", node: "research", at: 9.7 }], null)));
    expect(within(working).getByLabelText("Research: Working")).toBeTruthy();
    expect(within(working).getByText("Tavily is researching each specialist's area and the main competitors.")).toBeTruthy();

    await act(async () =>
      live.send(
        sse(
          [
            {
              type: "done",
              node: "research",
              at: 80.2,
              summary: "Researched 2 areas and 1 competitor (3 sources, 102 credits).",
              credits: 102,
            },
            { type: "start", node: "finance", at: 80.3 },
          ],
          null,
        ),
      ),
    );
    const log = within(working).getByRole("region", { name: "What the team has done" });
    expect(within(log).getByText("Tavily")).toBeTruthy();
    expect(within(log).getByText("Researched 2 areas and 1 competitor (3 sources, 102 credits).")).toBeTruthy();
    expect(within(working).getByLabelText("Research: Done")).toBeTruthy();
  });

  test("the result shows each area's research, the competitors and every source", async () => {
    fakeBackend({ "POST /evaluate/stream": () => ({ stream: sse(STEPS, { result: { ...RESULT, research: DEEP } }) }) });
    const user = userEvent.setup();
    renderPage();
    await writeBrief(user, false);
    await user.click(screen.getByRole("button", { name: /^Evaluate\s*⌘↵$/ }));
    await screen.findByRole("heading", { name: "Go with conditions" });

    const summary = screen.getByRole("complementary", { name: "The team's reviews" });
    expect(within(summary).getByText("Deep research on 2 areas and 1 competitor, 102 Tavily credits")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Research" }));
    const tab = screen.getByRole("tabpanel", { name: "Research" });

    const areas = within(tab).getByRole("region", { name: "Deep research" });
    expect(within(areas).getByText("Financial Planning")).toBeTruthy();
    expect(within(areas).getByText("Marketing Strategy")).toBeTruthy();
    expect(within(areas).getByText("$50").tagName).toBe("STRONG");
    const competitors = within(tab).getByRole("region", { name: "Competitors" });
    expect(within(competitors).getByText("Klara")).toBeTruthy();
    expect(within(competitors).getByText("$15 per user a month [2]")).toBeTruthy();
    expect(within(competitors).queryByText("Funding")).toBeNull(); // empty fields are left out
    expect(within(tab).getByRole("alert").textContent).toBe(
      "Tavily could not research Risk & Compliance; the team worked without it there.",
    );
    const sources = within(tab).getByRole("region", { name: "Sources" });
    expect(within(sources).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(
      DEEP.sources.map((source) => source.url),
    );
  });
});

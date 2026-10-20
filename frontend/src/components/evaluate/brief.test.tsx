import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { EvaluateApp } from "@/components/evaluate/evaluate-app";
import type { PreparedBrief } from "@/lib/api";
import { BackendProvider } from "@/lib/backend";
import { fakeBackend, HEALTH, PREPARED } from "@/test/backend";

function renderPage() {
  return render(
    <BackendProvider>
      <EvaluateApp />
    </BackendProvider>,
  );
}

const checkButton = () => screen.getByRole("button", { name: /^Check the brief/ });
const review = () => screen.findByRole("region", { name: "Before the team starts" });

describe("preparing the brief", () => {
  test("the brief is researched and checked, then run with the answers and the facts kept", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("The brief"), "An assistant for clinics.");
    await user.type(screen.getByLabelText("Constraints"), "Under $15k");

    await user.click(checkButton());

    const before = await review();
    expect(sent[0]).toEqual({
      path: "/brief/prepare",
      body: {
        prompt: "An assistant for clinics.",
        context: { constraints: "Under $15k" },
        template: null,
        reasoning: { specialist: "minimal", chief: "medium" },
        research_provider: "azure",
      },
    });
    expect(screen.queryByRole("form", { name: "New request" })).toBeNull(); // hidden, not gone
    expect(within(before).getByText("An assistant for clinics.")).toBeTruthy();

    const budget = within(before).getByRole("group", { name: "What budget do you have to first launch?" });
    expect(within(budget).getByText("It decides whether a paid pilot is affordable.")).toBeTruthy();
    await user.click(within(budget).getByRole("button", { name: "Under $15k" }));
    expect(within(budget).getByRole("button", { name: "Under $15k" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(budget).getByRole<HTMLInputElement>("textbox").value).toBe("Under $15k");

    expect(within(before).getByText(/3 facts from 2 sources/)).toBeTruthy();
    await user.click(within(before).getByRole("button", { name: "Leave out: Most small practices still book follow-ups by phone." }));
    const sources = within(before).getByRole("complementary", { name: "Sources" });
    expect(within(sources).getByRole("link", { name: "Physician practice benchmark survey" }).getAttribute("href")).toBe(
      "https://www.ama-assn.org/survey",
    );
    expect(within(sources).getByText("ama-assn.org")).toBeTruthy();
    expect(within(sources).getByText("clinic scheduling software prices")).toBeTruthy();
    expect(within(before).getAllByRole("link", { name: "Source 1" })[0].getAttribute("href")).toMatch(/-source-1$/);

    await user.click(within(before).getByRole("button", { name: /^Run the team/ }));

    await screen.findByRole("heading", { name: "Go with conditions" });
    expect(sent[1].path).toBe("/evaluate/stream");
    expect((sent[1].body as { context: unknown }).context).toEqual({
      constraints: "Under $15k",
      answers: [{ question: "What budget do you have to first launch?", answer: "Under $15k" }],
      research: {
        findings: PREPARED.research!.findings.slice(0, 2),
        sources: PREPARED.research!.sources,
      },
    });
    const summary = screen.getByRole("complementary", { name: "The team's reviews" });
    expect(within(summary).getByText("2 facts from the web for the brief")).toBeTruthy();
    expect(within(summary).getByText("1 answer from you")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Research" }));
    const tab = screen.getByRole("tabpanel", { name: "Research" });
    expect(within(tab).getByText("Under $15k")).toBeTruthy();
    expect(within(tab).getByText(/147,000 office-based primary care physicians/)).toBeTruthy();
    expect(within(tab).queryByText(/book follow-ups by phone/)).toBeNull();
  });

  test("a decision template is filled in, prepared, and kept for editing", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();
    const idea = await screen.findByRole("button", { name: "Evaluate a new idea" });

    await user.click(idea);
    expect(idea.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Is it worth building, and how should it launch?")).toBeTruthy();
    await user.click(checkButton());
    expect(screen.getByRole("alert").textContent).toBe("Fill in the idea first.");
    expect(document.activeElement).toBe(screen.getByLabelText("The idea"));
    expect(screen.getByLabelText("The idea").getAttribute("aria-invalid")).toBe("true");

    await user.type(screen.getByLabelText("The idea"), "An app that books follow-ups.");
    await user.type(screen.getByLabelText("Who it is for"), " small clinics ");
    const brief =
      "Evaluate this startup idea: An app that books follow-ups. It is for small clinics. Is it worth building, and how should we launch it?";
    expect(screen.getByText(brief)).toBeTruthy();
    await user.click(checkButton());

    await review();
    expect(sent[0].body).toMatchObject({ prompt: brief, template: "evaluate_idea" });
    await user.click(screen.getByRole("button", { name: "Edit the brief" }));
    expect(screen.getByLabelText<HTMLTextAreaElement>("The idea").value).toBe("An app that books follow-ups.");
    await user.click(screen.getByRole("button", { name: "Your own brief" }));
    expect(screen.getByLabelText("The brief")).toBeTruthy();
  });

  test("an example clears a template, and a missing field after it is named", async () => {
    fakeBackend();
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Set the price" }));
    await user.type(screen.getByLabelText("The product"), "A scheduling assistant");
    await user.click(checkButton());
    expect(screen.getByRole("alert").textContent).toBe("Fill in who pays first.");

    await user.click(screen.getByRole("button", { name: /Follow-up scheduling for small clinics/ }));

    expect(screen.getByRole("button", { name: "Your own brief" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByLabelText<HTMLTextAreaElement>("The brief").value).toBe(
      "Evaluate an assistant that schedules patient follow-ups.",
    );
  });

  test("while the Chief of Staff prepares it, the page says what is happening", async () => {
    let answer!: (prepared: { body: PreparedBrief }) => void;
    fakeBackend({ "POST /brief/prepare": () => new Promise((resolve) => (answer = resolve)) });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("The brief"), "An idea");

    await user.click(checkButton());

    expect(await screen.findByText("The Chief of Staff is preparing the brief.")).toBeTruthy();
    expect(screen.getByText("Azure OpenAI searches the web")).toBeTruthy();
    answer({ body: PREPARED });
    expect(await review()).toBeTruthy();
  });

  test("without web research, the brief is still checked, and says why there is none", async () => {
    const { sent } = fakeBackend({
      "GET /health": { body: { ...HEALTH, research: { providers: { azure: false, tavily: false }, default: null } } },
      "POST /brief/prepare": {
        body: { queries: [], research: null, research_note: "Web research is off: add a TAVILY_API_KEY.", questions: [] },
      },
    });
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText(/Web research is off: the server has neither Azure OpenAI nor a TAVILY_API_KEY/)).toBeTruthy();
    await user.type(screen.getByLabelText("The brief"), "An idea");

    await user.click(checkButton());

    const before = await review();
    expect(within(before).getByText("Nothing: the brief gives the team what it needs.")).toBeTruthy();
    expect(within(before).getByRole("status").textContent).toBe("Web research is off: add a TAVILY_API_KEY.");
    expect(within(before).queryByRole("complementary", { name: "Sources" })).toBeNull();
    // The keyboard runs the team from here too.
    fireEvent.keyDown(within(before).getByRole("button", { name: /^Run the team/ }), { key: "Enter", metaKey: true });
    await screen.findByRole("heading", { name: "Go with conditions" });
    expect(sent[1].body).toMatchObject({ prompt: "An idea", context: null });
    expect(screen.queryByRole("tab", { name: "Research" })).toBeNull();
  });

  test("a fact left out can be put back, and an answer can be written in", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("The brief"), "An idea");
    await user.click(checkButton());
    const before = await review();
    const fact = "Most small practices still book follow-ups by phone.";

    await user.click(within(before).getByRole("button", { name: `Leave out: ${fact}` }));
    await user.click(within(before).getByRole("button", { name: `Put back: ${fact}` }));
    await user.type(within(before).getByLabelText("Your answer: Who is on the team?"), "Two founders ");
    await user.click(within(before).getByRole("button", { name: /^Run the team/ }));
    await screen.findByRole("heading", { name: "Go with conditions" });
    const { context } = sent[1].body as { context: { research: unknown; answers: unknown } };
    expect(context.research).toEqual(PREPARED.research);
    expect(context.answers).toEqual([{ question: "Who is on the team?", answer: "Two founders" }]);
  });

  test("a failed preparation says why, and the brief stays", async () => {
    fakeBackend({ "POST /brief/prepare": { status: 502, body: { detail: "The LLM call failed: timeout" } } });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("The brief"), "An idea");

    await user.click(checkButton());

    expect((await screen.findByRole("alert")).textContent).toBe("The backend returned 502: The LLM call failed: timeout");
    expect(screen.getByLabelText<HTMLTextAreaElement>("The brief").value).toBe("An idea");
  });
});

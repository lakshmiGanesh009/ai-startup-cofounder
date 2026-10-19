import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import Home from "@/app/page";
import { EvaluateApp } from "@/components/evaluate/evaluate-app";
import { BackendProvider } from "@/lib/backend";
import { fakeBackend, RESULT } from "@/test/backend";

function renderPage() {
  return render(
    <BackendProvider>
      <EvaluateApp />
    </BackendProvider>,
  );
}

async function pickScenario(user: ReturnType<typeof userEvent.setup>) {
  const select = screen.getByLabelText("Start from a scenario");
  await screen.findByRole("option", { name: "Healthcare scheduling" });
  await user.selectOptions(select, "healthcare_scheduling");
}

describe("the Evaluate page", () => {
  test("a scenario fills the form, and the request carries the sliders' efforts", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();

    await pickScenario(user);
    expect(screen.getByLabelText<HTMLTextAreaElement>("Startup idea or request").value).toBe(
      "Evaluate an assistant that schedules patient follow-ups.",
    );
    expect(screen.getByLabelText<HTMLInputElement>("Target market").value).toBe("Small clinics");
    await user.click(screen.getByRole("button", { name: "Evaluate" }));

    expect(await screen.findByRole("heading", { name: "Go with conditions" })).toBeTruthy();
    expect(sent[0]).toEqual({
      path: "/evaluate",
      body: {
        prompt: "Evaluate an assistant that schedules patient follow-ups.",
        context: { target_market: "Small clinics", constraints: "Under $15k" },
        session_id: null,
        reasoning: { specialist: "minimal", chief: "medium" },
      },
    });
    expect(screen.getByText("Session session-")).toBeTruthy();
  });

  test("a follow-up reuses the session and keeps the earlier request", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();
    await pickScenario(user);
    await user.click(screen.getByRole("button", { name: "Evaluate" }));
    await screen.findByRole("heading", { name: "Go with conditions" });

    const followUp = screen.getByLabelText<HTMLInputElement>("Follow-up in this session");
    expect(followUp.value).toBe("Refine the pricing strategy after financial review.");
    await user.click(screen.getByRole("button", { name: "Send follow-up" }));

    await screen.findByRole("heading", { name: /^Request 2:/ });
    expect(sent[1].body).toMatchObject({ session_id: RESULT.session_id, context: null });
    expect(screen.getByText(/^Request 1:/)).toBeTruthy();
    expect(followUp.value).toBe("");
  });

  test("the tabs show the plan, reports, reviews, conflicts and metrics", async () => {
    fakeBackend();
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("Startup idea or request"), "An idea");
    await user.click(screen.getByRole("button", { name: "Evaluate" }));
    await screen.findByRole("heading", { name: "Go with conditions" });

    await user.click(screen.getByRole("tab", { name: "Reports" }));
    const reports = screen.getByRole("tabpanel", { name: "Reports" });
    expect(within(reports).getByText("Financial Planning")).toBeTruthy();
    expect(reports.querySelector("mark.assumption")?.textContent).toBe("(assumption)");

    await user.click(screen.getByRole("tab", { name: "Reviews" }));
    const reviews = screen.getByRole("tabpanel", { name: "Reviews" });
    expect(within(reviews).getByText("Sent back")).toBeTruthy();
    expect(within(reviews).getByText("3/5")).toBeTruthy();

    await user.click(screen.getByRole("tab", { name: "Conflicts" }));
    expect(screen.getByText("Financial Planning vs Marketing Strategy")).toBeTruthy();
    expect(screen.getByText("Revised: Marketing Strategy")).toBeTruthy();

    await user.click(screen.getByRole("tab", { name: "Metrics" }));
    expect(within(screen.getByRole("tabpanel", { name: "Metrics" })).getByText("3,400")).toBeTruthy();
    expect(screen.getByText("2 LLM calls")).toBeTruthy();
  });

  test("an empty request is not sent", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Evaluate" }));

    expect(screen.getByRole("alert").textContent).toContain("Describe the idea");
    expect(sent).toEqual([]);
  });

  test("a failed request shows why, and the form stays", async () => {
    fakeBackend({ "POST /evaluate": { status: 502, body: { detail: "The LLM call failed: timeout" } } });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("Startup idea or request"), "An idea");

    await user.click(screen.getByRole("button", { name: "Evaluate" }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "The backend returned 502: The LLM call failed: timeout",
    );
    expect(screen.getByRole("button", { name: "Evaluate" })).toBeTruthy();
  });

  test("the progress panel shows while the team works", async () => {
    let finish: (answer: { body: unknown }) => void = () => {};
    fakeBackend({ "POST /evaluate": () => new Promise((resolve) => (finish = resolve)) });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("Startup idea or request"), "An idea");

    await user.click(screen.getByRole("button", { name: "Evaluate" }));

    expect(await screen.findByText("The founding team is working.")).toBeTruthy();
    expect(screen.getByLabelText("Elapsed time").textContent).toBe("0:00");
    finish({ body: RESULT });
    expect(await screen.findByRole("heading", { name: "Go with conditions" })).toBeTruthy();
  });

  test("the session survives a reload, until a new one is started", async () => {
    window.sessionStorage.setItem(
      "cofounder-session",
      JSON.stringify({ runs: [{ prompt: "An idea", result: RESULT }], followUp: "Next question" }),
    );
    fakeBackend();
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("heading", { name: "Request 1: An idea" })).toBeTruthy();
    expect(screen.getByLabelText<HTMLInputElement>("Follow-up in this session").value).toBe("Next question");

    await user.click(screen.getByRole("button", { name: "Start a new session" }));

    expect(screen.getByRole("form", { name: "New request" })).toBeTruthy();
    expect(JSON.parse(window.sessionStorage.getItem("cofounder-session") ?? "{}").runs).toEqual([]);
  });

  test("a damaged saved session is ignored", async () => {
    window.sessionStorage.setItem("cofounder-session", "{not json");
    fakeBackend({ "GET /scenarios": { status: 500, body: null } });

    renderPage();

    expect(await screen.findByRole("form", { name: "New request" })).toBeTruthy();
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["(none)"]);
  });
});

test("the home page is the Evaluate page", async () => {
  fakeBackend();

  render(
    <BackendProvider>
      <Home />
    </BackendProvider>,
  );

  expect(await screen.findByRole("heading", { name: "Evaluate an idea" })).toBeTruthy();
});

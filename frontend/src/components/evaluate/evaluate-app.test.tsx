import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import Home from "@/app/page";
import { EvaluateApp } from "@/components/evaluate/evaluate-app";
import { BackendProvider } from "@/lib/backend";
import { fakeBackend, liveStream, RESULT, sse, STEPS } from "@/test/backend";

function renderPage() {
  return render(
    <BackendProvider>
      <EvaluateApp />
    </BackendProvider>,
  );
}

type User = ReturnType<typeof userEvent.setup>;

const researchFirst = () => screen.getByRole("checkbox", { name: /Research it and check the brief first/ });

// Runs the team straight away, without researching and checking the brief.
async function evaluateNow(user: User) {
  if ((researchFirst() as HTMLInputElement).checked) await user.click(researchFirst());
  await user.click(screen.getByRole("button", { name: /^Evaluate\s*⌘↵$/ }));
}

async function startFromExample(user: User) {
  await user.click(await screen.findByRole("button", { name: /Follow-up scheduling for small clinics/ }));
}

describe("the Evaluate page", () => {
  test("an example fills the brief, and the request carries the sliders' efforts", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();

    await startFromExample(user);
    expect(screen.getByLabelText<HTMLTextAreaElement>("The brief").value).toBe(
      "Evaluate an assistant that schedules patient follow-ups.",
    );
    expect(screen.getByLabelText<HTMLInputElement>("Target market").value).toBe("Small clinics");
    expect(screen.getByRole("button", { name: /Follow-up scheduling/ }).getAttribute("aria-pressed")).toBe("true");
    await evaluateNow(user);

    expect(await screen.findByRole("heading", { name: "Go with conditions" })).toBeTruthy();
    expect(sent[0]).toEqual({
      path: "/evaluate/stream",
      body: {
        prompt: "Evaluate an assistant that schedules patient follow-ups.",
        context: { target_market: "Small clinics", constraints: "Under $15k" },
        session_id: null,
        reasoning: { specialist: "minimal", chief: "medium" },
      },
    });
    expect(screen.getByRole("heading", { name: "Decide whether to launch a paid pilot." })).toBeTruthy();
    expect(screen.getByText(/^Session/).textContent).toContain("session-");
  });

  test("the brief can be sent from the keyboard", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();

    await user.click(researchFirst());
    await user.type(screen.getByLabelText("The brief"), "An idea");
    fireEvent.keyDown(screen.getByLabelText("The brief"), { key: "Enter", ctrlKey: true });

    await screen.findByRole("heading", { name: "Go with conditions" });
    expect(sent[0].body).toMatchObject({ prompt: "An idea", context: null });
  });

  test("while the team works, the page shows each step as it arrives", async () => {
    const live = liveStream();
    fakeBackend({ "POST /evaluate/stream": () => ({ stream: live.stream }) });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("The brief"), "An idea");
    await evaluateNow(user);

    const working = await screen.findByRole("region", { name: "The team is working" });
    expect(within(working).getByText("The Chief of Staff is reading the brief and planning the work.")).toBeTruthy();
    expect(within(working).getByLabelText("Plan: Working")).toBeTruthy();
    expect(within(working).getByLabelText("Elapsed time").textContent).toBe("0:00");

    await act(async () => live.send(sse(STEPS.slice(0, 5), null)));
    const log = within(working).getByRole("region", { name: "What the team has done" });
    expect(within(log).getByText("Planned the work and assigned Financial Planning and Marketing Strategy.")).toBeTruthy();
    expect(within(log).getByText("Decide whether to launch a paid pilot.")).toBeTruthy();
    expect(within(working).getByLabelText("Plan: Done")).toBeTruthy();
    expect(within(working).getByLabelText("Reports: Working")).toBeTruthy();
    expect(within(working).getByText("Financial Planning is writing its report.")).toBeTruthy();
    const team = within(working).getByRole("region", { name: "The team at work" });
    expect(within(team).getAllByText("Not needed")).toHaveLength(2);

    await act(async () => live.send(sse(STEPS.slice(5, 10), null)));
    expect(within(log).getByText("Reviewed 2 reports: approved 1, sent back Financial Planning.")).toBeTruthy();
    expect(within(team).getByText("Revised")).toBeTruthy();

    await act(async () => {
      live.send(sse(STEPS.slice(10), { result: RESULT }));
      live.close();
    });
    expect(await screen.findByRole("heading", { name: "Go with conditions" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "The team is working" })).toBeNull();
    // The time the team took is kept with the result.
    expect(screen.getByText("1:57")).toBeTruthy();
  });

  test("a lost connection is reported", async () => {
    const live = liveStream();
    fakeBackend({ "POST /evaluate/stream": () => ({ stream: live.stream }) });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("The brief"), "An idea");
    await evaluateNow(user);
    await screen.findByRole("region", { name: "The team is working" });

    await act(async () => live.fail());

    expect((await screen.findByRole("alert")).textContent).toContain("connection to the backend was lost");
  });

  test("a follow-up reuses the session, and the requests can be switched between", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();
    await startFromExample(user);
    await evaluateNow(user);
    await screen.findByRole("heading", { name: "Go with conditions" });

    const followUp = screen.getByLabelText<HTMLInputElement>("Follow up in this session");
    expect(followUp.value).toBe("Refine the pricing strategy after financial review.");
    await user.click(screen.getByRole("button", { name: "Send follow-up" }));

    await screen.findByRole("article", { name: "Request 2" });
    expect(sent[1].body).toMatchObject({ session_id: RESULT.session_id, context: null });
    expect(screen.getByLabelText<HTMLInputElement>("Follow up in this session").value).toBe("");
    const requests = screen.getByRole("navigation", { name: "Requests in this session" });
    await user.click(within(requests).getByRole("button", { name: /Request 1/ }));
    expect(screen.getByRole("article", { name: "Request 1" })).toBeTruthy();
    expect(within(requests).getByRole("button", { name: /Request 1/ }).getAttribute("aria-current")).toBe("true");
  });

  test("the result shows the reviews, and tabs for the team's work", async () => {
    fakeBackend();
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("The brief"), "An idea");
    await evaluateNow(user);
    await screen.findByRole("heading", { name: "Go with conditions" });

    const reviews = screen.getByRole("complementary", { name: "The team's reviews" });
    expect(within(reviews).getByText("Approved after revision")).toBeTruthy();
    expect(within(reviews).getByText("1 settled by the Chief of Staff.")).toBeTruthy();
    expect(within(reviews).getByText("4,600")).toBeTruthy();
    expect(within(reviews).getByRole("link", { name: "Open the report" }).getAttribute("href")).toBe(
      `/reports?session=${RESULT.session_id}`,
    );

    const reports = screen.getByRole("tabpanel", { name: "Specialist reports" });
    expect(reports.querySelector("mark.assumption")?.textContent).toBe("(assumption)");
    await user.click(screen.getByRole("tab", { name: "Plan" }));
    expect(within(screen.getByRole("tabpanel", { name: "Plan" })).getByText("Price the pilot.")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Reviews" }));
    expect(within(screen.getByRole("region", { name: "Round 1" })).getByText("Sent back")).toBeTruthy();
    // The second round shows only the report it reviewed again.
    const second = screen.getByRole("region", { name: "Round 2" });
    expect(within(second).getByText("Financial Planning")).toBeTruthy();
    expect(within(second).queryByText("Marketing Strategy")).toBeNull();
    await user.click(screen.getByRole("tab", { name: "Conflicts" }));
    expect(screen.getByText("Charge $149 a month.")).toBeTruthy();
    expect(screen.getByText("Marketing Strategy revised its report to match.")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Run" }));
    expect(within(screen.getByRole("tabpanel", { name: "Run" })).getByText("3,400")).toBeTruthy();
  });

  test("a report still short after its revision reads as not approved, not sent back", async () => {
    const short = structuredClone(RESULT);
    short.review_history[1].finance = { approved: false, score: 3, feedback: "Still no arithmetic." };
    fakeBackend({ "POST /evaluate/stream": () => ({ stream: sse(STEPS, { result: short }) }) });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("The brief"), "An idea");
    await evaluateNow(user);
    await screen.findByRole("heading", { name: "Go with conditions" });

    const reviews = screen.getByRole("complementary", { name: "The team's reviews" });
    expect(within(reviews).getByText("Not approved after revision")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Reviews" }));
    expect(within(screen.getByRole("region", { name: "Round 2" })).getByText("Not approved")).toBeTruthy();
  });

  test("an empty brief is not sent", async () => {
    const { sent } = fakeBackend();
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /^Check the brief/ }));

    expect(screen.getByRole("alert").textContent).toContain("Describe the idea");
    expect(screen.getByLabelText("The brief").getAttribute("aria-invalid")).toBe("true");
    expect(sent).toEqual([]);
  });

  test("a failure partway through says why, and the brief stays", async () => {
    fakeBackend({
      "POST /evaluate/stream": () => ({
        stream: sse(STEPS.slice(0, 2), { error: { status: 502, detail: "The LLM call failed: timeout" } }),
      }),
    });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("The brief"), "An idea");

    await evaluateNow(user);

    expect((await screen.findByRole("alert")).textContent).toBe("The backend returned 502: The LLM call failed: timeout");
    expect(screen.getByLabelText<HTMLTextAreaElement>("The brief").value).toBe("An idea");
  });

  test("the session survives a reload, until a new one is started", async () => {
    window.sessionStorage.setItem(
      "cofounder-session",
      JSON.stringify({ runs: [{ prompt: "An idea", result: RESULT, seconds: 97 }], followUp: "Next question" }),
    );
    fakeBackend();
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("article", { name: "Request 1" })).toBeTruthy();
    expect(screen.getByText("1:37")).toBeTruthy();
    expect(screen.getByLabelText<HTMLInputElement>("Follow up in this session").value).toBe("Next question");

    await user.click(screen.getByRole("button", { name: "Start a new session" }));

    expect(screen.getByRole("form", { name: "New request" })).toBeTruthy();
    expect(JSON.parse(window.sessionStorage.getItem("cofounder-session") ?? "{}").runs).toEqual([]);
  });

  test("a damaged saved session is ignored, and the page works without examples or templates", async () => {
    window.sessionStorage.setItem("cofounder-session", "{not json");
    fakeBackend({ "GET /scenarios": { status: 500, body: null }, "GET /templates": { status: 500, body: null } });

    renderPage();

    expect(await screen.findByRole("form", { name: "New request" })).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("Or start from an example")).toBeNull());
    expect(screen.queryByText("What do you need decided?")).toBeNull();
    expect(screen.getByLabelText("The brief")).toBeTruthy();
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

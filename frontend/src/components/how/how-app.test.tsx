import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import HowItWorksPage from "@/app/how-it-works/page";
import { BackendProvider } from "@/lib/backend";
import { fakeBackend, MONITORING, PIPELINE } from "@/test/backend";

const mermaid = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(async (id: string, text: string) => ({ svg: `<svg data-id="${id}"><text>${text.split("\n")[0]}</text></svg>` })),
}));
vi.mock("mermaid", () => ({ default: mermaid }));

function renderPage() {
  return render(
    <BackendProvider>
      <HowItWorksPage />
    </BackendProvider>,
  );
}

afterEach(() => {
  mermaid.render.mockClear();
  vi.unstubAllGlobals();
});

describe("the How it works page", () => {
  test("shows the pipeline at a glance, each step linking to its explanation", async () => {
    fakeBackend();
    renderPage();

    const map = await screen.findByRole("figure", { name: "The pipeline, step by step" });
    const steps = within(map).getAllByRole("link");
    expect(steps).toHaveLength(9);
    expect(steps[2].getAttribute("href")).toBe("#decisions");
    expect(steps[2].textContent).toBe("03PlanChief of Staffobjective · tasks");
    expect(within(map).getAllByText("optional")).toHaveLength(2);
    expect(within(map).getAllByTitle("Your call")).toHaveLength(3);
    expect(screen.getByRole("heading", { name: "From a brief to a decision, in 9 steps" })).toBeTruthy();
  });

  test("explains the agents, the decisions and the state from the backend's own settings", async () => {
    fakeBackend();
    renderPage();
    await screen.findByRole("heading", { name: "One orchestrator, four specialists" });

    const team = screen.getByRole("region", { name: "One orchestrator, four specialists" });
    expect(within(team).getByText("Reviews each report against a rubric: 4 of 5 to pass.")).toBeTruthy();
    expect(within(team).getByText("Covers costs, pricing, runway and break-even.")).toBeTruthy();
    expect(within(team).getAllByText("competitor profiles")).toHaveLength(2);
    expect(within(team).getAllByText("a report, ≤ 250 words")).toHaveLength(4);
    expect(within(team).getByText("medium reasoning")).toBeTruthy();

    const decisions = screen.getByRole("region", { name: "How the Chief of Staff decides" });
    expect(within(decisions).getByText(/4 or more passes; below, the report goes back with feedback, once\./)).toBeTruthy();
    expect(decisions.textContent).toContain("4 or more → approved");
    expect(decisions.textContent).toContain("below 4 → revise with feedback");

    const state = screen.getByRole("table", { name: "Which step reads and writes each part of the state" });
    const reports = within(state).getByRole("rowheader", { name: /^Reports/ }).closest("tr")!;
    expect(within(reports).getAllByText("writes")).toHaveLength(1);
    expect(within(reports).getAllByText("reads")).toHaveLength(4);

    expect(screen.getByRole("region", { name: "How the specialists check each other" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Where the facts come from" }).textContent).toContain("up to 3 competitors");
    const judgement = screen.getByRole("region", { name: "Where your judgement matters" });
    expect(within(judgement).getAllByRole("listitem")).toHaveLength(7);
    expect(screen.getByRole("region", { name: "What it is built with, and what each part does" }).textContent).toContain(
      "LangGraph StateGraph",
    );
    expect(screen.getByRole("region", { name: "From an idea to a document you can share" })).toBeTruthy();
  });

  test("draws the diagrams with Mermaid, and copies their source", async () => {
    fakeBackend();
    const user = userEvent.setup(); // with a clipboard of its own
    renderPage();
    await screen.findByRole("heading", { name: "One orchestrator, four specialists" });

    await user.click(screen.getAllByRole("button", { name: "Show the diagrams" })[0]);

    const dialog = screen.getByRole("dialog", { name: "Diagrams" });
    const graph = await within(dialog).findByRole("figure", { name: "The LangGraph state machine" });
    await waitFor(() => expect(graph.querySelector("svg")).toBeTruthy());
    expect(mermaid.render).toHaveBeenCalledWith(expect.stringMatching(/^diagram-/), PIPELINE.mermaid);
    expect(mermaid.initialize).toHaveBeenCalledWith(expect.objectContaining({ theme: "base", securityLevel: "strict" }));
    await user.click(within(graph).getByRole("button", { name: "Copy the Mermaid source" }));
    expect(await navigator.clipboard.readText()).toBe(PIPELINE.mermaid);
    expect(within(graph).getByRole("button", { name: "Copied" })).toBeTruthy();

    await user.click(within(dialog).getByRole("tab", { name: "How data flows" }));
    await waitFor(() => expect(mermaid.render).toHaveBeenCalledWith(expect.any(String), expect.stringContaining("sequenceDiagram")));
    expect(mermaid.render.mock.calls.some(([, text]) => text.includes("Below 4 of 5"))).toBe(true);
    await user.click(within(dialog).getByRole("tab", { name: "How decisions are made" }));
    await waitFor(() =>
      expect(mermaid.render.mock.calls.some(([, text]) => text.includes("Does each report score at least 4 of 5?"))).toBe(true),
    );
  });

  test("a diagram is drawn again, in the new colours, when the colour scheme changes", async () => {
    fakeBackend();
    let dark = false;
    const listeners = new Set<() => void>();
    vi.stubGlobal("matchMedia", (media: string) => ({
      media,
      get matches() {
        return dark;
      },
      addEventListener: (_: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
    }));
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "One orchestrator, four specialists" });

    await user.click(screen.getAllByRole("button", { name: "Show the diagrams" })[0]);
    const graph = await screen.findByRole("figure", { name: "The LangGraph state machine" });
    await waitFor(() => expect(graph.querySelector("svg")).toBeTruthy());
    await waitFor(() => expect(mermaid.render).toHaveBeenCalledTimes(3)); // one for each tab
    const first = graph.querySelector("svg")!.getAttribute("data-id");

    dark = true;
    act(() => listeners.forEach((listener) => listener()));

    await waitFor(() => expect(mermaid.render).toHaveBeenCalledTimes(6));
    await waitFor(() => expect(graph.querySelector("svg")!.getAttribute("data-id")).not.toBe(first));
  });

  test("a diagram Mermaid cannot draw shows its source instead", async () => {
    fakeBackend();
    mermaid.render.mockRejectedValueOnce(new Error("Parse error on line 2"));
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "One orchestrator, four specialists" });

    await user.click(screen.getAllByRole("button", { name: "Show the diagrams" })[0]);

    const dialog = screen.getByRole("dialog", { name: "Diagrams" });
    expect((await within(dialog).findByRole("alert")).textContent).toContain("could not be drawn (Parse error on line 2)");
    expect(within(dialog).getAllByText(/__start__/)[0].tagName).toBe("PRE");
  });

  test("without the API it says why", async () => {
    fakeBackend({ "GET /pipeline": { status: 500, body: null } });
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("needs the API running");
    expect(screen.getAllByRole("button", { name: "Show the diagrams" })[0].hasAttribute("disabled")).toBe(true);
  });
});

describe("the Monitor", () => {
  test("shows the health, the totals, the time by step, the latest runs and the log", async () => {
    fakeBackend();
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("tab", { name: "Monitor" }));

    const panel = screen.getByRole("tabpanel", { name: "Monitor" });
    const health = await within(panel).findByRole("status");
    expect(health.textContent).toContain("Warnings1 warning in the last 15 minutes.");
    expect(health.textContent).toContain("1 evaluation running now");
    expect(within(panel).getByText("1 failed, 50%")).toBeTruthy();
    // The time to a decision is the finished evaluation's, so it matches its row.
    expect(within(panel).getAllByText("2:37")).toHaveLength(2);
    expect(within(panel).getByText("median · p95 2:37 · slowest 2:37")).toBeTruthy();
    expect(within(panel).getByText("2.5% of 40 requests")).toBeTruthy();
    expect(within(panel).getByText("22 an evaluation · 2 retried")).toBeTruthy();
    expect(within(panel).getAllByText("95.0k")).toHaveLength(2); // the total, and the one run that finished
    expect(within(panel).getAllByText("3 of 4")).toHaveLength(2);
    expect(within(panel).getByText("75% passed review · 2 conflicts settled")).toBeTruthy();
    expect(within(panel).getByText("42 · 0")).toBeTruthy();
    expect(within(panel).getByText("prepared · written; 1 failed")).toBeTruthy();

    const steps = within(panel).getByRole("region", { name: "Where the time goes, per evaluation" });
    expect(within(steps).getAllByRole("listitem").map((item) => item.textContent?.split(/\d/)[0])).toEqual([
      "Plan",
      "Financial Planning",
      "Strategy",
    ]);
    expect(within(steps).getByText("9.5 s")).toBeTruthy(); // the plan's median
    expect(within(steps).getByText("· p95 9.9 s")).toBeTruthy();
    expect(within(steps).getByText("1.5 calls · 1.2k tokens")).toBeTruthy();
    expect(within(steps).getByText("1 call · 3.4k tokens")).toBeTruthy();
    const runs = within(panel).getByRole("region", { name: "Latest evaluations" });
    expect(within(runs).getByText("Azure OpenAI, 42 searches")).toBeTruthy();
    expect(within(runs).getByText("Failed").closest("td")?.getAttribute("title")).toBe("The LLM call failed: timeout");

    const log = within(panel).getByRole("region", { name: "Log" });
    expect(within(log).getAllByRole("listitem")).toHaveLength(MONITORING.events.length);
    // A problem names its request, to find it in the API's logs; routine lines do not.
    expect(within(log).getByText("request 3f2a9c1b").getAttribute("title")).toBe("Request 3f2a9c1b7d4e5f60");
    expect(within(log).queryByText("request a1b2c3d4")).toBeNull();
    await user.click(within(health).getByRole("button", { name: "Show them" }));
    expect(within(log).getAllByRole("listitem")).toHaveLength(1);
    expect(within(log).getByRole("button", { name: "Warnings and errors" }).getAttribute("aria-pressed")).toBe("true");
    expect(document.activeElement).toBe(log);
    expect(within(log).getByText("Evaluation failed on an LLM call: timeout")).toBeTruthy();
    await user.click(within(log).getByRole("button", { name: "Steps" }));
    expect(within(log).getByText("Reviewed 4 reports: approved 3.")).toBeTruthy();
    expect(within(log).getByText("Financial Planning")).toBeTruthy();
  });

  test("refreshes while it is shown, until paused", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { fetch } = fakeBackend();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage();
    const asked = () => fetch.mock.calls.filter(([url]) => String(url).endsWith("/monitoring")).length;
    await screen.findByRole("tab", { name: "Monitor" });
    expect(asked()).toBe(0); // not while the pipeline is shown

    await user.click(screen.getByRole("tab", { name: "Monitor" }));
    await waitFor(() => expect(asked()).toBe(1));
    await act(async () => vi.advanceTimersByTimeAsync(5000));
    expect(asked()).toBe(2);

    await user.click(screen.getByRole("button", { name: "Pause" }));
    await act(async () => vi.advanceTimersByTimeAsync(15000));
    expect(asked()).toBe(2);
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(asked()).toBe(3));
    expect(screen.getByRole("button", { name: "Resume" }).getAttribute("aria-pressed")).toBe("true");
  });

  test("it stops asking while the page is hidden, and asks at once when it is shown again", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { fetch } = fakeBackend();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage();
    const asked = () => fetch.mock.calls.filter(([url]) => String(url).endsWith("/monitoring")).length;
    await user.click(await screen.findByRole("tab", { name: "Monitor" }));
    await waitFor(() => expect(asked()).toBe(1));

    let visibility: DocumentVisibilityState = "hidden";
    const hidden = vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
    await act(async () => vi.advanceTimersByTimeAsync(30000));
    expect(asked()).toBe(1);

    visibility = "visible";
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await waitFor(() => expect(asked()).toBe(2));
    hidden.mockRestore();
  });

  test("the log shows the latest 40 lines, and older ones on request", async () => {
    const events = Array.from({ length: 45 }, (_, index) => ({ ...MONITORING.events[3], message: `Line ${index}.` }));
    fakeBackend({ "GET /monitoring": { body: { ...MONITORING, events } } });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Monitor" }));

    const log = await screen.findByRole("region", { name: "Log" });
    expect(within(log).getAllByRole("listitem")).toHaveLength(40);
    await user.click(within(log).getByRole("button", { name: "Show older" }));
    expect(within(log).getAllByRole("listitem")).toHaveLength(45);
  });

  test("when the API stops answering it keeps what it last heard, and waits longer between tries", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let down = false;
    const { fetch } = fakeBackend({
      "GET /monitoring": () => (down ? { status: 503, body: { detail: "Down." } } : { body: MONITORING }),
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage();
    const asked = () => fetch.mock.calls.filter(([url]) => String(url).endsWith("/monitoring")).length;
    await user.click(await screen.findByRole("tab", { name: "Monitor" }));
    await screen.findByText("1 failed, 50%");

    down = true;
    await act(async () => vi.advanceTimersByTimeAsync(5000));
    expect(asked()).toBe(2);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The API stopped answering: The backend returned 503: Down. Showing what it reported at");
    expect(alert.textContent).toContain("Trying again at");
    expect(screen.getByText("1 failed, 50%")).toBeTruthy(); // what it last heard
    expect(screen.queryByText("Healthy")).toBeNull(); // not the health it reported before

    // 10 s, then 20 s, rather than every 5 s.
    await act(async () => vi.advanceTimersByTimeAsync(9000));
    expect(asked()).toBe(2);
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(asked()).toBe(3);
    await act(async () => vi.advanceTimersByTimeAsync(19000));
    expect(asked()).toBe(3);
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(asked()).toBe(4);

    // Asked again at once, and back to every 5 s once it answers.
    down = false;
    await user.click(within(screen.getByRole("alert")).getByRole("button", { name: "Try now" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(asked()).toBe(5);
    await act(async () => vi.advanceTimersByTimeAsync(5000));
    expect(asked()).toBe(6);
  });

  test("an answer slower than 10 s is given up", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fakeBackend({ "GET /monitoring": () => new Promise<never>(() => {}) });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Monitor" }));

    await act(async () => vi.advanceTimersByTimeAsync(10000));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The API is not answering: The API took more than 10 s to answer. Trying again at",
    );
  });

  test("before anything has run it says how to start, and a failure says why", async () => {
    const idle = { status: "healthy" as const, warnings: 0, errors: 0, minutes: 15 };
    fakeBackend({
      "GET /monitoring": { body: { ...MONITORING, health: idle, running: 0, runs: [], events: [], nodes: [] } },
    });
    const user = userEvent.setup();
    const { unmount } = renderPage();
    await user.click(await screen.findByRole("tab", { name: "Monitor" }));
    expect(await screen.findByText("Nothing has run since the API started.")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Evaluate an idea/ }).getAttribute("href")).toBe("/");
    const health = screen.getByRole("status");
    expect(health.textContent).toBe("HealthyNo warnings or errors in the last 15 minutes.Nothing running now");
    unmount();

    fakeBackend({ "GET /monitoring": { status: 503, body: { detail: "Down." } } });
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Monitor" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The API is not answering: The backend returned 503: Down. Trying again at");
    // Paused, a failed refresh says why but sets no time to try again.
    await user.click(screen.getByRole("button", { name: "Pause" }));
    await user.click(within(alert).getByRole("button", { name: "Try now" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).not.toContain("Trying again"));
  });
});

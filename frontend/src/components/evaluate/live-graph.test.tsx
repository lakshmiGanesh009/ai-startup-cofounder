import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { EvaluateApp } from "@/components/evaluate/evaluate-app";
import { BackendProvider } from "@/lib/backend";
import { fakeBackend, GRAPH, liveStream, PIPELINE, RESULT, sse, STEPS } from "@/test/backend";

// Mermaid, drawing what the live graph needs: each node a group and each edge
// a path, with Mermaid's ids (a second edge between two nodes numbered on), in
// the order they are written.
const mermaid = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(async (id: string, text: string) => {
    const nodes = [...text.matchAll(/^\t(\w+)\(/gm)].map(([, node], index) => `<g class="node default" id="${id}-flowchart-${node}-${index}"><rect/></g>`);
    const seen = new Map<string, number>();
    const edges = [...text.matchAll(/^\t(\w+) (?:-->|-\.->|---|-\.-) (\w+);$/gm)].map(([, from, to]) => {
      const count = seen.get(`${from}_${to}`) ?? 0;
      seen.set(`${from}_${to}`, count + 1);
      return `<path class="flowchart-link" data-id="L_${from}_${to}_${count}"/>`;
    });
    return { svg: `<svg xmlns="http://www.w3.org/2000/svg" id="${id}">${nodes.join("")}${edges.join("")}</svg>` };
  }),
}));
vi.mock("mermaid", () => ({ default: mermaid }));

afterEach(() => {
  mermaid.render.mockClear();
});

function node(dialog: HTMLElement, name: string) {
  return dialog.querySelector(`g.node[id*="-flowchart-${name}-"]`)!;
}

// An edge as drawn: from, to, and which of the edges drawn between them.
function edge(dialog: HTMLElement, from: string, to: string, which = 0) {
  return dialog.querySelector(`path[data-id="L_${from}_${to}_${which}"]`)!;
}

describe("the live graph", () => {
  test("opens from the progress card and lights up the graph as the team works, then stays on the finished run", async () => {
    const live = liveStream();
    fakeBackend({
      "GET /pipeline": { body: { ...PIPELINE, mermaid: GRAPH } },
      "POST /evaluate/stream": () => ({ stream: live.stream }),
    });
    const user = userEvent.setup();
    render(
      <BackendProvider>
        <EvaluateApp />
      </BackendProvider>,
    );
    await user.type(screen.getByLabelText("The brief"), "An idea");
    await user.click(screen.getByRole("checkbox", { name: /Research it and check the brief first/ }));
    await user.click(screen.getByRole("button", { name: /^Evaluate\s*⌘↵$/ }));

    const card = await screen.findByRole("region", { name: "The team at work" });
    await act(async () => live.send(sse(STEPS.slice(0, 5), null)));
    await user.click(within(card).getByRole("button", { name: "Live graph" }));

    const dialog = screen.getByRole("dialog", { name: "The team at work, on the graph" });
    expect(within(dialog).getByText("An idea")).toBeTruthy();
    await waitFor(() => expect(dialog.querySelector(".live-graph svg")).toBeTruthy());
    expect(node(dialog, "plan").classList.contains("live-done")).toBe(true);
    expect(node(dialog, "finance").classList.contains("live-running")).toBe(true);
    expect(node(dialog, "marketing").classList.contains("live-done")).toBe(true);
    expect(node(dialog, "technical").classList.contains("live-skipped")).toBe(true);
    expect(node(dialog, "review").classList.contains("live-waiting")).toBe(true);
    expect((node(dialog, "finance") as SVGGElement).style.getPropertyValue("--live")).toBe("var(--agent-finance)");
    expect(edge(dialog, "plan", "finance").classList.contains("live-moving")).toBe(true);
    expect(edge(dialog, "plan", "marketing").classList.contains("live-taken")).toBe(true);
    expect(edge(dialog, "plan", "technical").classList.contains("live-taken")).toBe(false);

    const now = within(dialog).getByRole("region", { name: "What the team is doing" });
    expect(now.textContent).toContain("Financial Planning is writing its report.");
    const turns = within(dialog).getByRole("region", { name: "Step by step, newest first" });
    expect(within(turns).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      expect.stringContaining("Marketing Strategy0:09–0:27Wrote its report (4 words)."),
      expect.stringContaining("Financial Planning0:09Financial Planning is writing its report."),
      expect.stringContaining("Plan · Chief of Staff0:00–0:09Planned the work"),
    ]);

    // The report sent back: the review hands the work back to Finance.
    await act(async () => live.send(sse(STEPS.slice(5, 9), null)));
    expect(edge(dialog, "finance", "review").classList.contains("live-taken")).toBe(true);
    expect(edge(dialog, "finance", "review").classList.contains("live-moving")).toBe(false);
    // Review to Finance, drawn back up the graph: the work moving along it, backwards.
    const back = edge(dialog, "finance", "review", 1);
    expect([...back.classList]).toEqual(expect.arrayContaining(["live-taken", "live-moving", "live-back"]));
    expect(within(turns).getAllByRole("listitem")[0].textContent).toContain("Financial Planning · revision");

    await act(async () => {
      live.send(sse(STEPS.slice(9), { result: RESULT }));
      live.close();
    });
    await screen.findByRole("heading", { name: "Go with conditions" });
    // The pop-up stays open on the finished run.
    expect(screen.getByRole("dialog", { name: "The team at work, on the graph" })).toBe(dialog);
    expect(now.textContent).toContain("Finished");
    expect(now.textContent).toContain("The launch strategy is ready. Close this to read it.");
    expect(node(dialog, "__end__").classList.contains("live-done")).toBe(true);
    expect(edge(dialog, "synthesis", "__end__").classList.contains("live-taken")).toBe(true);
    expect(dialog.querySelectorAll(".live-moving")).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("the button shows only while the team works", async () => {
    fakeBackend();
    render(
      <BackendProvider>
        <EvaluateApp />
      </BackendProvider>,
    );
    const idle = await screen.findByRole("region", { name: "How the team works" });
    expect(within(idle).queryByRole("button", { name: "Live graph" })).toBeNull();
  });
});

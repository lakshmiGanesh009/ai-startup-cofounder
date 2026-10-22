import { describe, expect, test } from "vitest";

import type { Step } from "@/lib/api";
import { graphEdges } from "@/lib/how";
import { liveEdges, liveNodes, turns } from "@/lib/live-graph";
import { GRAPH, STEPS } from "@/test/backend";

const EDGES = graphEdges(GRAPH);

// The edges taken, as "from > to".
function taken(steps: Step[]) {
  const { taken: indexes, moving } = liveEdges(steps, EDGES);
  const name = (index: number) => `${EDGES[index].from} > ${EDGES[index].to}`;
  return { taken: [...indexes].map(name).sort(), moving: [...moving].map(name).sort() };
}

function states(steps: Step[], live = true) {
  return Object.fromEntries(Object.entries(liveNodes(steps, live)).map(([node, { state }]) => [node, state]));
}

describe("the live graph", () => {
  test("before the first step, the Chief of Staff is already planning", () => {
    expect(states([])).toMatchObject({ __start__: "done", plan: "running", finance: "waiting", __end__: "waiting" });
    expect(taken([])).toEqual({ taken: [], moving: [] });
    expect(taken(STEPS.slice(0, 1))).toEqual({ taken: ["__start__ > plan"], moving: ["__start__ > plan"] });
  });

  test("once the plan is in, the specialists it left out, and research not due, are skipped", () => {
    const writing = STEPS.slice(0, 5); // finance writing, marketing done
    expect(states(writing)).toMatchObject({
      plan: "done",
      finance: "running",
      marketing: "done",
      technical: "skipped",
      risk: "skipped",
      lookup: "skipped",
      research: "skipped",
      review: "waiting",
      synthesis: "waiting",
    });
    expect(taken(writing)).toEqual({
      taken: ["__start__ > plan", "plan > finance", "plan > marketing"],
      moving: ["plan > finance"],
    });
  });

  test("the look-ups take the work from the plan and hand it to the specialists", () => {
    const steps: Step[] = [
      { type: "start", node: "plan", at: 0 },
      { type: "done", node: "plan", at: 9, assigned: ["finance"] },
      { type: "start", node: "lookup", at: 9 },
      { type: "start", node: "research", at: 9 },
      { type: "done", node: "lookup", at: 20 },
      { type: "done", node: "research", at: 40 },
      { type: "start", node: "finance", at: 40 },
    ];
    expect(taken(steps)).toEqual({
      taken: ["__start__ > plan", "lookup > finance", "plan > lookup", "plan > research", "research > finance"],
      moving: ["lookup > finance", "research > finance"],
    });
    expect(states(steps)).toMatchObject({ lookup: "done", research: "done", finance: "running", marketing: "skipped" });
  });

  test("a whole run: the report sent back, the conflict settled, the revision, then the strategy", () => {
    expect(taken(STEPS)).toEqual({
      taken: [
        "__start__ > plan",
        "critique > resolve",
        "finance > review",
        "marketing > review",
        "marketing > synthesis",
        "plan > finance",
        "plan > marketing",
        "resolve > marketing",
        "review > critique",
        "review > finance",
        "synthesis > __end__",
      ],
      moving: [],
    });
    const done = liveNodes(STEPS, false);
    expect(done.finance).toEqual({ state: "done", runs: 2 });
    expect(done.review).toEqual({ state: "done", runs: 2 });
    expect(done.__end__.state).toBe("done");
    expect(done.technical.state).toBe("skipped");
  });

  test("a step still at work when the run stops has failed, and the run has no end", () => {
    expect(states(STEPS.slice(0, 7), false)).toMatchObject({ review: "failed", __end__: "waiting" });
    expect(states([...STEPS.slice(0, 4), { type: "done", node: "finance", at: 20, failed: true }])).toMatchObject({
      finance: "failed",
    });
  });

  test("lists each turn of each step, with when it began and ended", () => {
    const list = turns(STEPS.slice(0, 9));
    expect(list.map(({ node, run, started, finished }) => [node, run, started, finished])).toEqual([
      ["plan", 1, 0.1, 9.6],
      ["finance", 1, 9.7, 29.9],
      ["marketing", 1, 9.7, 27.2],
      ["review", 1, 30.0, 41.0],
      ["finance", 2, 41.1, undefined],
    ]);
    expect(list[3].done?.summary).toBe("Reviewed 2 reports: approved 1, sent back Financial Planning.");
  });
});

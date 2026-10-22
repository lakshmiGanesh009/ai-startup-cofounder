// Where the team is in the graph LangGraph runs, from the steps the API
// streams: the state of each node, the edges the run has taken, and each turn a
// node has taken, so the Evaluate page can light the graph up as the team works.

import type { Step } from "@/lib/api";
import type { GraphEdge } from "@/lib/how";
import { assigned, nodeStates, SPECIALISTS } from "@/lib/team";

export type LiveState = "waiting" | "running" | "done" | "failed" | "skipped";

export const LIVE_STATES: LiveState[] = ["waiting", "running", "done", "failed", "skipped"];

export type LiveNode = { state: LiveState; runs: number };

const SPECIALIST_NODES: string[] = SPECIALISTS;
const RESEARCH = ["lookup", "research"];
const LOOPS = ["review", "critique", "resolve"];

// Each node's state: at work, done (or failed), still to come, or skipped once
// the run has gone past it (a specialist the plan left out, research that was
// not due, a loop with nothing to do). A step still at work when the run ends
// has failed with it.
export function liveNodes(steps: Step[], live: boolean): Record<string, LiveNode> {
  const states = nodeStates(steps);
  const team: string[] | null = assigned(steps);
  const reached = (nodes: string[]) => nodes.some((node) => states[node]);
  const strategy = states.synthesis;

  function stateOf(node: string): LiveState {
    const state = states[node];
    if (node === "__start__") return live || steps.length ? "done" : "waiting";
    if (node === "__end__") return strategy?.last && !strategy.working ? "done" : "waiting";
    if (state?.working) return live ? "running" : "failed";
    if (state?.last) return state.last.failed ? "failed" : "done";
    // Before the first step arrives, the Chief of Staff is already planning.
    if (node === "plan" && live) return "running";
    if (SPECIALIST_NODES.includes(node) && team && !team.includes(node)) return "skipped";
    if (RESEARCH.includes(node) && reached(SPECIALIST_NODES)) return "skipped";
    if (LOOPS.includes(node) && strategy) return "skipped";
    return "waiting";
  }

  const nodes = ["__start__", "plan", ...RESEARCH, ...SPECIALIST_NODES, ...LOOPS, "synthesis", "__end__"];
  return Object.fromEntries(nodes.map((node) => [node, { state: stateOf(node), runs: states[node]?.runs ?? 0 }]));
}

// The edges the run has taken (by their index in `edges`), and those the work
// is moving along now, into a step at work. A step that starts was handed the
// work by the steps with an edge to it that finished since it last started,
// less those that handed it on to another of them first: the plan hands the
// work to the look-ups, and they to the specialists.
export function liveEdges(steps: Step[], edges: GraphEdge[]): { taken: Set<number>; moving: Set<number> } {
  const into = new Map<string, number[]>();
  edges.forEach((edge, index) => into.set(edge.to, [...(into.get(edge.to) ?? []), index]));
  const started = new Map<string, number>();
  const finished = new Map<string, number>();
  const handed = new Map<string, number[]>();
  const taken = new Set<number>();

  steps.forEach((step, at) => {
    if (step.type === "done") {
      finished.set(step.node, at);
      return;
    }
    const since = started.get(step.node) ?? -1;
    const incoming = into.get(step.node) ?? [];
    const from = incoming.filter((index) => (finished.get(edges[index].from) ?? -1) > since);
    const direct = from.filter(
      (index) => !from.some((other) => (started.get(edges[other].from) ?? -1) > finished.get(edges[index].from)!),
    );
    const along = direct.length ? direct : incoming.filter((index) => edges[index].from === "__start__");
    along.forEach((index) => taken.add(index));
    handed.set(step.node, along);
    started.set(step.node, at);
  });

  const states = nodeStates(steps);
  edges.forEach((edge, index) => {
    if (edge.to === "__end__" && states[edge.from]?.last && !states[edge.from].working) taken.add(index);
  });
  const moving = new Set([...handed].filter(([node]) => states[node]?.working).flatMap(([, along]) => along));
  return { taken, moving };
}

// A turn a step took: which run of it, when it began and finished, and what it did.
export type Turn = { node: string; run: number; started: number; finished?: number; done?: Step };

// Each turn of each step, in the order they began.
export function turns(steps: Step[]): Turn[] {
  const all: Turn[] = [];
  const open = new Map<string, Turn>();
  const runs = new Map<string, number>();
  for (const step of steps) {
    if (step.type === "start") {
      const run = (runs.get(step.node) ?? 0) + 1;
      runs.set(step.node, run);
      const turn: Turn = { node: step.node, run, started: step.at };
      all.push(turn);
      open.set(step.node, turn);
      continue;
    }
    const turn = open.get(step.node);
    if (turn) {
      turn.finished = step.at;
      turn.done = step;
      open.delete(step.node);
    } else {
      all.push({ node: step.node, run: runs.get(step.node) ?? 1, started: step.at, finished: step.at, done: step });
    }
  }
  return all;
}

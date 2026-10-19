// What the UI says about the founding team: its members, the stages of its
// work, and how long a request takes at the chosen reasoning efforts.

import type { Effort, Reasoning, Specialist, Step } from "@/lib/api";

export const SPECIALISTS: Specialist[] = ["marketing", "finance", "technical", "risk"];

export const SPECIALIST_TITLES: Record<Specialist, string> = {
  marketing: "Marketing Strategy",
  finance: "Financial Planning",
  technical: "Technical Feasibility",
  risk: "Risk & Compliance",
};

export function specialistTitle(name: string): string {
  return SPECIALIST_TITLES[name as Specialist] ?? name;
}

// Who did a step of the graph.
export function actor(node: string): string {
  if (node in SPECIALIST_TITLES) return SPECIALIST_TITLES[node as Specialist];
  if (node === "critique") return "Specialists";
  return "Chief of Staff";
}

export type StageState = "waiting" | "working" | "done" | "skipped";

export type Stage = { key: string; title: string; who: string; about: string; nodes: string[] };

// The team's work, in the order the graph runs it (graph.py).
export const STAGES: Stage[] = [
  {
    key: "plan",
    title: "Plan",
    who: "Chief of Staff",
    about: "Turns the brief into the decision to make, and assigns the specialists it needs.",
    nodes: ["plan"],
  },
  {
    key: "reports",
    title: "Reports",
    who: "The specialists",
    about: "Marketing, finance, technical and risk write their reports at the same time.",
    nodes: SPECIALISTS,
  },
  {
    key: "review",
    title: "Review",
    who: "Chief of Staff",
    about: "Scores each report against a rubric and sends weak ones back once.",
    nodes: ["review"],
  },
  {
    key: "cross-check",
    title: "Cross-check",
    who: "The specialists, then the Chief of Staff",
    about: "The specialists check each other's reports; the Chief of Staff settles each conflict.",
    nodes: ["critique", "resolve"],
  },
  {
    key: "strategy",
    title: "Strategy",
    who: "Chief of Staff",
    about: "Writes the launch strategy from the approved reports.",
    nodes: ["synthesis"],
  },
];

export type NodeState = { runs: number; working: boolean; last?: Step };

// What the steps so far say about each node: how often it began, whether it is
// at work now, and the last thing it finished.
export function nodeStates(steps: Step[]): Record<string, NodeState> {
  const states: Record<string, NodeState> = {};
  for (const step of steps) {
    const node = (states[step.node] ??= { runs: 0, working: false });
    if (step.type === "start") {
      node.runs += 1;
      node.working = true;
    } else {
      node.working = false;
      node.last = step;
    }
  }
  return states;
}

// Names as a phrase: "A", "A and B", "A, B and C".
export function joinNames(names: string[]): string {
  return names.length <= 1 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}

function writing(names: string[], verb: string): string {
  const titles = joinNames(names.map(specialistTitle));
  return names.length === 1 ? `${titles} is ${verb} its report.` : `${titles} are ${verb} their reports.`;
}

const AT_WORK: Record<string, string> = {
  plan: "The Chief of Staff is reading the brief and planning the work.",
  review: "The Chief of Staff is reviewing the reports.",
  critique: "The specialists are cross-checking each other's reports.",
  resolve: "The Chief of Staff is settling the conflicts.",
  synthesis: "The Chief of Staff is writing the launch strategy.",
};

// What the team is doing now, from the steps so far.
export function activity(steps: Step[]): string {
  if (!steps.length) return AT_WORK.plan;
  const busy = Object.entries(nodeStates(steps)).filter(([, state]) => state.working);
  const writers = busy.filter(([node, state]) => node in SPECIALIST_TITLES && state.runs === 1).map(([node]) => node);
  const revisers = busy.filter(([node, state]) => node in SPECIALIST_TITLES && state.runs > 1).map(([node]) => node);
  const others = busy.filter(([node]) => !(node in SPECIALIST_TITLES)).map(([node]) => AT_WORK[node] ?? `${actor(node)} is working.`);
  const sentences = [
    ...others,
    ...(writers.length ? [writing(writers, "writing")] : []),
    ...(revisers.length ? [writing(revisers, "revising")] : []),
  ];
  return sentences.length ? sentences.join(" ") : "Passing the work on.";
}

// The specialists the plan assigned, once it has.
export function assigned(steps: Step[]): Specialist[] | null {
  const plan = steps.find((step) => step.type === "done" && step.node === "plan");
  return plan?.assigned ?? null;
}

export function stageState(stage: Stage, states: Record<string, NodeState>, team: Specialist[] | null): StageState {
  const nodes = stage.key === "reports" ? (team ?? SPECIALISTS) : stage.nodes;
  if (nodes.some((node) => states[node]?.working)) return "working";
  // With one specialist there is nothing to cross-check, so the graph skips it.
  if (stage.key === "cross-check" && !states.critique && states.synthesis) return "skipped";
  const ran = nodes.filter((node) => states[node]?.runs);
  if (ran.length && (stage.key !== "reports" || ran.length === nodes.length)) return "done";
  return "waiting";
}

// Measured per call on the team's Azure gpt-5-mini deployment (docs/performance.md).
export const SECONDS_PER_CALL: Record<Effort, string> = {
  minimal: "~4 s",
  low: "~6 s",
  medium: "~9 s",
  high: "~27 s",
};

// How long an evaluation takes, by the highest effort chosen.
export function evaluationWait(reasoning: Reasoning | null): string {
  const efforts = Object.values(reasoning ?? {});
  if (efforts.includes("high")) return "At high reasoning this takes 5 to 10 minutes.";
  if (efforts.includes("medium")) return "This takes about two minutes.";
  return "This takes about a minute.";
}

// How long writing or revising the proposal takes (measured: 40-82 s at the defaults).
export function proposalWait(reasoning: Reasoning | null): string {
  const efforts = Object.values(reasoning ?? {});
  if (efforts.includes("high")) return "At high reasoning this takes several minutes.";
  return "This takes a minute or two.";
}

export function formatSeconds(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  return `${minutes}:${String(whole % 60).padStart(2, "0")}`;
}

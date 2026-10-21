// The team's six stages of work, each in the colour of the agent who does it.
// Before a request it explains them; while the team works it shows, from the
// steps the API streams, which stage is under way, what each finished, and
// which specialists are writing.

import { useId } from "react";

import { AgentAvatar, AgentStack } from "@/components/ui/agent";
import { AlertIcon, CheckIcon } from "@/components/ui/icons";
import { type AgentKey, agentClass, SPECIALIST_AGENTS } from "@/lib/agents";
import type { Specialist, Step } from "@/lib/api";
import {
  assigned,
  type NodeState,
  nodeStates,
  SPECIALISTS,
  type Stage,
  STAGES,
  type StageState,
  stageState,
} from "@/lib/team";

const SHORT: Record<Specialist, string> = {
  marketing: "Marketing",
  finance: "Finance",
  technical: "Technical",
  risk: "Risk",
};

// Who does each stage: the Chief of Staff's own, the web's, or the specialists'.
export const STAGE_AGENTS: Record<string, AgentKey[]> = {
  plan: ["chief"],
  research: ["research"],
  reports: SPECIALIST_AGENTS,
  review: ["chief"],
  "cross-check": [...SPECIALIST_AGENTS, "chief"],
  strategy: ["chief"],
};

// A ring in the colours of the agents who share a stage.
function ring(agents: AgentKey[]): string {
  const share = 100 / agents.length;
  const stops = agents.map((agent, i) => `var(--agent-${agent}) ${i * share}% ${(i + 1) * share}%`);
  return `conic-gradient(${stops.join(", ")})`;
}

function Glyph({ state, number, agents }: { state: StageState; number: number; agents: AgentKey[] }) {
  const single = agents.length === 1 ? agents[0] : null;
  if (state === "done" || state === "working") {
    const mark =
      state === "done" ? (
        <CheckIcon className={`size-3.5 ${single ? "text-white" : "text-ink"}`} />
      ) : (
        <span className={`working-dot size-2 rounded-full ${single ? "bg-agent" : "bg-ink-2"}`} />
      );
    if (single) {
      return (
        <span
          className={`${agentClass(single)} flex size-7 shrink-0 items-center justify-center rounded-full ${
            state === "done" ? "bg-agent-solid" : "border-2 border-agent bg-agent-soft"
          }`}
        >
          {mark}
        </span>
      );
    }
    return (
      <span className="relative flex size-7 shrink-0 items-center justify-center">
        <span
          aria-hidden
          className={`absolute inset-0 rounded-full ${state === "working" ? "stage-turning" : ""}`}
          style={{ background: ring(agents) }}
        />
        <span className="absolute inset-[3px] rounded-full bg-surface" />
        <span className="relative flex">{mark}</span>
      </span>
    );
  }
  if (state === "skipped") {
    return (
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full border border-dashed border-rule-strong bg-surface text-[11px] text-ink-3">
        –
      </span>
    );
  }
  // Waiting: the number on the tint of whoever will do it.
  if (single) {
    return (
      <span
        className={`${agentClass(single)} flex size-7 shrink-0 items-center justify-center rounded-full bg-agent-soft text-[11px] font-medium text-agent-deep tabular shadow-[inset_0_0_0_1px_var(--agent-line)]`}
      >
        {number}
      </span>
    );
  }
  return (
    <span className="relative flex size-7 shrink-0 items-center justify-center">
      <span aria-hidden className="absolute inset-0 rounded-full opacity-45" style={{ background: ring(agents) }} />
      <span className="absolute inset-[2px] rounded-full bg-surface" />
      <span className="relative text-[11px] font-medium text-ink-2 tabular">{number}</span>
    </span>
  );
}

const STATE_WORDS: Record<StageState, string> = {
  waiting: "",
  working: "Working",
  done: "Done",
  skipped: "Skipped",
};

// The latest thing a stage's agents finished, to say under it.
function latest(stage: Stage, states: Record<string, NodeState>): Step | undefined {
  return stage.nodes
    .map((node) => states[node]?.last)
    .filter((step): step is Step => Boolean(step))
    .sort((a, b) => b.at - a.at)[0];
}

function Specialists({ states, team }: { states: Record<string, NodeState>; team: Specialist[] | null }) {
  return (
    <ul className="mt-3 space-y-1.5 text-[13px]">
      {SPECIALISTS.map((name) => {
        const state = states[name];
        const needed = !team || team.includes(name);
        let word = "Waiting";
        let mark: React.ReactNode = null;
        if (!needed) word = "Not needed";
        else if (state?.working) {
          word = state.runs > 1 ? "Revising" : "Writing";
          mark = <span className="working-dot size-1.5 rounded-full bg-agent" />;
        } else if (state?.last?.failed) {
          word = "Failed";
          mark = <AlertIcon className="size-3 text-bad" />;
        } else if (state?.last) {
          word = state.runs > 1 ? "Revised" : "Done";
          mark = <CheckIcon className="size-3 text-agent-deep" />;
        }
        return (
          <li
            key={name}
            className={`${agentClass(name)} flex items-center gap-2 rounded-md px-1.5 py-1 ${
              needed ? "bg-agent-soft text-ink" : "text-ink-3 opacity-60"
            }`}
          >
            <AgentAvatar agent={name} size="xs" />
            <span className={needed ? "" : "line-through decoration-ink-3/50"}>{SHORT[name]}</span>
            <span className="ml-auto flex items-center gap-1.5 text-xs text-ink-3">
              {mark}
              {word}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function TeamProgress({ steps, live }: { steps: Step[]; live: boolean }) {
  const states = nodeStates(steps);
  const team = assigned(steps);
  // The idle panel stays in the page, hidden, while the live one shows.
  const heading = useId();

  return (
    <section aria-labelledby={heading}>
      <h2 id={heading} className="kicker">
        {live ? "The team at work" : "How the team works"}
      </h2>
      <ol className="mt-4">
        {STAGES.map((stage, index) => {
          // Before the first step arrives, the Chief of Staff is already planning.
          const state: StageState = !live
            ? "waiting"
            : index === 0 && !steps.length
              ? "working"
              : stageState(stage, states, team);
          const last = live ? latest(stage, states) : undefined;
          const agents = STAGE_AGENTS[stage.key] ?? ["chief"];
          const next = STAGES[index + 1] && (STAGE_AGENTS[STAGES[index + 1].key] ?? ["chief"]);
          return (
            <li
              key={stage.key}
              className="relative flex gap-3.5 pb-6 last:pb-0"
              aria-label={`${stage.title}: ${STATE_WORDS[state] || "Waiting"}`}
            >
              {next && (
                <span
                  aria-hidden
                  className="absolute top-8 bottom-1 left-[13.5px] w-px"
                  style={{
                    background:
                      state === "done" || state === "skipped"
                        ? `linear-gradient(var(--agent-${agents.at(-1)}), var(--agent-${next[0]}))`
                        : "var(--rule)",
                  }}
                />
              )}
              <Glyph state={state} number={index + 1} agents={agents} />
              <div className="min-w-0 flex-1 pt-1">
                <div className="flex items-center gap-3">
                  <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-sm font-medium text-ink">{stage.title}</span>
                    {agents.length > 1 ? <AgentStack agents={agents} /> : <AgentAvatar agent={agents[0]} size="sm" />}
                    <span className="text-xs text-ink-3">{stage.who}</span>
                  </p>
                  {live && STATE_WORDS[state] && (
                    <span className={`ml-auto shrink-0 text-xs ${state === "working" ? "font-medium text-ink" : "text-ink-3"}`}>
                      {STATE_WORDS[state]}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-[13px] leading-snug text-ink-2">
                  {last && stage.key !== "reports" ? last.summary : stage.about}
                </p>
                {live && stage.key === "reports" && <Specialists states={states} team={team} />}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

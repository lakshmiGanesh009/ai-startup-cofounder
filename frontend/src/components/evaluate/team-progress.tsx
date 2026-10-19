// The team's five stages of work. Before a request it explains them; while
// the team works it shows, from the steps the API streams, which stage is under
// way, what each finished, and which specialists are writing.

import { AlertIcon, CheckIcon } from "@/components/ui/icons";
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

function Glyph({ state, number }: { state: StageState; number: number }) {
  if (state === "done") {
    return (
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-ink">
        <CheckIcon className="size-3.5" />
      </span>
    );
  }
  if (state === "working") {
    return (
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full border-[1.5px] border-primary bg-surface">
        <span className="working-dot size-2 rounded-full bg-primary" />
      </span>
    );
  }
  return (
    <span
      className={`flex size-6 shrink-0 items-center justify-center rounded-full border bg-paper text-[11px] text-ink-3 tabular ${
        state === "skipped" ? "border-dashed border-rule-strong" : "border-rule-strong"
      }`}
    >
      {state === "skipped" ? "–" : number}
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
    <ul className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[13px]">
      {SPECIALISTS.map((name) => {
        const state = states[name];
        const needed = !team || team.includes(name);
        let word = "Waiting";
        let mark: React.ReactNode = <span className="size-1.5 rounded-full bg-rule-strong" />;
        if (!needed) word = "Not needed";
        else if (state?.working) {
          word = state.runs > 1 ? "Revising" : "Writing";
          mark = <span className="working-dot size-1.5 rounded-full bg-primary" />;
        } else if (state?.last?.failed) {
          word = "Failed";
          mark = <AlertIcon className="size-3 text-bad" />;
        } else if (state?.last) {
          word = state.runs > 1 ? "Revised" : "Done";
          mark = <CheckIcon className="size-3 text-primary" />;
        }
        return (
          <li key={name} className={`flex items-center gap-2 ${needed ? "text-ink" : "text-ink-3 line-through decoration-ink-3/50"}`}>
            <span aria-hidden className="flex w-3 justify-center">
              {mark}
            </span>
            <span>{SHORT[name]}</span>
            <span className="text-xs text-ink-3 no-underline">{word}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function TeamProgress({ steps, live }: { steps: Step[]; live: boolean }) {
  const states = nodeStates(steps);
  const team = assigned(steps);

  return (
    <section aria-labelledby="team-heading">
      <h2 id="team-heading" className="kicker">
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
          return (
            <li key={stage.key} className="relative flex gap-3.5 pb-6 last:pb-0" aria-label={`${stage.title}: ${STATE_WORDS[state] || "Waiting"}`}>
              {index < STAGES.length - 1 && (
                <span aria-hidden className="absolute top-7 bottom-1 left-[11.5px] w-px bg-rule" />
              )}
              <Glyph state={state} number={index + 1} />
              <div className="min-w-0 flex-1 pt-0.5">
                <div className="flex items-baseline gap-3">
                  <p className="flex min-w-0 flex-wrap items-baseline gap-x-2">
                    <span className="text-sm font-medium text-ink">{stage.title}</span>
                    <span className="text-xs text-ink-3">{stage.who}</span>
                  </p>
                  {live && STATE_WORDS[state] && (
                    <span
                      className={`ml-auto shrink-0 text-xs ${state === "working" ? "font-medium text-primary" : "text-ink-3"}`}
                    >
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

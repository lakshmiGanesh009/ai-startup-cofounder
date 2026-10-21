// What the team has finished so far, newest last, as the API streams it: each
// step under the avatar of the agent who did it, and the agents at work now.

import { useId } from "react";

import { AgentAvatar, AgentStack } from "@/components/ui/agent";
import { agentOf, agentsOf, SPECIALIST_AGENTS, type AgentKey } from "@/lib/agents";
import type { Step } from "@/lib/api";
import { activity, actor, formatSeconds, nodeStates } from "@/lib/team";

// The agents at work now, for the line under the log.
function busy(steps: Step[]): AgentKey[] {
  if (!steps.length) return ["chief"];
  const working = Object.entries(nodeStates(steps))
    .filter(([, state]) => state.working)
    .flatMap(([node]) => agentsOf(node));
  return [...new Set(working)];
}

export function ActivityLog({ steps }: { steps: Step[] }) {
  const finished = steps.filter((step) => step.type === "done");
  const heading = useId();
  const now = busy(steps);

  return (
    <section aria-labelledby={heading}>
      <h2 id={heading} className="kicker">
        What the team has done
      </h2>
      <ol className="mt-3">
        {finished.map((step, index) => {
          const agent = agentOf(step.node);
          const shared = step.node === "critique";
          return (
            <li key={`${step.node}-${index}`} className="relative grid grid-cols-[2rem_minmax(0,1fr)] gap-3 pb-4 text-sm">
              <span aria-hidden className="absolute top-8 bottom-0 left-[15.5px] w-px bg-rule" />
              <span className="flex justify-center pt-0.5">
                {shared ? <AgentStack agents={SPECIALIST_AGENTS} /> : <AgentAvatar agent={agent} size="md" />}
              </span>
              <div className={`min-w-0 rounded-lg border px-3.5 py-2.5 ${step.failed ? "border-bad/40 bg-bad-soft" : "border-rule bg-surface"}`}>
                <p className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="font-medium text-ink">{step.provider ?? actor(step.node)}</span>
                  <time className="font-mono text-[11px] text-ink-3 tabular">{formatSeconds(step.at)}</time>
                </p>
                <p className={`mt-0.5 ${step.failed ? "text-bad" : "text-ink-2"}`}>{step.summary}</p>
                {step.node === "plan" && step.objective && (
                  <p className="mt-2 border-l-2 border-[var(--agent-chief)] pl-3 font-serif text-[15px] leading-snug text-ink-2 italic">
                    {step.objective}
                  </p>
                )}
              </div>
            </li>
          );
        })}
        <li className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3 text-sm">
          <span className="flex justify-center pt-1">
            {now.length > 1 ? (
              <span className="flex size-8 items-center justify-center rounded-full border border-dashed border-rule-strong">
                <span aria-hidden className="working-dot size-2 rounded-full bg-ink-3" />
              </span>
            ) : (
              <AgentAvatar agent={now[0] ?? "chief"} size="md" />
            )}
          </span>
          <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 pt-1.5 text-ink-3">
            {now.length > 1 ? (
              <AgentStack agents={now} />
            ) : (
              <span aria-hidden className="working-dot size-1.5 shrink-0 rounded-full bg-ink-3" />
            )}
            <span>{activity(steps)}</span>
          </p>
        </li>
      </ol>
    </section>
  );
}

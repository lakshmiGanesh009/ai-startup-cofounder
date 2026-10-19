// What the team has finished so far, newest last, as the API streams it.

import { useId } from "react";

import type { Step } from "@/lib/api";
import { activity, actor, formatSeconds } from "@/lib/team";

export function ActivityLog({ steps }: { steps: Step[] }) {
  const finished = steps.filter((step) => step.type === "done");
  const heading = useId();

  return (
    <section aria-labelledby={heading}>
      <h2 id={heading} className="kicker">
        What the team has done
      </h2>
      <ol className="mt-3 border-t border-rule">
        {finished.map((step, index) => (
          <li key={`${step.node}-${index}`} className="grid grid-cols-[3rem_minmax(0,1fr)] gap-3 border-b border-rule py-3 text-sm">
            <time className="pt-px font-mono text-xs text-ink-3 tabular">{formatSeconds(step.at)}</time>
            <div>
              <p>
                <span className="font-medium text-ink">{actor(step.node)}</span>{" "}
                <span className={step.failed ? "text-bad" : "text-ink-2"}>{step.summary}</span>
              </p>
              {step.node === "plan" && step.objective && (
                <p className="mt-1.5 font-serif text-[15px] leading-snug text-ink-2 italic">{step.objective}</p>
              )}
            </div>
          </li>
        ))}
        <li className="grid grid-cols-[3rem_minmax(0,1fr)] gap-3 py-3 text-sm">
          <span aria-hidden className="flex justify-start pt-1.5">
            <span className="working-dot size-1.5 rounded-full bg-primary" />
          </span>
          <p className="text-ink-3">{activity(steps)}</p>
        </li>
      </ol>
    </section>
  );
}

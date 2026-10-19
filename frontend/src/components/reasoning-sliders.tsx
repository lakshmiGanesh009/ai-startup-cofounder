"use client";

// Two sliders: how hard the specialists and the Chief of Staff reason for the
// requests this app sends. They start at the backend's configured efforts.

import { EFFORTS } from "@/lib/api";
import { useBackend } from "@/lib/backend";
import { evaluationWait, SECONDS_PER_CALL } from "@/lib/team";

const ROLES = [
  {
    role: "specialist",
    label: "Specialists",
    help: "Marketing, finance, technical and risk: their reports, critiques and proposal parts.",
  },
  {
    role: "chief",
    label: "Chief of Staff",
    help: "Planning, reviews, decisions on conflicts, the strategy and the proposal's executive summary.",
  },
] as const;

export function ReasoningSliders() {
  const { status, health, reasoning, setEffort } = useBackend();
  const adjustable = Boolean(health?.reasoning.adjustable);
  const efforts = health?.reasoning.efforts.length ? health.reasoning.efforts : [...EFFORTS];

  return (
    <section aria-labelledby="reasoning-heading">
      <h2 id="reasoning-heading" className="kicker">
        Reasoning
      </h2>
      <div className="mt-3 space-y-4">
        {ROLES.map(({ role, label, help }) => {
          const current = reasoning?.[role] ?? health?.reasoning[role] ?? "minimal";
          const index = Math.max(0, efforts.indexOf(current));
          const fill = `${(index / Math.max(efforts.length - 1, 1)) * 100}%`;
          return (
            <div key={role} title={help}>
              <div className="flex items-baseline justify-between gap-2">
                <label htmlFor={`effort-${role}`} className="text-[13px] font-medium text-ink">
                  {label}
                </label>
                <span aria-hidden className="text-xs text-ink-2">
                  {efforts[index]}
                  <span className="text-ink-3"> · {SECONDS_PER_CALL[efforts[index]]}</span>
                </span>
              </div>
              <input
                id={`effort-${role}`}
                type="range"
                min={0}
                max={efforts.length - 1}
                step={1}
                value={index}
                disabled={!adjustable}
                aria-valuetext={efforts[index]}
                aria-describedby="reasoning-note"
                onChange={(event) => setEffort(role, efforts[Number(event.target.value)])}
                className="range mt-1"
                style={{ "--fill": fill } as React.CSSProperties}
              />
            </div>
          );
        })}
      </div>
      <p id="reasoning-note" className="mt-2 text-xs leading-relaxed text-ink-3">
        {status === "checking" && "Checking what the backend offers…"}
        {status === "down" && "Unavailable until the backend answers."}
        {status === "up" && !adjustable && "This provider takes no reasoning setting; only Azure OpenAI does."}
        {status === "up" && adjustable && `More reasoning, more considered answers, slower calls. ${evaluationWait(reasoning)}`}
      </p>
    </section>
  );
}

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
    <section aria-labelledby="reasoning-heading" className="space-y-4">
      <h2 id="reasoning-heading" className="text-sm font-semibold">
        Reasoning
      </h2>
      {ROLES.map(({ role, label, help }) => {
        const current = reasoning?.[role] ?? health?.reasoning[role] ?? "minimal";
        const index = Math.max(0, efforts.indexOf(current));
        return (
          <div key={role}>
            <div className="flex items-baseline justify-between text-sm" title={help}>
              <label htmlFor={`effort-${role}`}>{label}</label>
              <span aria-hidden className="font-medium text-accent-strong dark:text-accent-soft">
                {efforts[index]}
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
              className="mt-1 w-full accent-accent disabled:opacity-40"
            />
            <div aria-hidden className="flex justify-between text-[10px] text-zinc-400">
              {efforts.map((effort) => (
                <span key={effort}>{effort}</span>
              ))}
            </div>
          </div>
        );
      })}
      <p id="reasoning-note" className="text-xs leading-relaxed text-zinc-500">
        {status === "checking" && "Checking what the backend offers…"}
        {status === "down" && "Unavailable until the backend answers."}
        {status === "up" && !adjustable && "This provider takes no reasoning setting; only Azure OpenAI does."}
        {status === "up" &&
          adjustable &&
          `Higher reasoning gives more considered answers but slower calls (${efforts
            .map((effort) => `${effort} ${SECONDS_PER_CALL[effort]}`)
            .join(", ")} a call). ${evaluationWait(reasoning)}`}
      </p>
    </section>
  );
}

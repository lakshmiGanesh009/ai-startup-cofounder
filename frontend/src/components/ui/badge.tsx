// A small label for a state: a verdict, a rating, "edited".

import { type AgentKey, agentClass } from "@/lib/agents";

const TONES = {
  neutral: "bg-sunken text-ink-2",
  primary: "bg-primary-soft text-primary",
  good: "bg-good-soft text-good",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
};

export type Tone = keyof typeof TONES;

export function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: Tone }) {
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs leading-4 font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}

// A review score out of five, as five marks, with the number for those who can't
// see them; in the reviewed agent's colour when one is given.
export function Score({ score, agent }: { score: number; agent?: AgentKey }) {
  return (
    <span className={`inline-flex items-center gap-1.5 ${agent ? agentClass(agent) : ""}`} title={`Score ${score} of 5`}>
      <span aria-hidden className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((mark) => (
          <span
            key={mark}
            className={`h-2.5 w-1.5 rounded-[1px] ${mark <= score ? (agent ? "bg-agent-solid" : "bg-ink") : "bg-rule-strong"}`}
          />
        ))}
      </span>
      <span className="text-xs text-ink-3 tabular">{score}/5</span>
    </span>
  );
}

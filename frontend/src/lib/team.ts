// What the UI says about the founding team: its members' names, and how long a
// request takes at the chosen reasoning efforts.

import type { Effort, Reasoning, Specialist } from "@/lib/api";

export const SPECIALIST_TITLES: Record<Specialist, string> = {
  marketing: "Marketing Strategy",
  finance: "Financial Planning",
  technical: "Technical Feasibility",
  risk: "Risk & Compliance",
};

export function specialistTitle(name: string): string {
  return SPECIALIST_TITLES[name as Specialist] ?? name;
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

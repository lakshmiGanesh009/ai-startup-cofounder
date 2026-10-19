// A stand-in for the FastAPI backend in tests: answers fetch() like the API
// and records what the app sent.

import { vi } from "vitest";

import type { EvaluateResponse, Health, Scenario } from "@/lib/api";

export const HEALTH: Health = {
  status: "healthy",
  service: "AI Startup Co-Founder Team",
  reasoning: {
    adjustable: true,
    efforts: ["minimal", "low", "medium", "high"],
    specialist: "minimal",
    chief: "medium",
  },
};

export const SCENARIOS: Scenario[] = [
  {
    name: "healthcare_scheduling",
    prompt: "Evaluate an assistant that schedules patient follow-ups.",
    context: { target_market: "Small clinics", constraints: "Under $15k", competitive_landscape: null },
    follow_up: "Refine the pricing strategy after financial review.",
  },
  { name: "gtm_risk", prompt: "Identify risks in our go-to-market plan.", context: null, follow_up: null },
];

export const RESULT: EvaluateResponse = {
  session_id: "session-1234567890",
  objective: "Decide whether to launch a paid pilot.",
  assignments: { finance: "Price the pilot.", marketing: "Pick the first niche." },
  analyses: {
    finance: "Charge **$149** a month (assumption).",
    marketing: "Start with small clinics.",
  },
  review_history: [
    {
      finance: { approved: false, score: 3, feedback: "Show the break-even arithmetic." },
      marketing: { approved: true, score: 5, feedback: "" },
    },
  ],
  resolutions: [
    {
      conflict: { raised_by: "finance", about: "marketing", issue: "The pilot price is too low." },
      decision: "Charge $149 a month.",
      revise: "marketing",
    },
  ],
  metrics: {
    plan: { calls: 1, seconds: 9.5, tokens: 1200 },
    synthesis: { calls: 1, seconds: 19, tokens: 3400 },
  },
  final_strategy: "## Go with conditions\nLaunch a paid pilot with five clinics.",
};

type Answer = { status?: number; body?: unknown };
// A function answers each call afresh, from the body sent, and can hold the
// call open with a promise.
export type Answering = Answer | ((body: unknown) => Answer | Promise<Answer>);

export function fakeBackend(overrides: Partial<Record<string, Answering>> = {}) {
  const sent: { path: string; body: unknown }[] = [];
  const answers: Record<string, Answering | undefined> = {
    "GET /health": { body: HEALTH },
    "GET /scenarios": { body: SCENARIOS },
    "POST /evaluate": { body: RESULT },
    ...overrides,
  };
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    const key = `${init?.method ?? "GET"} ${path}`;
    const request = init?.body ? JSON.parse(String(init.body)) : undefined;
    if (init?.body) sent.push({ path, body: request });
    const answer = answers[key];
    if (!answer) throw new TypeError("Failed to fetch");
    const { status = 200, body } = typeof answer === "function" ? await answer(request) : answer;
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetch);
  return { fetch, sent };
}

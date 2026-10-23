// A stand-in for the FastAPI backend in tests: answers fetch() like the API
// and records what the app sent.

import { vi } from "vitest";

import type {
  DeepResearch,
  EvaluateResponse,
  Health,
  Monitoring,
  Pipeline,
  PreparedBrief,
  Scenario,
  Step,
  Template,
} from "@/lib/api";

export const HEALTH: Health = {
  status: "healthy",
  service: "AI Startup Co-Founder Team",
  reasoning: {
    adjustable: true,
    efforts: ["minimal", "low", "medium", "high"],
    specialist: "minimal",
    chief: "medium",
  },
  research: { providers: { azure: true, tavily: true }, default: "azure" },
  storage: { kind: "postgres", ok: true },
};

export const SCENARIOS: Scenario[] = [
  {
    name: "healthcare_scheduling",
    title: "Follow-up scheduling for small clinics",
    prompt: "Evaluate an assistant that schedules patient follow-ups.",
    context: { target_market: "Small clinics", constraints: "Under $15k", competitive_landscape: null },
    follow_up: "Refine the pricing strategy after financial review.",
  },
  {
    name: "gtm_risk",
    title: "Go-to-market risks for an expense tool",
    prompt: "Identify risks in our go-to-market plan.",
    context: null,
    follow_up: null,
  },
];

export const TEMPLATES: Template[] = [
  {
    name: "evaluate_idea",
    title: "Evaluate a new idea",
    summary: "Is it worth building, and how should it launch?",
    prompt: "Evaluate this startup idea: {idea}. It is for {customer}. Is it worth building, and how should we launch it?",
    fields: [
      { key: "idea", label: "The idea", placeholder: "An assistant for clinics", long: true },
      { key: "customer", label: "Who it is for", placeholder: "Small clinics", long: false },
    ],
    research: ["the market's size"],
    ask: ["the budget"],
  },
  {
    name: "pricing",
    title: "Set the price",
    summary: "What to charge, how to package it, and what it does to margins.",
    prompt: "Decide how to price {product} for {customer}.",
    fields: [
      { key: "product", label: "The product", placeholder: "", long: true },
      { key: "customer", label: "Who pays", placeholder: "", long: false },
    ],
    research: [],
    ask: [],
  },
];

// What preparing a brief gives back: three facts from two sources, and two questions.
export const PREPARED: PreparedBrief = {
  queries: ["clinic scheduling software market", "clinic scheduling software prices"],
  research: {
    findings: [
      { point: "About 147,000 office-based primary care physicians practised in 2019.", sources: [1] },
      { point: "Scheduling tools cost $20-$300 per provider a month in 2025.", sources: [2, 1] },
      { point: "Most small practices still book follow-ups by phone.", sources: [2] },
    ],
    sources: [
      { title: "Physician practice benchmark survey", url: "https://www.ama-assn.org/survey" },
      { title: "Scheduling software pricing", url: "https://prices.example.com/scheduling" },
    ],
  },
  research_note: null,
  questions: [
    {
      question: "What budget do you have to first launch?",
      why: "It decides whether a paid pilot is affordable.",
      suggestions: ["Under $15k", "$15k-$50k"],
    },
    { question: "Who is on the team?", why: "It sets what can be built in-house.", suggestions: ["Just me"] },
  ],
};

export const RESULT: EvaluateResponse = {
  session_id: "session-1234567890",
  objective: "Decide whether to launch a paid pilot.",
  assignments: { finance: "Price the pilot.", marketing: "Pick the first niche." },
  analyses: {
    finance: "Charge **$149** a month (assumption).",
    marketing: "Start with small clinics.",
  },
  // Each round carries the earlier reviews forward, as the backend does.
  review_history: [
    {
      finance: { approved: false, score: 3, feedback: "Show the break-even arithmetic." },
      marketing: { approved: true, score: 5, feedback: "" },
    },
    {
      finance: { approved: true, score: 4, feedback: "" },
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

// A session's deep research: two areas, one competitor, and one area Tavily could not research.
export const DEEP: DeepResearch = {
  areas: {
    finance: "Scheduling tools cost **$50** a month [2].",
    marketing: "Small clinics buy through state medical societies [1].",
  },
  companies: [
    {
      name: "Klara",
      summary: "Patient messaging for clinics.",
      pricing: "$15 per user a month [2]",
      customers: "219 practices [3]",
      funding: "",
      recent_moves: "",
      strengths: "Integrations with EHRs",
      weaknesses: "Fragmented pricing",
      sources: [2, 3],
    },
  ],
  sources: [
    { title: "Medical societies directory", url: "https://societies.example.com" },
    { title: "Scheduling prices 2026", url: "https://prices.example.com" },
    { title: "Klara profile", url: "https://klara.example.com" },
  ],
  credits: 102,
  searches: 0,
  providers: ["Tavily"],
  failed: ["risk"],
};

// The whole graph as /pipeline sends it (main.py's _diagram), for the live graph.
export const GRAPH = [
  "graph TD;",
  "\t__start__([start])",
  ...["plan", "research", "lookup", "review", "critique", "resolve", "synthesis", "marketing", "finance", "technical", "risk"].map(
    (node) => `\t${node}(${node})`,
  ),
  "\t__end__([end])",
  "\t__start__ --> plan;",
  "\tcritique --> resolve;",
  ...["marketing", "finance", "technical", "risk"].flatMap((name) => [
    `\t${name} -.-> critique;`,
    `\t${name} -.-> review;`,
    `\t${name} -.-> synthesis;`,
    `\tlookup -.-> ${name};`,
    `\tplan -.-> ${name};`,
    `\tresearch -.-> ${name};`,
    `\tresolve -.-> ${name};`,
    `\treview -.-> ${name};`,
  ]),
  "\tplan -.-> lookup;",
  "\tplan -.-> research;",
  "\tresolve -.-> synthesis;",
  "\treview -.-> critique;",
  "\treview -.-> synthesis;",
  "\tsynthesis --> __end__;",
].join("\n");

// How the backend describes the team (/pipeline).
export const PIPELINE: Pipeline = {
  mermaid: "graph TD;\n\t__start__([start])\n\tplan(plan)\n\t__start__ --> plan;",
  specialists: [
    { name: "marketing", title: "Marketing Strategy", focus: "customers, positioning, demand and go-to-market", reads_competitors: true },
    { name: "finance", title: "Financial Planning", focus: "costs, pricing, runway and break-even", reads_competitors: true },
    { name: "technical", title: "Technical Feasibility", focus: "architecture, build effort and technical risk", reads_competitors: false },
    { name: "risk", title: "Risk & Compliance", focus: "legal, regulatory and operational risk", reads_competitors: false },
  ],
  rules: {
    approval_score: 4,
    max_revisions: 1,
    max_critique_rounds: 1,
    report_words: 250,
    strategy_words: 500,
    max_questions: 3,
    max_facts: 8,
    max_competitors: 3,
  },
};

// What the API has done (/monitoring): two evaluations, one failed and another
// running, a warning in the last 15 minutes, and a short log.
export const MONITORING: Monitoring = {
  started_at: "2026-10-20T09:00:00Z",
  kept_in: "postgres",
  health: { status: "warnings", warnings: 1, errors: 0, minutes: 15 },
  running: 1,
  totals: {
    evaluations: 2,
    failures: 1,
    seconds: 157, // the finished evaluation's only
    calls: 22,
    tokens: 95000,
    reviewed: 4,
    approved: 3,
    conflicts: 2,
    searches: 42,
    credits: 0,
    briefs: 1,
    brief_failures: 0,
    proposals: 1,
    proposal_failures: 1,
    requests: 40,
    server_errors: 1,
    retries: 2,
    warnings: 1,
    errors: 0,
  },
  evaluation_seconds: { p50: 157, p95: 157, max: 157, samples: 1 },
  providers: [
    {
      provider: "azure",
      set_up: true,
      role: "the team's model, web search and dictation",
      status: "failing",
      services: [
        {
          service: "model",
          calls: 3,
          failed: 3,
          tokens_in: 0,
          tokens_out: 0,
          seconds: 1.2,
          credits: 0,
          last_at: "2026-10-20T09:04:00Z",
          last_failure: "401: Access denied due to invalid subscription key.",
          last_failure_at: "2026-10-20T09:04:00Z",
        },
      ],
    },
    { provider: "tavily", set_up: false, role: "web research", status: "not set up", services: [] },
    {
      provider: "fred",
      set_up: true,
      role: "official economic figures",
      status: "ready",
      services: [
        {
          service: "figures",
          calls: 2,
          failed: 0,
          tokens_in: 0,
          tokens_out: 0,
          seconds: 3.1,
          credits: 0,
          last_at: "2026-10-20T09:02:00Z",
          last_failure: null,
          last_failure_at: null,
        },
      ],
    },
  ],
  nodes: [
    { node: "synthesis", runs: 1, calls: 1, seconds: 19, tokens: 3400, p50: 19, p95: 19 },
    { node: "plan", runs: 2, calls: 3, seconds: 19, tokens: 2400, p50: 9.5, p95: 9.9 },
    { node: "finance", runs: 1, calls: 2, seconds: 30, tokens: 8000, p50: 30, p95: 30 },
  ],
  runs: [
    {
      session: "abcd1234", at: "2026-10-20T09:10:00Z", seconds: 3, ok: false, error: "The LLM call failed: timeout",
      specialists: [], calls: 0, tokens: 0, reviewed: 0, approved: 0, conflicts: 0, research: null, searches: 0, credits: 0, nodes: {},
    },
    {
      session: "efgh5678", at: "2026-10-20T09:05:00Z", seconds: 157, ok: true, error: null,
      specialists: ["marketing", "finance", "technical", "risk"], calls: 22, tokens: 95000, reviewed: 4, approved: 3,
      conflicts: 2, research: "Azure OpenAI", searches: 42, credits: 0, nodes: {},
    },
  ],
  events: [
    {
      at: "2026-10-20T09:10:00Z", kind: "warning", source: "main", message: "Evaluation failed on an LLM call: timeout",
      session: null, request: "3f2a9c1b7d4e5f60",
    },
    {
      at: "2026-10-20T09:05:00Z", kind: "run", source: "evaluate", message: "Finished in 157 s: 4 specialists.",
      session: "efgh5678", request: "a1b2c3d4e5f60718",
    },
    {
      at: "2026-10-20T09:04:00Z", kind: "done", source: "review", message: "Reviewed 4 reports: approved 3.",
      session: "efgh5678", request: "a1b2c3d4e5f60718",
    },
    { at: "2026-10-20T09:03:00Z", kind: "start", source: "finance", message: "Started.", session: "efgh5678", request: null },
  ],
};

// What /evaluate/stream reports for RESULT, step by step.
export const STEPS: Step[] = [
  { type: "start", node: "plan", at: 0.1 },
  {
    type: "done",
    node: "plan",
    at: 9.6,
    summary: "Planned the work and assigned Financial Planning and Marketing Strategy.",
    objective: "Decide whether to launch a paid pilot.",
    assigned: ["finance", "marketing"],
  },
  { type: "start", node: "finance", at: 9.7 },
  { type: "start", node: "marketing", at: 9.7 },
  { type: "done", node: "marketing", at: 27.2, summary: "Wrote its report (4 words).", words: 4, revision: false },
  { type: "done", node: "finance", at: 29.9, summary: "Wrote its report (6 words).", words: 6, revision: false },
  { type: "start", node: "review", at: 30.0 },
  { type: "done", node: "review", at: 41.0, summary: "Reviewed 2 reports: approved 1, sent back Financial Planning." },
  { type: "start", node: "finance", at: 41.1 },
  { type: "done", node: "finance", at: 58.4, summary: "Revised its report (6 words).", words: 6, revision: true },
  { type: "start", node: "review", at: 58.5 },
  { type: "done", node: "review", at: 66.0, summary: "Reviewed 1 report: approved 1." },
  { type: "start", node: "critique", at: 66.1 },
  { type: "done", node: "critique", at: 73.0, summary: "Cross-checked the reports and raised 1 conflict.", conflicts: 1 },
  { type: "start", node: "resolve", at: 73.1 },
  { type: "done", node: "resolve", at: 88.0, summary: "Settled 1 conflict; Marketing Strategy to revise." },
  { type: "start", node: "marketing", at: 88.1 },
  { type: "done", node: "marketing", at: 99.0, summary: "Revised its report (4 words).", revision: true },
  { type: "start", node: "synthesis", at: 99.1 },
  { type: "done", node: "synthesis", at: 117.0, summary: "Wrote the launch strategy (10 words).", words: 10 },
];

// The server-sent events of a stream: the steps, then the result or an error.
export function sse(steps: Step[], end: { result: unknown } | { error: { status: number; detail: string } } | null) {
  const events = steps.map(({ type, ...data }) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`);
  if (end && "result" in end) events.push(`event: result\ndata: ${JSON.stringify(end.result)}\n\n`);
  if (end && "error" in end) events.push(`event: error\ndata: ${JSON.stringify(end.error)}\n\n`);
  return events.join("");
}

// A stream the test feeds as it goes, to see the page while the team works.
export function liveStream() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(control) {
      controller = control;
    },
  });
  return {
    stream,
    send(text: string) {
      controller.enqueue(encoder.encode(text));
    },
    close() {
      controller.close();
    },
    fail() {
      controller.error(new TypeError("network error"));
    },
  };
}

export type Answer = {
  status?: number;
  body?: unknown;
  stream?: string | ReadableStream<Uint8Array>;
  headers?: Record<string, string>;
};
// A function answers each call afresh, from the body sent, and can hold the
// call open with a promise.
export type Answering = Answer | ((body: unknown) => Answer | Promise<Answer>);

// Like fetch, a call gives up when its signal aborts.
function abortable<T>(value: T | Promise<T>, signal?: AbortSignal | null): Promise<T> {
  if (!signal) return Promise.resolve(value);
  return new Promise((resolve, reject) => {
    const abort = () => reject(new DOMException("The operation was aborted.", "AbortError"));
    if (signal.aborted) return abort();
    signal.addEventListener("abort", abort, { once: true });
    Promise.resolve(value).then(resolve, reject);
  });
}

export function fakeBackend(overrides: Partial<Record<string, Answering>> = {}) {
  const sent: { path: string; body: unknown }[] = [];
  const answers: Record<string, Answering | undefined> = {
    "GET /health": { body: HEALTH },
    "GET /scenarios": { body: SCENARIOS },
    "GET /templates": { body: TEMPLATES },
    "POST /brief/prepare": { body: PREPARED },
    "GET /pipeline": { body: PIPELINE },
    "GET /monitoring": { body: MONITORING },
    "POST /evaluate": { body: RESULT },
    "POST /evaluate/stream": () => ({ stream: sse(STEPS, { result: RESULT }) }),
    ...overrides,
  };
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, "http://localhost").pathname.replace(/^\/api(?=\/)/, "");
    const key = `${init?.method ?? "GET"} ${path}`;
    // A JSON body is recorded parsed; a file (an upload) as it is.
    const request = typeof init?.body === "string" ? JSON.parse(init.body) : (init?.body ?? undefined);
    if (init?.body) sent.push({ path, body: request });
    const answer = answers[key];
    if (!answer) throw new TypeError("Failed to fetch");
    const answered = typeof answer === "function" ? answer(request) : answer;
    const { status = 200, body, stream, headers = {} } = await abortable(answered, init?.signal);
    if (stream !== undefined) {
      return new Response(stream, { status, headers: { "Content-Type": "text/event-stream", ...headers } });
    }
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
  });
  vi.stubGlobal("fetch", fetch);
  return { fetch, sent };
}

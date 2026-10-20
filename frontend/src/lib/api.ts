// Client for the FastAPI backend. The types mirror the request and response
// models in main.py and state.py; keep them in step.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Specialist = "marketing" | "finance" | "technical" | "risk";

// How hard a model reasons, least to most. The deployment also accepts
// "xhigh", but then does no reasoning at all, so the API does not offer it.
export const EFFORTS = ["minimal", "low", "medium", "high"] as const;
export type Effort = (typeof EFFORTS)[number];

// The efforts one request uses; a role left out keeps the configured effort.
export type Reasoning = { specialist?: Effort | null; chief?: Effort | null };

// A web page the research drew on, and one fact from it: `sources` number the
// pages it came from, 1 being the first in the research's `sources`.
export type Source = { title: string; url: string };
export type Finding = { point: string; sources: number[] };
export type Research = { findings: Finding[]; sources: Source[] };

// The founder's answer to one of the Chief of Staff's questions.
export type Answer = { question: string; answer: string };

// A competitor as Tavily's research found it; `sources` number the session's sources.
export type CompanyProfile = {
  name: string;
  summary: string;
  pricing: string;
  customers: string;
  funding: string;
  recent_moves: string;
  strengths: string;
  weaknesses: string;
  sources: number[];
};

// The session's deep research (deep_research.py): a report per specialist's
// area, the competitors, and every source, numbered once from 1 (the brief's
// research keeps its numbers); `failed` names what could not be researched.
export type DeepResearch = {
  areas: Partial<Record<Specialist, string>>;
  companies: CompanyProfile[];
  sources: Source[];
  // What it cost: Tavily credits, and the web searches Azure OpenAI ran; and who ran it.
  credits: number;
  searches: number;
  providers: string[];
  failed: string[];
};

export type RequestContext = {
  target_market?: string | null;
  constraints?: string | null;
  competitive_landscape?: string | null;
  // Set once the brief is prepared: they reach every agent.
  answers?: Answer[];
  research?: Research | null;
};

export type EvaluateRequest = {
  prompt: string;
  context?: RequestContext | null;
  // Pass the session_id of an earlier response to send a follow-up.
  session_id?: string | null;
  reasoning?: Reasoning | null;
  // Research each specialist's area and the main competitors on the web first.
  deep_research?: boolean;
  research_provider?: ResearchProvider | null;
};

export type ReviewResult = { approved: boolean; score: number; feedback: string };

export type Conflict = { raised_by: Specialist; about: Specialist; issue: string };

// `revise` is empty when no specialist had to change their report.
export type Resolution = { conflict: Conflict; decision: string; revise: Specialist | "" };

export type NodeMetric = { calls: number; seconds: number; tokens: number };

export type EvaluateResponse = {
  session_id: string;
  objective: string;
  assignments: Partial<Record<Specialist, string>>;
  analyses: Partial<Record<Specialist, string>>;
  review_history: Partial<Record<Specialist, ReviewResult>>[];
  resolutions: Resolution[];
  metrics: Record<string, NodeMetric>;
  final_strategy: string;
  research?: DeepResearch | null;
};

export type ReasoningSettings = {
  // Only Azure OpenAI takes a reasoning effort.
  adjustable: boolean;
  efforts: Effort[];
  // The configured defaults; null when none is set.
  specialist: Effort | null;
  chief: Effort | null;
};

// Where web research runs: Azure OpenAI's own web search (Bing, on the team's
// deployment), or Tavily, for demanding tasks.
export const RESEARCH_PROVIDERS = ["azure", "tavily"] as const;
export type ResearchProvider = (typeof RESEARCH_PROVIDERS)[number];
export const PROVIDER_NAMES: Record<ResearchProvider, string> = { azure: "Azure OpenAI", tavily: "Tavily" };

export type Health = {
  status: string;
  service: string;
  reasoning: ReasoningSettings;
  // Which research providers are set up, and the default (null with neither).
  research: { providers: Record<ResearchProvider, boolean>; default: ResearchProvider | null };
};

export type Scenario = {
  name: string;
  title: string;
  prompt: string;
  context: RequestContext | null;
  follow_up: string | null;
};

// A kind of decision to bring the team (templates/*.json): a brief with a
// {key} for each field to fill in.
export type TemplateField = { key: string; label: string; placeholder: string; long: boolean };
export type Template = {
  name: string;
  title: string;
  summary: string;
  prompt: string;
  fields: TemplateField[];
  research: string[];
  ask: string[];
};

// Something the Chief of Staff needs from the founder before the team starts.
export type Question = { question: string; why: string; suggestions: string[] };

// What preparing a brief gives back (brief.py): the searches run, the facts
// found with their sources, or why there are none, and the questions.
export type PreparedBrief = {
  queries: string[];
  // Who searched the web: "Azure OpenAI" or "Tavily"; null with no research.
  provider?: string | null;
  research: Research | null;
  research_note: string | null;
  questions: Question[];
};

export type PrepareRequest = {
  prompt: string;
  context?: RequestContext | null;
  template?: string | null;
  reasoning?: Reasoning | null;
  research_provider?: ResearchProvider | null;
};

// The backend could not be reached, or answered with an error.
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function errorMessage(response: Response): Promise<string> {
  // FastAPI sends {"detail": "..."}; a validation error sends a list of problems.
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((problem: { msg?: string }) => problem.msg ?? "Invalid request").join("; ");
  }
  return `HTTP ${response.status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(`Could not reach the backend at ${API_URL}.`);
  }
  if (!response.ok) {
    throw new ApiError(
      `The backend returned ${response.status}: ${await errorMessage(response)}`,
      response.status,
    );
  }
  return response.json() as Promise<T>;
}

export function getHealth(): Promise<Health> {
  return request("/health");
}

export function getScenarios(): Promise<Scenario[]> {
  return request("/scenarios");
}

export function getTemplates(): Promise<Template[]> {
  return request("/templates");
}

// About 20-30 s: the Chief of Staff plans the searches, Tavily runs them, and
// the Chief of Staff reads the results and checks the brief.
export function prepareBrief(body: PrepareRequest): Promise<PreparedBrief> {
  return request("/brief/prepare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// A full evaluation makes many LLM calls: about two minutes at the default
// reasoning efforts, 5 to 10 at "high".
export function evaluate(body: EvaluateRequest): Promise<EvaluateResponse> {
  return request("/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// One step of an evaluation, as /evaluate/stream reports it: an agent began
// (`start`) or finished (`done`, with what it did). `at` is seconds since the
// request began. The figures depend on the step (progress.py).
export type Step = {
  type: "start" | "done";
  node: string;
  at: number;
  summary?: string;
  objective?: string;
  assigned?: Specialist[];
  words?: number;
  revision?: boolean;
  failed?: boolean;
  reviews?: Partial<Record<Specialist, { approved: boolean; score: number }>>;
  conflicts?: number;
  decisions?: number;
  revise?: Specialist[];
  // The research step: what it covered, what it cost, and what it could not research.
  areas?: Specialist[];
  companies?: string[];
  credits?: number;
  searches?: number;
  provider?: string | null;
  not_researched?: string[];
};

function parseEvent(block: string): { name: string; data: Record<string, unknown> } | null {
  let name = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  return { name, data: JSON.parse(data) as Record<string, unknown> };
}

// Runs an evaluation like evaluate(), calling `onStep` as each agent begins and
// finishes, and resolving with the same result.
export async function evaluateStream(body: EvaluateRequest, onStep: (step: Step) => void): Promise<EvaluateResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/evaluate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(`Could not reach the backend at ${API_URL}.`);
  }
  if (!response.ok || !response.body) {
    throw new ApiError(`The backend returned ${response.status}: ${await errorMessage(response)}`, response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch {
      throw new ApiError("The connection to the backend was lost before the evaluation finished.");
    }
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, "\n");
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const event = parseEvent(buffer.slice(0, end));
      buffer = buffer.slice(end + 2);
      if (!event) continue;
      if (event.name === "result") return event.data as unknown as EvaluateResponse;
      if (event.name === "error") {
        const status = Number(event.data.status) || null;
        throw new ApiError(`The backend returned ${status}: ${String(event.data.detail)}`, status);
      }
      if (event.name === "start" || event.name === "done") {
        onStep({ ...(event.data as Omit<Step, "type">), type: event.name });
      }
    }
  }
  throw new ApiError("The connection to the backend was lost before the evaluation finished.");
}

// ---- How it works (main.py's /pipeline, monitor.py) ----

// The team as the code runs it: the graph as Mermaid, the specialists, and the
// rules the Chief of Staff decides by.
export type Pipeline = {
  mermaid: string;
  specialists: { name: Specialist; title: string; focus: string; reads_competitors: boolean }[];
  rules: {
    approval_score: number;
    max_revisions: number;
    max_critique_rounds: number;
    report_words: number;
    strategy_words: number;
    max_questions: number;
    max_facts: number;
    max_competitors: number;
  };
};

export type MonitorEvent = {
  at: string;
  kind: "start" | "done" | "run" | "brief" | "proposal" | "warning" | "error";
  source: string;
  message: string;
  session: string | null;
};

export type MonitorRun = {
  session: string;
  at: string;
  seconds: number;
  ok: boolean;
  error: string | null;
  specialists: Specialist[];
  calls: number;
  tokens: number;
  reviewed: number;
  approved: number;
  conflicts: number;
  research: string | null;
  searches: number;
  credits: number;
  nodes: Record<string, NodeMetric>;
};

export type NodeStats = { node: string; runs: number; calls: number; seconds: number; tokens: number };

// What the API has done since it started (kept in memory).
export type Monitoring = {
  started_at: string;
  totals: {
    evaluations: number;
    failures: number;
    seconds: number;
    calls: number;
    tokens: number;
    reviewed: number;
    approved: number;
    conflicts: number;
    searches: number;
    credits: number;
    briefs: number;
    proposals: number;
  };
  nodes: NodeStats[];
  runs: MonitorRun[];
  events: MonitorEvent[];
};

export function getPipeline(): Promise<Pipeline> {
  return request("/pipeline");
}

export function getMonitoring(): Promise<Monitoring> {
  return request("/monitoring");
}

// ---- Reports (reports.py, proposal.py) ----

export type ReportSection = { key: string; title: string; body: string };

export type ReportSummary = {
  session_id: string;
  title: string;
  version: number;
  has_proposal: boolean;
  edited: boolean;
  outdated: boolean;
  updated_at: string;
};

export type Level = "Low" | "Medium" | "High";
export type MarketSize = { value_usd: number; basis: string };
export type Competitor = {
  name: string;
  kind: "Direct" | "Indirect";
  market_share: string;
  strengths: string;
  weaknesses: string;
};
export type Channel = { channel: string; approach: string; monthly_budget_usd: number };
export type FunnelStage = { stage: string; monthly_volume: number };
export type MarketPlan = {
  personas: string;
  tam: MarketSize;
  sam: MarketSize;
  som: MarketSize;
  competitors: Competitor[];
  value_proposition: string;
  channels: Channel[];
  pricing_strategy: string;
  funnel: FunnelStage[];
};
export type Phase = { name: string; start_month: number; duration_months: number; deliverables: string };
export type StaffLine = { role: string; count: number; timing: string };
export type TechnicalPlan = {
  infrastructure: string;
  stack: string;
  scalability: string;
  roadmap: Phase[];
  staffing: StaffLine[];
};
export type RiskItem = {
  category: "Technical" | "Financial" | "Marketing" | "Regulatory" | "Operational";
  description: string;
  probability: Level;
  impact: Level;
  mitigation: string;
};
export type RiskPlan = { data_protection: string; compliance: string; risks: RiskItem[] };
export type CostLine = { item: string; amount_usd: number };
export type YearProjection = {
  year: number;
  customers: number;
  average_customers: number;
  one_off_revenue_usd: number;
  fixed_costs_month_usd: number;
  cac_usd: number;
};
export type FinancialPlan = {
  capex: CostLine[];
  monthly_opex: CostLine[];
  projections: YearProjection[];
  price_per_customer_month_usd: number;
  variable_cost_per_customer_month_usd: number;
  discount_rate: number;
  assumptions: string;
};
export type Kpi = { category: "Financial" | "Technical" | "Marketing"; metric: string; target: string };
export type ExecutivePlan = {
  project_name: string;
  verdict: "Go" | "Go with conditions" | "Not yet";
  recommendation: string;
  overview: string;
  opportunity: string;
  strategic_alignment: string;
  financial_case: string;
  kpis: Kpi[];
};
export type Proposal = {
  executive: ExecutivePlan;
  market: MarketPlan;
  technical: TechnicalPlan;
  risk: RiskPlan;
  financial: FinancialPlan;
};
export type PartKey = keyof Proposal;

// Calculated by the API from the financial plan (proposal.investment_metrics).
export type InvestmentMetrics = {
  capex_usd: number;
  monthly_fixed_costs_usd: number;
  revenue_usd: number[];
  opex_usd: number[];
  net_cash_flow_usd: number[];
  net_margin: (number | null)[];
  npv_usd: number;
  irr: number | null;
  payback_months: number | null;
  break_even_customers: number | null;
};

export type Report = {
  session_id: string;
  title: string;
  objective: string;
  context: string;
  sections: ReportSection[];
  version: number;
  proposal: Proposal | null;
  edited: boolean;
  outdated: boolean;
  updated_at: string;
  investment: InvestmentMetrics | null;
  // Where the proposal's figures disagree, worked out by the API.
  checks: string[];
};

export type ProposalResult = { report: Report; failed: string[] };

function send<T>(method: "POST" | "PUT", path: string, body?: unknown): Promise<T> {
  return request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const reportPath = (sessionId: string) => `/reports/${encodeURIComponent(sessionId)}`;

export function listReports(): Promise<ReportSummary[]> {
  return request("/reports");
}

export function getReport(sessionId: string): Promise<Report> {
  return request(reportPath(sessionId));
}

// Saves edited sections of the team's report; a 409 means the report changed
// since `version`.
export function saveReport(sessionId: string, version: number, sections: ReportSection[]): Promise<Report> {
  return send("PUT", reportPath(sessionId), { version, sections });
}

export function resetReport(sessionId: string): Promise<Report> {
  return send("POST", `${reportPath(sessionId)}/reset`);
}

// The agents write the proposal: about one to two minutes at the default efforts.
export function writeProposal(sessionId: string, version: number, reasoning: Reasoning | null): Promise<ProposalResult> {
  return send("POST", `${reportPath(sessionId)}/proposal`, { version, reasoning });
}

// Applies an instruction to one part (all of them when `part` is null).
export function reviseProposal(
  sessionId: string,
  version: number,
  instruction: string,
  part: PartKey | null,
  reasoning: Reasoning | null,
): Promise<ProposalResult> {
  return send("POST", `${reportPath(sessionId)}/proposal/revise`, { version, instruction, part, reasoning });
}

export function saveProposal(sessionId: string, version: number, proposal: Proposal): Promise<Report> {
  return send("PUT", `${reportPath(sessionId)}/proposal`, { version, proposal });
}

export async function reportPdf(sessionId: string): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${reportPath(sessionId)}/pdf`);
  } catch {
    throw new ApiError(`Could not reach the backend at ${API_URL}.`);
  }
  if (!response.ok) {
    throw new ApiError(`The backend returned ${response.status}: ${await errorMessage(response)}`, response.status);
  }
  return response.blob();
}

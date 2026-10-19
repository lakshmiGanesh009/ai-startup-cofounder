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

export type RequestContext = {
  target_market?: string | null;
  constraints?: string | null;
  competitive_landscape?: string | null;
};

export type EvaluateRequest = {
  prompt: string;
  context?: RequestContext | null;
  // Pass the session_id of an earlier response to send a follow-up.
  session_id?: string | null;
  reasoning?: Reasoning | null;
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
};

export type ReasoningSettings = {
  // Only Azure OpenAI takes a reasoning effort.
  adjustable: boolean;
  efforts: Effort[];
  // The configured defaults; null when none is set.
  specialist: Effort | null;
  chief: Effort | null;
};

export type Health = { status: string; service: string; reasoning: ReasoningSettings };

export type Scenario = {
  name: string;
  prompt: string;
  context: RequestContext | null;
  follow_up: string | null;
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

// A full evaluation makes many LLM calls: about two minutes at the default
// reasoning efforts, 5 to 10 at "high".
export function evaluate(body: EvaluateRequest): Promise<EvaluateResponse> {
  return request("/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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

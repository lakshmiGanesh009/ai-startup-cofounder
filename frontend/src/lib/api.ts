// Client for the FastAPI backend. The types mirror the request and response
// models in main.py and state.py; keep them in step.
//
// The browser calls the API through this app's own server (app/api/[...path]/
// route.ts), which adds the API's key, so the key never reaches the browser.
export const API_URL = "/api";
const UNREACHABLE = "Could not reach this app's server; check the connection.";

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
  // What its own pricing page says, read through Tavily's MCP server, citing it.
  site?: string;
  sources: number[];
};

// One official figure from FRED (lookups.py): its latest value, and how it
// moved over the year, worked out by the API.
export type Figure = {
  id: string;
  title: string;
  units: string;
  frequency: string;
  date: string;
  value: number;
  year_ago: number | null;
  change: string;
  why: string;
  link: string;
};

// The official figures a session looked up on FRED, and why any are missing.
export type EconomicData = { figures: Figure[]; searches: string[]; note: string | null };

// Text that tried to instruct the agents (guardrails.py): the founder's or a web
// page's. It was cut out of what the agents read, and the founder is told.
export type GuardrailFlag = { origin: "founder" | "web"; source: string; kind: string; excerpt: string };

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
  flags?: GuardrailFlag[];
};

export type RequestContext = {
  target_market?: string | null;
  constraints?: string | null;
  competitive_landscape?: string | null;
  // The founder's documents, by id: files uploaded (uploadFile) and earlier
  // reports (their session ids). Each agent reads the passages on its work.
  uploads?: string[];
  reports?: string[];
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
  economic?: EconomicData | null;
  guardrails?: GuardrailFlag[];
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
  // Where sessions and reports are kept, and whether it answers ("degraded" status when not).
  storage: { kind: "memory" | "postgres"; ok: boolean };
  // Look-ups through MCP servers: FRED's figures, and competitors' own pages (on Tavily).
  lookups?: { fred: boolean; competitor_pages: boolean };
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
  guardrails?: GuardrailFlag[];
};

export type PrepareRequest = {
  prompt: string;
  context?: RequestContext | null;
  template?: string | null;
  reasoning?: Reasoning | null;
  research_provider?: ResearchProvider | null;
};

// The backend could not be reached, or answered with an error. `requestId` is
// the X-Request-ID the backend answered with: its logs name the request by it.
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null = null,
    readonly requestId: string | null = null,
    // What the API said was wrong, on its own: "The file is empty."
    readonly detail: string = message,
  ) {
    super(requestId ? `${message} (request ${requestId})` : message);
    this.name = "ApiError";
  }
}

async function failure(response: Response): Promise<ApiError> {
  const detail = await errorMessage(response);
  return new ApiError(
    `The backend returned ${response.status}: ${detail}`,
    response.status,
    response.headers.get("X-Request-ID"),
    detail,
  );
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
    throw new ApiError(UNREACHABLE);
  }
  if (!response.ok) throw await failure(response);
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

// Today's rates from a currency to the app's others: the ECB's reference rates,
// with the pegged dirham and riyal worked out from the dollar's.
export type Rates = { base: string; date: string; source: string; rates: Record<string, number>; pegged: string[] };

export function getRates(base: string): Promise<Rates> {
  return request(`/rates/${encodeURIComponent(base)}`);
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
  // The look-up step: the FRED series read, and what the Chief of Staff searched for.
  figures?: string[];
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
    throw new ApiError(UNREACHABLE);
  }
  if (!response.ok || !response.body) throw await failure(response);
  const requestId = response.headers.get("X-Request-ID");
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
        throw new ApiError(`The backend returned ${status}: ${String(event.data.detail)}`, status, requestId);
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
  kind: "start" | "done" | "run" | "brief" | "proposal" | "document" | "warning" | "error" | "system";
  source: string;
  message: string;
  session: string | null;
  // The request it happened in: its X-Request-ID, also on every log line.
  request: string | null;
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

// A step of the graph over the evaluations that finished: its totals, and the
// median (p50) and 95th percentile of its time in one evaluation.
export type NodeStats = {
  node: string;
  runs: number;
  calls: number;
  seconds: number;
  tokens: number;
  p50: number;
  p95: number;
};

// Whether anything went wrong in the last `minutes`: an error, or only warnings
// (a model call Azure made the client retry among them).
export type MonitorHealth = {
  status: "healthy" | "warnings" | "errors";
  warnings: number;
  errors: number;
  minutes: number;
};

// What the API has done. The statistics count since it started: the time,
// calls and costs are the finished evaluations', and `requests` leaves out
// polled routes. The latest runs and events are history, which survives a
// restart when it is kept in PostgreSQL.
export type Monitoring = {
  started_at: string;
  kept_in: "memory" | "postgres";
  health: MonitorHealth;
  running: number;
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
    brief_failures: number;
    proposals: number;
    proposal_failures: number;
    requests: number;
    server_errors: number;
    retries: number;
    warnings: number;
    errors: number;
  };
  // How long the latest finished evaluations took, in seconds.
  evaluation_seconds: { p50: number; p95: number; max: number; samples: number } | null;
  nodes: NodeStats[];
  runs: MonitorRun[];
  events: MonitorEvent[];
};

export function getPipeline(): Promise<Pipeline> {
  return request("/pipeline");
}

export function getMonitoring(signal?: AbortSignal): Promise<Monitoring> {
  return request("/monitoring", { signal });
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
export type MarketSize = { value: number; basis: string };
export type Competitor = {
  name: string;
  kind: "Direct" | "Indirect";
  market_share: string;
  strengths: string;
  weaknesses: string;
};
export type Channel = { channel: string; approach: string; monthly_budget: number };
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
export type CostLine = { item: string; amount: number };
export type YearProjection = {
  year: number;
  customers: number;
  average_customers: number;
  one_off_revenue: number;
  fixed_costs_month: number;
  cac: number;
};
export type FinancialPlan = {
  capex: CostLine[];
  monthly_opex: CostLine[];
  projections: YearProjection[];
  price_per_customer_month: number;
  variable_cost_per_customer_month: number;
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
  capex: number;
  monthly_fixed_costs: number;
  revenue: number[];
  opex: number[];
  net_cash_flow: number[];
  net_margin: (number | null)[];
  npv: number;
  irr: number | null;
  payback_months: number | null;
  break_even_customers: number | null;
};

// Set once for the whole document and applied by code (document.py): the
// currency of every amount, the system its measurements were last converted
// to, who it is from, and the team report's sections left out.
export type DocumentSettings = {
  currency: string;
  units: "metric" | "imperial" | null;
  prepared_by: string;
  hidden: string[];
};

export type Report = {
  session_id: string;
  title: string;
  objective: string;
  context: string;
  sections: ReportSection[];
  version: number;
  proposal: Proposal | null;
  settings: DocumentSettings;
  // How this version came about, for the history.
  change: string | null;
  // The founder's documents its run worked from, by id.
  worked_from?: WorkedFrom;
  edited: boolean;
  outdated: boolean;
  updated_at: string;
  investment: InvestmentMetrics | null;
  // Where the proposal's figures disagree, worked out by the API.
  checks: string[];
};

export type WorkedFrom = { uploads: string[]; reports: string[] };

export type ProposalResult = { report: Report; failed: string[]; guardrails?: GuardrailFlag[] };

// What the founder can change in a report and save together.
export type ReportContent = Pick<Report, "title" | "objective" | "sections" | "proposal" | "settings">;

// One field a change touches: where, for a person, and its value before and after.
export type FieldChange = {
  path: string;
  label: string;
  before: string | number | null;
  after: string | number | null;
  // A figure in the document's currency.
  money: boolean;
};

// A report as a change would leave it, saved only if accepted.
export type Draft = { report: Report; changes: FieldChange[]; summary: string; base_version: number };

export type RevisionResult = { draft: Draft; failed: string[]; guardrails?: GuardrailFlag[] };

// The changes code makes exactly (document.py).
export type DraftChange =
  | { kind: "currency"; to: string; rate: number; relabel?: boolean }
  | { kind: "units"; to: "metric" | "imperial" }
  | { kind: "replace"; find: string; by: string; match_case?: boolean; whole_words?: boolean }
  | { kind: "redact"; terms: string[] }
  | { kind: "remove"; path: string; passage: string }
  | { kind: "settings"; prepared_by: string; hidden: string[] };

export type VersionSummary = {
  version: number;
  updated_at: string;
  change: string | null;
  has_proposal: boolean;
  current: boolean;
};

export function contentOf(report: Report): ReportContent {
  const { title, objective, sections, proposal, settings } = report;
  return { title, objective, sections, proposal, settings };
}

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

// The agents write the proposal, in `currency` if given: about one to two
// minutes at the default efforts.
export function writeProposal(
  sessionId: string,
  version: number,
  reasoning: Reasoning | null,
  currency?: string,
): Promise<ProposalResult> {
  return send("POST", `${reportPath(sessionId)}/proposal`, { version, reasoning, currency });
}

// Applies an instruction to one part (all of them when `part` is null), as a
// draft to accept or discard.
export function reviseProposal(
  sessionId: string,
  version: number,
  instruction: string,
  part: PartKey | null,
  reasoning: Reasoning | null,
): Promise<RevisionResult> {
  return send("POST", `${reportPath(sessionId)}/proposal/revise`, { version, instruction, part, reasoning });
}

// One text of the report, or a passage of it, rewritten by the agent who wrote
// it, as a draft; everything else is left alone.
export function reviseText(
  sessionId: string,
  version: number,
  path: string,
  instruction: string,
  passage: string | null,
  reasoning: Reasoning | null,
): Promise<RevisionResult> {
  return send("POST", `${reportPath(sessionId)}/revise`, { version, path, instruction, passage, reasoning });
}

// A change code makes exactly, as a draft to preview.
export function makeDraft(sessionId: string, version: number, change: DraftChange): Promise<Draft> {
  return send("POST", `${reportPath(sessionId)}/drafts`, { version, change });
}

// Saves a draft; a 409 means the report changed since the draft was made.
export function acceptDraft(sessionId: string, draft: Draft): Promise<Report> {
  return send("POST", `${reportPath(sessionId)}/accept`, {
    version: draft.base_version,
    content: contentOf(draft.report),
    change: draft.summary,
  });
}

export function listVersions(sessionId: string): Promise<VersionSummary[]> {
  return request(`${reportPath(sessionId)}/versions`);
}

export function getVersion(sessionId: string, version: number): Promise<Report> {
  return request(`${reportPath(sessionId)}/versions/${version}`);
}

// Makes an earlier version the newest; `current` is the report's version now.
export function restoreVersion(sessionId: string, current: number, version: number): Promise<Report> {
  return send("POST", `${reportPath(sessionId)}/versions/${version}/restore`, { version: current });
}

export function saveProposal(sessionId: string, version: number, proposal: Proposal): Promise<Report> {
  return send("PUT", `${reportPath(sessionId)}/proposal`, { version, proposal });
}

// The report as a PDF; with `content`, a draft or an earlier version, unsaved.
export async function reportPdf(sessionId: string, content?: ReportContent): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(
      `${API_URL}${reportPath(sessionId)}/pdf`,
      content
        ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(content) }
        : undefined,
    );
  } catch {
    throw new ApiError(UNREACHABLE);
  }
  if (!response.ok) throw await failure(response);
  return response.blob();
}

// ---- The founder's documents (library.py, extract.py) ----

// What was read of an uploaded file: only its text is kept, as passages.
export type UploadSummary = {
  id: string;
  name: string;
  kind: string;
  parts: string;
  size: number;
  characters: number;
  warnings: string[];
  preview: string;
};

export type UploadResult = { upload: UploadSummary; guardrails?: GuardrailFlag[] };

// The formats the API reads, told from the content; for the file picker.
export const UPLOAD_TYPES =
  ".pdf,.docx,.pptx,.xlsx,.odt,.ods,.odp,.csv,.tsv,.rtf,.html,.htm,.md,.markdown,.txt";
export const MAX_UPLOAD_BYTES = 10_000_000;

export function uploadFile(file: File): Promise<UploadResult> {
  return request(`/uploads?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
  });
}

export function getUpload(id: string): Promise<UploadSummary> {
  return request(`/uploads/${encodeURIComponent(id)}`);
}

// A passage an answer cites, by its mark: "[D1 · page 3]", "[R1 · Launch Strategy]".
export type Cited = { mark: string; name: string; where: string; text: string };

export type AskResult = { answer: string; sources: Cited[]; guardrails?: GuardrailFlag[] };

// The Chief of Staff answers from the documents' passages alone: about 10-20 s.
export function ask(
  question: string,
  uploads: string[],
  reports: string[],
  reasoning: Reasoning | null = null,
): Promise<AskResult> {
  return send("POST", "/ask", { question, uploads, reports, reasoning });
}

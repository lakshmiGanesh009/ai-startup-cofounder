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

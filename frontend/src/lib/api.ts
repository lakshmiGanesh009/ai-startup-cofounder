// Client for the FastAPI backend. The types mirror EvaluateRequest and
// EvaluateResponse in main.py and the models in state.py; keep them in step.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Specialist = "marketing" | "finance" | "technical" | "risk";

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

export type Health = { status: string; service: string };

async function errorMessage(response: Response): Promise<string> {
  // FastAPI sends {"detail": "..."} for errors; validation errors carry a list.
  const body = await response.json().catch(() => null);
  return typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`;
}

export async function getHealth(): Promise<Health> {
  const response = await fetch(`${API_URL}/health`);
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

// A full evaluation makes many LLM calls and can take a minute or more.
export async function evaluate(request: EvaluateRequest): Promise<EvaluateResponse> {
  const response = await fetch(`${API_URL}/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

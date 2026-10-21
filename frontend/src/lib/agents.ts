// The team as the UI draws it: each agent's name, role and colour (its class in
// globals.css), and which agent does each step of the graph, writes each part
// of the proposal and each section of the report. Web research is a tool the
// team uses, drawn like an agent in a neutral colour.

import type { PartKey, Specialist } from "@/lib/api";

export type AgentKey = "chief" | "marketing" | "finance" | "technical" | "risk" | "research";

export type Agent = { key: AgentKey; name: string; short: string; role: string };

export const AGENTS: Record<AgentKey, Agent> = {
  chief: { key: "chief", name: "Chief of Staff", short: "Chief of Staff", role: "Plans, reviews, settles conflicts, decides" },
  marketing: { key: "marketing", name: "Marketing Strategy", short: "Marketing", role: "Market, customers, channels, pricing" },
  finance: { key: "finance", name: "Financial Planning", short: "Finance", role: "Costs, revenue, runway, returns" },
  technical: { key: "technical", name: "Technical Feasibility", short: "Technical", role: "Architecture, build, team, timeline" },
  risk: { key: "risk", name: "Risk & Compliance", short: "Risk", role: "Regulation, data protection, risks" },
  research: { key: "research", name: "Web research", short: "Web", role: "Searches the web for the team" },
};

// The Chief of Staff, then the specialists in the order the app lists them.
export const TEAM: AgentKey[] = ["chief", "marketing", "finance", "technical", "risk"];

export const SPECIALIST_AGENTS: AgentKey[] = ["marketing", "finance", "technical", "risk"];

export function isAgent(key: string): key is AgentKey {
  return key in AGENTS;
}

// The class that gives an element its agent's colours.
export function agentClass(key: AgentKey): string {
  return `agent-${key}`;
}

// Who does a step of the graph. The cross-check is the specialists' (each
// critiques the others); the Chief of Staff's own steps are its.
export function agentsOf(node: string): AgentKey[] {
  if (isAgent(node)) return [node];
  if (node === "critique") return SPECIALIST_AGENTS;
  return ["chief"];
}

export function agentOf(node: string): AgentKey {
  return agentsOf(node)[0];
}

// The steps and runs the agents do, as the Monitor names its sources.
const AGENT_SOURCES = new Set([
  "plan", "research", "marketing", "finance", "technical", "risk",
  "review", "critique", "resolve", "synthesis", "evaluate", "brief", "proposal",
]);

// The agents behind a source of the Monitor's events; none for the API's own.
export function agentsOfSource(source: string): AgentKey[] {
  return AGENT_SOURCES.has(source) ? agentsOf(source) : [];
}

// A bar's fill for a step: its agent's colour, or the colours of several.
export function agentFill(agents: AgentKey[]): string {
  if (agents.length === 1) return `var(--agent-${agents[0]})`;
  const share = 100 / agents.length;
  const stops = agents.map((agent, i) => `var(--agent-${agent}) ${i * share}% ${(i + 1) * share}%`);
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}

// The specialist behind a key the API uses for one ("marketing", ...).
export function specialistAgent(name: Specialist | string): AgentKey {
  return isAgent(name) ? name : "chief";
}

// Who writes each part of the investment proposal.
export const PART_AGENT: Record<PartKey, AgentKey> = {
  executive: "chief",
  market: "marketing",
  technical: "technical",
  risk: "risk",
  financial: "finance",
};

// Who wrote each section of the team's report, by its key.
export const SECTION_AGENT: Record<string, AgentKey> = {
  strategy: "chief",
  decisions: "chief",
  marketing: "marketing",
  finance: "finance",
  technical: "technical",
  risk: "risk",
  research: "research",
};

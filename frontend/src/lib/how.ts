// What the How it works page explains: the steps from a brief to a decision,
// who reads and writes what, where the founder's judgement matters, the stack,
// and two of its diagrams. The numbers come from the backend (/pipeline), so
// the page says what the code does.

import type { Pipeline } from "@/lib/api";

export type IconName =
  | "user"
  | "search"
  | "compass"
  | "globe"
  | "team"
  | "scale"
  | "swap"
  | "gavel"
  | "document";

export type Station = {
  key: string;
  title: string;
  who: string;
  makes: string;
  icon: IconName;
  // A step the founder can skip, and one where the founder decides.
  optional?: boolean;
  yours?: boolean;
  // The section of the page that explains it.
  more: string;
};

// From a brief to a decision, as the graph runs it (graph.py) with the steps around it.
export const STATIONS: Station[] = [
  { key: "brief", title: "Brief", who: "You", makes: "brief · context", icon: "user", yours: true, more: "user-flow" },
  {
    key: "prepare",
    title: "Prepare",
    who: "Chief of Staff, on the web",
    makes: "facts [n] · questions",
    icon: "search",
    optional: true,
    yours: true,
    more: "research",
  },
  { key: "plan", title: "Plan", who: "Chief of Staff", makes: "objective · tasks", icon: "compass", more: "decisions" },
  {
    key: "research",
    title: "Research",
    who: "Azure OpenAI or Tavily",
    makes: "area reports · competitors",
    icon: "globe",
    optional: true,
    more: "research",
  },
  { key: "reports", title: "Reports", who: "4 specialists at once", makes: "four reports", icon: "team", more: "team" },
  { key: "review", title: "Review", who: "Chief of Staff", makes: "scores · revisions", icon: "scale", more: "decisions" },
  { key: "cross-check", title: "Cross-check", who: "Specialists", makes: "conflicts", icon: "swap", more: "critique" },
  { key: "resolve", title: "Resolve", who: "Chief of Staff", makes: "decisions", icon: "gavel", more: "critique" },
  {
    key: "strategy",
    title: "Strategy",
    who: "Chief of Staff, then you",
    makes: "memo · report · PDF",
    icon: "document",
    yours: true,
    more: "judgement",
  },
];

// Who reads (r) and writes (w) each part of the shared state, step by step.
// LangGraph keeps it per session, so a follow-up starts from it.
export const STEPS = ["Prepare", "Plan", "Research", "Specialists", "Review", "Cross-check", "Resolve", "Strategy"];

export const STATE: { field: string; about: string; cells: ("r" | "w" | "")[] }[] = [
  { field: "Brief and context", about: "your words, market, constraints", cells: ["r", "r", "r", "r", "r", "", "r", "r"] },
  { field: "Answers and web facts", about: "what you told it, facts with [n]", cells: ["w", "r", "r", "r", "r", "", "r", "r"] },
  { field: "Objective and tasks", about: "the decision, one task each", cells: ["", "w", "r", "r", "r", "", "r", "r"] },
  { field: "Deep research", about: "a report per area, competitors", cells: ["", "", "w", "r", "", "", "", ""] },
  { field: "Reports", about: "one per specialist", cells: ["", "", "", "w", "r", "r", "r", "r"] },
  { field: "Reviews", about: "score, verdict, feedback", cells: ["", "", "", "r", "w", "", "", ""] },
  { field: "Conflicts", about: "who questions whom, and why", cells: ["", "", "", "", "", "w", "r", ""] },
  { field: "Decisions", about: "how each conflict is settled", cells: ["", "", "", "r", "", "", "w", "r"] },
  { field: "Launch strategy", about: "the memo", cells: ["", "", "", "", "", "", "", "w"] },
  { field: "Metrics", about: "calls, seconds, tokens", cells: ["", "w", "w", "w", "w", "w", "w", "w"] },
];

// Where the founder's judgement matters most.
export const JUDGEMENT: { title: string; why: string; where: string }[] = [
  {
    title: "Your brief and your answers",
    why: "Only you know the budget, the team, the runway and what you will risk. Leave a question unanswered and the team assumes.",
    where: "The brief, Before the team starts",
  },
  {
    title: "The facts you keep",
    why: "Web sources disagree, sometimes a thousandfold: one run found a $4.4 trillion and a $46 billion outpatient market. Leave out what does not fit your case.",
    where: "Before the team starts",
  },
  {
    title: "Reports that were not approved",
    why: "A report still below the bar after its one revision goes on to the strategy, marked. Read it with care before you rely on it.",
    where: "The result's reviews",
  },
  {
    title: "How conflicts were settled",
    why: "A model decides between your specialists. Check each decision against your own priorities; you may weigh them differently.",
    where: "The Conflicts tab",
  },
  {
    title: "Assumptions and figures",
    why: "Figures marked (assumption) are estimates. The proposal's NPV, IRR and payback are calculated from Finance's drivers, so they are only as good as the drivers.",
    where: "Reports, the financial plan",
  },
  {
    title: "What leaves your hands",
    why: "Edit the report, ask the team to revise the proposal, and read the PDF before you share it. Nothing is sent anywhere until you do.",
    where: "Reports, Open PDF",
  },
  {
    title: "Text that tried to instruct the team",
    why: "The agents read your text and every web page as material, never as orders, and a notice names any that tried to give them instructions. Check what it touched: a page that tries this may also be lying.",
    where: "The brief's review, the result, the PDF's changes",
  },
  {
    title: "What you send to the web",
    why: "Research sends your brief's searches to Bing or Tavily, outside your Azure boundary. Keep patient data and confidential numbers out of the brief.",
    where: "The sidebar's Web research",
  },
];

export type LayerIcon =
  | "window"
  | "server"
  | "flow"
  | "team"
  | "spark"
  | "globe"
  | "document"
  | "state"
  | "shield"
  | "pulse"
  | "check";

// The stack, by layer, and what each part does here.
export const STACK: { layer: string; icon: LayerIcon; tools: string[]; does: string }[] = [
  {
    layer: "Your browser",
    icon: "window",
    tools: ["Next.js 16", "React 19", "Tailwind CSS 4", "Mermaid"],
    does: "These pages; the team's progress as it streams in; these diagrams.",
  },
  {
    layer: "API",
    icon: "server",
    tools: ["FastAPI", "Uvicorn", "Server-sent events", "Pydantic"],
    does: "Every request and its validation; /evaluate/stream reports each step as it finishes.",
  },
  {
    layer: "Orchestration",
    icon: "flow",
    tools: ["LangGraph StateGraph", "Conditional edges", "PostgreSQL checkpointer"],
    does: "The graph: specialists in parallel, the routes the Chief of Staff's decisions take, and each session's state.",
  },
  {
    layer: "Agents",
    icon: "team",
    tools: ["LangChain", "Structured outputs"],
    does: "Every decision is a typed object: the plan, a review, a conflict, a decision, a proposal part.",
  },
  {
    layer: "Model",
    icon: "spark",
    tools: ["Azure OpenAI", "gpt-5-mini", "Reasoning effort"],
    does: "Every agent's thinking, at the effort the sidebar's sliders set for each role.",
  },
  {
    layer: "Research",
    icon: "globe",
    tools: ["Azure OpenAI web search (Bing)", "Tavily Search", "Tavily Research"],
    does: "Facts for the brief and deep research for each specialist, cited by number.",
  },
  {
    layer: "Documents",
    icon: "document",
    tools: ["fpdf2", "Calculated metrics"],
    does: "The PDF with its charts; revenue, NPV, IRR and payback calculated in code, not by the model.",
  },
  {
    layer: "Storage",
    icon: "state",
    tools: ["PostgreSQL", "psycopg", "Migrations"],
    does: "Sessions, reports and the Monitor's history, so a restart loses none of them; in memory without a database.",
  },
  {
    layer: "Security",
    icon: "shield",
    tools: ["API key, held by the app's server", "Rate and size limits", "A cap on runs", "Security headers", "Prompt guardrails"],
    does: "Only callers with the key reach the API, and the browser never holds it; no caller can exhaust the API or the model; your text and the web's are read as material, never obeyed.",
  },
  {
    layer: "Observability",
    icon: "pulse",
    tools: ["Request IDs", "JSON logs", "Prometheus", "The Monitor"],
    does: "An ID on every request, its log lines and its errors; metrics at /metrics for Prometheus; the Monitor tab.",
  },
  {
    layer: "Checks",
    icon: "check",
    tools: ["pytest", "Vitest", "Testing Library", "Headless Chrome"],
    does: "Tests on a fake model and a fake backend, and live runs read screen by screen.",
  },
];

// The founder's path through the app.
export const USER_FLOW: { title: string; does: string; yours?: boolean }[] = [
  { title: "Write or pick", does: "A brief, a decision template or an example, with context.", yours: true },
  { title: "Check", does: "The Chief of Staff researches it and asks what it needs." },
  { title: "Review", does: "Answer the questions, keep the facts that fit.", yours: true },
  { title: "Watch", does: "Each step of the team, live, with the time." },
  { title: "Read", does: "The memo, the reviews, the research and the conflicts.", yours: true },
  { title: "Follow up", does: "Only the specialists it concerns work again." },
  { title: "Report", does: "Edit it, or have it written up as an investment proposal.", yours: true },
  { title: "Share", does: "Revise with the team, then download the PDF.", yours: true },
];

// How the data moves, as a sequence: the founder, the page, the API and the agents.
export function flowDiagram(rules: Pipeline["rules"]): string {
  return `sequenceDiagram
  autonumber
  actor F as Founder
  participant UI as Next.js page
  participant API as FastAPI
  participant C as Chief of Staff
  participant W as Web (Azure OpenAI or Tavily)
  participant S as Specialists
  F->>UI: Brief, context, template
  UI->>API: POST /brief/prepare
  API->>C: Plan two to four searches
  C->>W: Search
  W-->>C: Results with their sources
  C-->>UI: Up to ${rules.max_facts} facts with [n], up to ${rules.max_questions} questions
  F->>UI: Answers, the facts kept
  UI->>API: POST /evaluate/stream
  API->>C: Plan the objective and the tasks
  opt Deep research is on
    API->>W: A task per area, a profile per competitor
    W-->>API: Cited reports
  end
  par Each assigned specialist, at once
    API->>S: Task, brief, answers, facts, research
    S-->>API: Report, citing [n]
  end
  API->>C: Review each report
  alt Below ${rules.approval_score} of 5
    C-->>S: Feedback, revise once
  end
  API->>S: Cross-check each other's reports
  S-->>C: Conflicts
  C-->>S: Decisions, and who revises
  API->>C: Write the strategy
  C-->>API: Launch strategy
  API-->>UI: Each step as it finishes, then the result
  UI-->>F: The memo, the reviews, the research`;
}

// The routes the Chief of Staff's decisions take through the graph (graph.py).
export function decisionsDiagram(rules: Pipeline["rules"]): string {
  return `flowchart TD
  brief([Your brief]) --> plan[Plan: the objective and a task per specialist]
  plan -->|deep research on| research[Research each area and the main competitors]
  plan -->|otherwise| work[The specialists write their reports, at once]
  research --> work
  work --> review{Does each report score at least ${rules.approval_score} of 5?}
  review -->|no, and not yet revised| back[Back to its specialist with feedback]
  back --> work
  review -->|yes, or revised ${rules.max_revisions === 1 ? "once" : `${rules.max_revisions} times`} already| many{More than one report?}
  many -->|no| strategy[Write the launch strategy]
  many -->|yes| critique[The specialists cross-check each other]
  critique --> conflicts{Any conflicts?}
  conflicts -->|no| strategy
  conflicts -->|yes| decide[The Chief of Staff decides each one]
  decide -->|a report must change| revise[That specialist revises]
  revise --> strategy
  decide -->|nothing to change| strategy
  strategy --> out([Memo, report and proposal])`;
}

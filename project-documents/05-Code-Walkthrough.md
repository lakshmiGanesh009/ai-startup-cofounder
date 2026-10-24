# Code walkthrough

How the AI Startup Co-Founder Team works, file by file: where everything lives, how one request travels through the code, how LangGraph connects the agents, where every prompt is, and what the backend does around them.

**To present from it:** open this file in VS Code and press <kbd>⌘</kbd><kbd>⇧</kbd><kbd>V</kbd> (Markdown preview). Every link opens the file at the line it names, so you can follow the guide and show the code side by side. Section 9 is a suggested order for a 10-minute walkthrough.

Line numbers are those of `main` on 24 October 2026.

**Contents**

1. [The project at a glance](#1-the-project-at-a-glance)
2. [One evaluation, end to end](#2-one-evaluation-end-to-end)
3. [LangGraph: how the pieces connect](#3-langgraph-how-the-pieces-connect)
4. [The agents](#4-the-agents)
5. [Where the prompts are](#5-where-the-prompts-are)
6. [The model layer](#6-the-model-layer)
7. [What the backend does around the graph](#7-what-the-backend-does-around-the-graph)
8. [The web app](#8-the-web-app)
9. [A 10-minute walkthrough](#9-a-10-minute-walkthrough)
10. [Questions you may be asked, and where the answer is in the code](#10-questions-you-may-be-asked-and-where-the-answer-is-in-the-code)

---

## 1. The project at a glance

Two programs talk over HTTP:

- **The backend**: Python, FastAPI and LangGraph, about 11,000 lines in the repository's root and `agents/`. It runs the team of agents and keeps sessions and reports in PostgreSQL.
- **The web app**: Next.js 16 and React, about 13,900 lines in `frontend/`. The founder works in it, and its server forwards the browser's calls to the API.

```
ai-startup-cofounder/
├── main.py                 FastAPI app: every endpoint, streaming, error handling
├── graph.py                LangGraph state machine: nodes, edges, routers, checkpointer
├── state.py                The shared state and every structured model (Pydantic)
├── agents/
│   ├── chief_of_staff.py   Plan, review, critique, resolve, synthesis nodes + their prompts
│   ├── specialist.py       One node implementation shared by the four specialists
│   ├── roles.py            The four specialists' identities and system prompts
│   └── proposal_writer.py  Writes and revises the investment proposal, part by part
├── llm.py                  The model client: which deployment, which reasoning effort
├── brief.py                Preparing a brief: web search, facts, clarifying questions
├── deep_research.py        Deep research node: each area and the main competitors
├── lookups.py              Look-ups through MCP servers: FRED figures, competitors' pages
├── fred_server.py          Our own MCP server for FRED (economic data)
├── providers.py            Where web research runs: Azure OpenAI or Tavily
├── azure_web.py            Azure OpenAI's web search (Bing), on gpt-5-mini
├── search.py               Tavily search and research
├── guardrails.py           Prompt guardrails: fences, rules, injection flags
├── proposal.py             The investment proposal's structure; NPV, IRR, payback in code
├── reports.py              Reports, their versions, and the store that keeps them
├── document.py             Changes made exactly by code: currency, units, redaction
├── currency.py, units.py   Finding and converting amounts and measurements in text
├── report_pdf.py           The report or proposal as a PDF (with report_charts.py)
├── library.py, extract.py  The founder's uploaded documents, and questions about them
├── persistence.py          PostgreSQL (or memory): sessions, reports, uploads, history
├── security.py             API key, request size, rate limits, concurrent runs
├── observability.py        Request IDs, structured logs, access log
├── monitor.py              The Monitor page and Prometheus metrics
├── tracing.py              Langfuse: traces, prompt versions, scores
├── prompt_library.py       Every prompt the app sends, by name (registered in Langfuse)
├── judge.py                An LLM judge of a finished strategy (Langfuse scores)
├── voice.py                Dictation: speech to text with Whisper
├── progress.py             Turns each step's result into the line the UI shows live
├── config.py               Settings read from the environment (.env)
├── scenarios/, templates/  Example startups, and decision templates for a brief
├── tests/                  425 backend tests (pytest), 97% of the code covered
├── frontend/               The web app (200 tests, Vitest)
└── docs/                   architecture.md (the full reference), performance, demo
```

**The models**, set in `.env` and chosen per role in [llm.py](../llm.py#L121):

| Who | Deployment | Reasoning |
| --- | --- | --- |
| Chief of Staff (the manager agent) | `gpt-5.6-luna` | medium |
| The four specialists | `gpt-5.6-terra` | none (the "minimal" setting) |
| Web search, for the brief and deep research | `gpt-5-mini` | low, fixed |
| Dictation | `whisper` | — |

---

## 2. One evaluation, end to end

The founder types an idea on the Evaluate page and clicks **Evaluate**. This is the path through the code.

| # | Where | What happens |
| --- | --- | --- |
| 1 | [evaluate-app.tsx](../frontend/src/components/evaluate/evaluate-app.tsx#L148) `send()` | Collects the brief, the context (market, constraints, competition, answers, research facts) and the reasoning sliders. |
| 2 | [api.ts](../frontend/src/lib/api.ts#L350) `evaluateStream()` | POSTs to `/api/evaluate/stream` and reads the answer as server-sent events. |
| 3 | [route.ts](../frontend/src/app/api/%5B...path%5D/route.ts#L61) `forward()` | The web app's own server forwards the call to the API, adding the API key on the server side, so the key never reaches the browser. |
| 4 | [security.py](../security.py#L155) `Guard` | Before any route: checks the key, the body's size, the caller's rate and how many runs are already going. |
| 5 | [main.py](../main.py#L651) `evaluate_stream()` | The endpoint. [`_start()`](../main.py#L483) gives the request a session id, scans it for prompt injection ([guardrails.py](../guardrails.py#L121)) and builds the graph's input and its config: `thread_id` = the session id. |
| 6 | [main.py](../main.py#L676) `graph.astream(...)` | **Runs the LangGraph graph.** With `stream_mode=["tasks"]` LangGraph reports each node as it starts and finishes. |
| 7 | [progress.py](../progress.py#L132) `summarize()` | Turns each finished node's result into a line for the UI ("Reviewed 4 reports: approved 3, sent back Financial Planning"). |
| 8 | main.py, inside the loop | Sends each as an SSE event, `start` or `done`, which the page shows live and lights up on the Live graph. |
| 9 | [main.py](../main.py#L551) `_finish()` | Saves the session's report ([reports.py](../reports.py#L658) `record`), scores the run in Langfuse, and sends the `result` event. |
| 10 | [result-view.tsx](../frontend/src/components/evaluate/result-view.tsx) | Shows the strategy, each specialist's report, the reviews and the conflicts settled. |

A **follow-up** goes the same way with the same `session_id`. The checkpointer gives the graph the session's saved state, so only the specialists the follow-up affects work again ([section 3](#the-checkpointer-sessions-and-follow-ups)).

The plain [`POST /evaluate`](../main.py#L613) runs the same graph with `graph.ainvoke` and answers once, without the live steps.

---

## 3. LangGraph: how the pieces connect

All of it is in [graph.py](../graph.py), 157 lines. The agents never call each other: **each node reads the shared state and returns an update to it, and the edges decide which node runs next.**

### The graph

```
                              START
                                │
                              plan ............... Chief of Staff: the objective, who works on what
                                │  _route_after_plan
                ┌───────────────┼────────────────┐
             lookup          research        (neither: straight on)
        FRED figures       deep research
        (MCP server)       (if ticked)
                └───────────────┼────────────────┘
                                │  _route_to_assigned: fan out, in parallel
          ┌───────────┬─────────┴─────────┬────────────┐
      marketing    finance           technical       risk ...... the assigned specialists
          └───────────┴─────────┬─────────┴────────────┘
                                │  _route_after_specialist
                             review ............. Chief of Staff scores each report 1-5
                                │  _route_after_review
              ┌─────────────────┼──────────────────────┐
     score below 4:          critique              one specialist only:
     back to that       each specialist checks       straight to synthesis
     specialist, once     the others' reports
     (then review again)        │
                             resolve ............. Chief of Staff decides each conflict
                                │  _route_after_resolve
                  ┌─────────────┴─────────────┐
        a specialist must change          synthesis ...... Chief of Staff writes the strategy
        to match a decision →                 │
        it revises, then synthesis           END
```

The How it works page draws this same graph live from the code: [`/pipeline`](../main.py#L338) asks LangGraph for its Mermaid diagram.

### The state

[`WorkflowState`](../state.py#L328) is a `TypedDict`: the request, the plan, the assignments, the reports (`analyses`), the reviews, the conflicts, the resolutions, the research, the FRED figures, per-step metrics and the final strategy.

Some fields have a **reducer**, a function that says how two updates combine. That is what makes the parallel steps safe:

| Field | Reducer | Why |
| --- | --- | --- |
| `analyses` | [`_merge_analyses`](../state.py#L310): merge by specialist name | Four specialists finish in the same step, and each adds its own report without overwriting the others'. |
| `review_history`, `resolutions` | `_append` | Each review round and each decision is kept. |
| `metrics` | `_merge_metrics`: sum per step | Calls, tokens and seconds from parallel nodes add up. |

### Nodes

Registered in [`build_graph()`](../graph.py#L129):

| Node | Function | File |
| --- | --- | --- |
| `plan` | [`plan_node`](../agents/chief_of_staff.py#L182) | agents/chief_of_staff.py |
| `lookup` | [`lookup_node`](../lookups.py#L311) | lookups.py |
| `research` | [`research_node`](../deep_research.py#L153) | deep_research.py |
| `marketing`, `finance`, `technical`, `risk` | [`specialist_node(role)`](../agents/specialist.py#L74): one function, four roles | agents/specialist.py |
| `review` | [`review_node`](../agents/chief_of_staff.py#L233) | agents/chief_of_staff.py |
| `critique` | [`critique_node`](../agents/chief_of_staff.py#L304) | agents/chief_of_staff.py |
| `resolve` | [`resolve_node`](../agents/chief_of_staff.py#L355) | agents/chief_of_staff.py |
| `synthesis` | [`synthesis_node`](../agents/chief_of_staff.py#L432) | agents/chief_of_staff.py |

### Edges: the five routers

A conditional edge calls a router with the state. **When a router returns a list of node names, LangGraph runs them all at once.** That is how the specialists run in parallel.

| Router | Decides |
| --- | --- |
| [`_route_after_plan`](../graph.py#L81) | Look up FRED figures (once a session) and/or do deep research (if asked), side by side; or go straight to the specialists. |
| [`_route_to_assigned`](../graph.py#L76) | Fan out to exactly the specialists the plan assigned: all four for a new idea, one or two for a narrow question or a follow-up. |
| [`_route_after_review`](../graph.py#L95) | Rejected reports go back to their specialists; otherwise critique; with one specialist, straight to synthesis. |
| [`_route_after_specialist`](../graph.py#L107) | A fresh report goes to review. A report revised to match a decision goes to synthesis, or to another critique round if one is allowed. |
| [`_route_after_resolve`](../graph.py#L123) | Specialists who must change to match a decision revise; otherwise synthesis. |

**The loops are bounded**, so a run always ends:
- A report is sent back at most once: `MAX_ITERATIONS = 1` ([config.py](../config.py#L15)).
- One round of critique and resolve: `MAX_CRITIQUE_ROUNDS = 1` ([config.py](../config.py#L18)).
- A report needs 4 out of 5 to be approved: `APPROVAL_SCORE` ([chief_of_staff.py](../agents/chief_of_staff.py#L42)).

### The checkpointer: sessions and follow-ups

The graph is compiled with a **checkpointer** ([graph.py](../graph.py#L157)), which saves the state after every step under the request's `thread_id`, the session id:

- With a database, it's LangGraph's `AsyncPostgresSaver` ([persistence.py](../persistence.py#L338)), so a session survives a restart. Without one, `MemorySaver`.
- On a follow-up, [`plan_node`](../agents/chief_of_staff.py#L182) sees the earlier reports (`prior`) and assigns only the specialists the follow-up affects; the others' reports stand. Per-request fields are reset with LangGraph's `Overwrite`, so a follow-up reports only its own reviews and cost.
- Deleting a report also deletes its saved state ([main.py](../main.py#L882)).

### The plan, act, check loop

The capstone asks for ReAct or Plan–Act–Check. Here it is **Plan–Act–Check, with reflection**:

| Phase | Node |
| --- | --- |
| **Plan** | `plan`: the Chief of Staff states the objective and gives each specialist one task. |
| **Act** | The specialists write their reports, from the research and the FRED figures. |
| **Check** | `review` scores each report against its task with a rubric, and a weak one is revised with the Chief's feedback (reflection). |
| **Check again** | `critique` has the specialists check each other; `resolve` settles the conflicts; the affected reports are revised. |
| **Synthesise** | `synthesis` merges the reports and the decisions into one strategy. |

---

## 4. The agents

### The Chief of Staff (the manager agent)

[agents/chief_of_staff.py](../agents/chief_of_staff.py): five nodes, all on Luna except the critique, which is the specialists' own.

| Step | What it does | Answer, validated by Pydantic |
| --- | --- | --- |
| [plan](../agents/chief_of_staff.py#L182) | The objective as the decision at stake; which specialists are needed and one task each | [`DelegationPlan`](../state.py#L26) |
| [review](../agents/chief_of_staff.py#L233) | Scores each report 1-5 against a rubric, with feedback below 4. The reports are reviewed in parallel. | [`ReviewResult`](../state.py#L61) |
| [critique](../agents/chief_of_staff.py#L304) | Each specialist flags up to two real contradictions with the others (Terra) | [`SpecialistCritique`](../state.py#L77) |
| [resolve](../agents/chief_of_staff.py#L355) | Decides every conflict in one call, so the decisions agree; names who must change | [`Resolutions`](../state.py#L93) |
| [synthesis](../agents/chief_of_staff.py#L432) | Writes the strategy: Go / Go with conditions / Not yet, the facts, decisions, risks, next steps, metrics | prose (markdown) |

Two helpers do the calling:
- [`structured_invoke`](../agents/chief_of_staff.py#L45) asks for a Pydantic schema and retries once on a reply that doesn't parse or that the content filter withheld.
- [`_ask_each`](../agents/chief_of_staff.py#L96) runs several of those in parallel threads.

### The specialists

[agents/roles.py](../agents/roles.py) defines the four as data: a name, a title, a focus and a brief that gives each its point of view. [agents/specialist.py](../agents/specialist.py) turns any role into a node. **Every specialist shares one implementation and differs only in its role.**

[`_build_prompt`](../agents/specialist.py#L24) gives a specialist everything it should work from:
- the request;
- its task from the Chief of Staff;
- the founder's details and documents;
- its area's deep research and, for Marketing and Finance, the competitor profiles;
- the FRED figures;
- on a revision, its previous report and the feedback to apply.

A specialist that fails returns a report marked `[unavailable]` ([`GAP_PREFIX`](../agents/specialist.py#L21)). The run goes on, and the strategy names the gap.

---

## 5. Where the prompts are

**The prompts live in the code, next to the step that uses them.** [prompt_library.py](../prompt_library.py) gathers all **22** by name, and [tracing.py](../tracing.py#L296) registers each in Langfuse as a version at start-up, so every traced call links to the exact prompt text it used.

| Prompt (Langfuse name) | Where | Model | Answer |
| --- | --- | --- | --- |
| `chief/plan` | [chief_of_staff.py](../agents/chief_of_staff.py#L117) `_PLANNER_PROMPT` | Luna | DelegationPlan |
| `chief/review` | [chief_of_staff.py](../agents/chief_of_staff.py#L215) `_REVIEW_PROMPT` | Luna | ReviewResult |
| `specialists/critique` | [chief_of_staff.py](../agents/chief_of_staff.py#L291) `_CRITIQUE_PROMPT` | Terra | SpecialistCritique |
| `chief/resolve` | [chief_of_staff.py](../agents/chief_of_staff.py#L341) `_RESOLVE_PROMPT` | Luna | Resolutions |
| `chief/synthesis` | [chief_of_staff.py](../agents/chief_of_staff.py#L401) `_SYNTHESIS_PROMPT` | Luna | prose |
| `specialists/marketing`, `finance`, `technical`, `risk` | [roles.py](../agents/roles.py#L47): each role's `brief`, plus `_BREVITY` ([L22](../agents/roles.py#L22)) | Terra | prose |
| `brief/search` | [brief.py](../brief.py#L106) `_SEARCH_PROMPT` | Terra | SearchPlan |
| `brief/review` | [brief.py](../brief.py#L115) `_REVIEW_PROMPT` | Luna | BriefReview (facts + questions) |
| `research/competitors` | [deep_research.py](../deep_research.py#L71) | Luna | Competitors |
| `lookups/fred-searches`, `lookups/fred-picks` | [lookups.py](../lookups.py#L151), [L292](../lookups.py#L292) | Luna | FredSearches, FredPicks |
| `proposal/market`, `technical`, `risk`, `financial`, `executive`, `rewrite` | [proposal_writer.py](../agents/proposal_writer.py#L80) `_PARTS`, `_EXECUTIVE` ([L174](../agents/proposal_writer.py#L174)) | Terra; the executive summary on Luna | each part's schema ([proposal.py](../proposal.py#L179)) |
| `documents/answer` | [library.py](../library.py#L278) `ANSWERER` | Luna | Answer, with citations |
| `judge/strategy` | [judge.py](../judge.py#L35) `JUDGE_PROMPT` | Luna | scores 1-5 |

**How a prompt is put together:**
- **System message:** the role's instructions, plus [`RULES`](../guardrails.py#L31), the security rules appended to *every* system prompt.
- **Human message:** the request and its material. Anything that came from the founder or the web is wrapped in `<untrusted source="...">` fences by [`fence()`](../guardrails.py#L101).
- **Structured answers:** 17 of the 22 prompts ask for a Pydantic schema through `with_structured_output`. The specialists' four reports and the synthesis are written as prose by design.
- **Figures:** a model never does the arithmetic. NPV, IRR, payback and break-even are calculated in [`investment_metrics()`](../proposal.py#L287) from Finance's drivers, and currency and unit conversions in [document.py](../document.py).

---

## 6. The model layer

[llm.py](../llm.py) is the only place that builds a model client:

- [`get_llm(role)`](../llm.py#L217) returns the model for `CHIEF` or `SPECIALIST`. Each call site names its role, never a model.
- [`deployment(role)`](../llm.py#L121) chooses Luna for the Chief of Staff (`AZURE_OPENAI_CHIEF_DEPLOYMENT_NAME`) and Terra for everyone else (`AZURE_OPENAI_DEPLOYMENT_NAME`).
- **Reasoning effort** is per role, from `.env`, and per request: the sidebar's sliders arrive with the request and apply through [`reasoning()`](../llm.py#L111), a context variable that the graph's worker threads inherit. gpt-5.6 models take "none" where older models took "minimal" ([L152](../llm.py#L152)).
- [`Counted`](../llm.py#L187) wraps every model, so the Monitor sees each call's tokens, time and failures.
- [`failure()`](../llm.py#L54) and [`refused()`](../llm.py#L44) turn a provider error into words for the founder. A safety-policy refusal becomes a 422 and the red warning, never a raw 502 ([main.py](../main.py#L184) `_failed`).
- Models are cached per (effort, deployment), so calls reuse one connection pool.

Web search does not go through `get_llm`. It is a Responses API call with the `web_search` tool, on its own deployment, gpt-5-mini ([azure_web.py](../azure_web.py#L62)), with a 45 s limit for a brief's searches ([L37](../azure_web.py#L37)).

---

## 7. What the backend does around the graph

### The endpoints

All in [main.py](../main.py). A failed model call becomes a 502 (a 422 for a refusal) and missing credentials a 503, so a provider problem never shows up as a 500.

| Area | Endpoints |
| --- | --- |
| **Prepare a brief** | [`POST /brief/prepare`](../main.py#L429): web search, the facts kept and up to 3 questions ([brief.py](../brief.py#L173)) |
| **Run the team** | [`POST /evaluate/stream`](../main.py#L651) (live), [`POST /evaluate`](../main.py#L613) |
| **Reports** | [`GET /reports`](../main.py#L869), [`GET`/`PUT`/`DELETE /reports/{id}`](../main.py#L875), [`reset`](../main.py#L902), [`versions`](../main.py#L1090), [`changes`](../main.py#L1097), [`restore`](../main.py#L1109), [`choices`](../main.py#L1073) |
| **Investment proposal** | [`POST …/proposal`](../main.py#L974) (write), [`…/proposal/revise`](../main.py#L984), [`…/revise`](../main.py#L1003) (one passage) |
| **Document control** | [`POST …/drafts`](../main.py#L1035) (currency, units, redaction, done in code) and [`…/accept`](../main.py#L1066) |
| **PDF** | [`GET …/pdf`](../main.py#L1116), [`POST …/pdf`](../main.py#L1135) (preview a draft) |
| **The founder's documents** | [`POST /uploads`](../main.py#L1159), [`POST /ask`](../main.py#L1239) |
| **Dictation** | [`POST /transcribe`](../main.py#L1195) ([voice.py](../voice.py#L129)) |
| **Operations** | [`/health`](../main.py#L240), [`/monitoring`](../main.py#L396), [`/metrics`](../main.py#L406) (Prometheus), [`/pipeline`](../main.py#L338) |

### Preparing a brief, before the team runs

[`prepare_brief()`](../brief.py#L173):
1. Terra plans up to 4 web searches.
2. They run at once on gpt-5-mini ([providers.py](../providers.py#L40) → [azure_web.py](../azure_web.py#L117)), or on Tavily if chosen.
3. Luna keeps the facts that bear on the decision, each with its sources, and asks up to 3 questions about what is missing.

The founder reviews them, and they travel with the request in its `context`, so every agent works from them.

### Research and official figures, inside the graph

- **Deep research** ([`research_node`](../deep_research.py#L153)): one research task per assigned specialist's area, plus profiles of up to 3 competitors that Luna names, all at once. Sources are numbered once for the whole session, so `[3]` means the same page in every report.
- **FRED figures** ([`lookup_node`](../lookups.py#L311)): Luna names the figures the venture turns on, and code fetches them through **our own MCP server**, [fred_server.py](../fred_server.py), started as a subprocess and spoken to over stdio ([SERVERS](../lookups.py#L93)). When deep research runs on Tavily, the competitors' own pricing pages are read through Tavily's hosted MCP server ([L445](../lookups.py#L445)).
- A failed search or look-up is left out with a note. It never fails the run.

### The investment proposal

[`write_proposal()`](../agents/proposal_writer.py#L377) writes in **three waves** ([`WAVES`](../agents/proposal_writer.py#L54)):
1. Market, Technical and Risk in parallel.
2. Finance, with those in front of it.
3. The executive summary, by the Chief of Staff.

The figures are then checked in code, and Finance gets one call to fix any that fail.

### Reports, versions and storage

- [reports.py](../reports.py#L648) `ReportStore` keeps each session's report. Every change raises its version, and a change made from an older version is refused with a 409, so two editors can't overwrite each other. Earlier versions are kept for comparing and restoring.
- [persistence.py](../persistence.py#L376) chooses PostgreSQL (when `DATABASE_URL` is set) or memory. It holds the sessions (LangGraph's checkpointer), reports, versions, uploads and the Monitor's history. The tables are created by [migrations](../persistence.py#L54).

### Safety and operations

| Concern | Where |
| --- | --- |
| Prompt injection | [guardrails.py](../guardrails.py): founder and web text fenced; sentences that try to instruct the agents cut out ([`_SIGNS`](../guardrails.py#L54)), flagged and shown to the founder |
| Access and abuse | [security.py](../security.py#L155): API key, body size, requests per minute, runs per hour, concurrent runs |
| Input validation | Pydantic request models in main.py: lengths, patterns, types (422) |
| Following a request | [observability.py](../observability.py): a request ID on every log line and response |
| What the API is doing | [monitor.py](../monitor.py#L406): each step's time, calls and tokens; each provider's use and failures; the Monitor page |
| Tracing and quality | [tracing.py](../tracing.py#L198): a Langfuse trace per request, prompt versions, scores; [judge.py](../judge.py) |

---

## 8. The web app

[frontend/src](../frontend/src): three pages and a proxy.

| Page | Entry | Main pieces |
| --- | --- | --- |
| **Evaluate** `/` | [app/page.tsx](../frontend/src/app/page.tsx) → [evaluate-app.tsx](../frontend/src/components/evaluate/evaluate-app.tsx) | [composer.tsx](../frontend/src/components/evaluate/composer.tsx) (the brief), [brief-review.tsx](../frontend/src/components/evaluate/brief-review.tsx) (facts and questions), [team-progress.tsx](../frontend/src/components/evaluate/team-progress.tsx) and [live-graph.tsx](../frontend/src/components/evaluate/live-graph.tsx) (live), [result-view.tsx](../frontend/src/components/evaluate/result-view.tsx) |
| **Reports** `/reports` | [reports-app.tsx](../frontend/src/components/reports/reports-app.tsx) | [report-picker.tsx](../frontend/src/components/reports/report-picker.tsx), [proposal-view.tsx](../frontend/src/components/reports/proposal-view.tsx), [pdf-panel.tsx](../frontend/src/components/reports/pdf-panel.tsx) (document control), [ask-panel.tsx](../frontend/src/components/reports/ask-panel.tsx), [report-versions.tsx](../frontend/src/components/reports/report-versions.tsx) |
| **How it works** `/how-it-works` | [how-app.tsx](../frontend/src/components/how/how-app.tsx) | [pipeline-map.tsx](../frontend/src/components/how/pipeline-map.tsx), [diagrams.tsx](../frontend/src/components/how/diagrams.tsx), [monitor-view.tsx](../frontend/src/components/how/monitor-view.tsx) |

- [lib/api.ts](../frontend/src/lib/api.ts) is every call to the API, typed to match its responses, with [`ApiError`](../frontend/src/lib/api.ts#L207).
- [`app/api/[...path]/route.ts`](../frontend/src/app/api/%5B...path%5D/route.ts#L12) is the proxy. It forwards only the API's own routes and adds the key on the server.
- [lib/backend.tsx](../frontend/src/lib/backend.tsx#L149) shares the API's health, the reasoning sliders and the research provider with every page.

---

## 9. A 10-minute walkthrough

The order to open files in, and the point to make at each.

1. **[graph.py](../graph.py#L129): the whole system on one screen.** "Every box in the diagram is a node, the agents only talk through the shared state, and these five routers decide what runs next. A list from a router means run in parallel."
2. **[state.py](../state.py#L328): the shared state.** "The reducers are why four specialists can write at the same moment without overwriting each other."
3. **[chief_of_staff.py `plan_node`](../agents/chief_of_staff.py#L182) and its [prompt](../agents/chief_of_staff.py#L117).** "Hierarchical delegation: the Chief decides who works on what, and its answer must fit a Pydantic schema."
4. **[roles.py](../agents/roles.py#L47) and [specialist.py](../agents/specialist.py#L74).** "Four specialists, one implementation: each differs only in its brief."
5. **[`review_node`](../agents/chief_of_staff.py#L233), then [`critique_node`](../agents/chief_of_staff.py#L304) and [`resolve_node`](../agents/chief_of_staff.py#L355).** "Plan–Act–Check with reflection: a rubric, feedback and a revision, then the specialists check each other and the Chief settles conflicts. Bounded by MAX_ITERATIONS, so it always ends."
6. **[`synthesis_node`](../agents/chief_of_staff.py#L432).** "One strategy, leading with Go, Go with conditions or Not yet."
7. **[main.py `evaluate_stream`](../main.py#L651), line [676](../main.py#L676).** "The API runs the graph and streams each step to the browser as it happens."
8. **[llm.py `get_llm`](../llm.py#L217).** "Each role gets its own model: Luna for the Chief, Terra for the specialists."
9. **[guardrails.py](../guardrails.py#L31) and [proposal.py `investment_metrics`](../proposal.py#L287).** "Founder and web text is fenced and checked for injection; the financial figures are calculated in code, not by the model."
10. **[tests/](../tests).** "425 backend tests run the graph against a fake model ([conftest.py `fake_llm`](../tests/conftest.py#L307)), and cover 97% of the code."

---

## 10. Questions you may be asked, and where the answer is in the code

| Question | Answer | Show |
| --- | --- | --- |
| How do the agents communicate? | Through the shared state, never directly. Each node returns an update; the edges route. | [state.py](../state.py#L328), [graph.py](../graph.py#L129) |
| How do the specialists run in parallel? | A router returns a list of node names; LangGraph runs them in the same step; the `analyses` reducer merges their reports. | [graph.py](../graph.py#L76), [state.py](../state.py#L310) |
| Where is the reasoning loop? | Plan → specialists → review → revise → critique → resolve → revise → synthesis. | [section 3](#the-plan-act-check-loop) |
| What stops it looping forever? | One revision, one critique round, set in config. | [config.py](../config.py#L15) |
| How is a follow-up handled? | The checkpointer restores the session by `thread_id`; the plan reassigns only the affected specialists. | [chief_of_staff.py](../agents/chief_of_staff.py#L148) |
| How are LLM outputs validated? | 17 of 22 prompts answer in a Pydantic schema; a reply that doesn't parse is retried once. | [chief_of_staff.py](../agents/chief_of_staff.py#L45) |
| Where are the numbers computed? | In code, from Finance's drivers. | [proposal.py](../proposal.py#L287) |
| What if a specialist or a search fails? | The specialist's report is marked unavailable and the run goes on; a failed search is left out with a note. | [specialist.py](../agents/specialist.py#L88), [azure_web.py](../azure_web.py#L117) |
| How is prompt injection handled? | Fenced, scanned, cut out, flagged; `RULES` on every system prompt. | [guardrails.py](../guardrails.py#L1) |
| How did you optimise cost and latency? | Parallel specialists, reviews and critiques; only the needed specialists; approved reports never re-reviewed; short reports; follow-ups reuse reports and research; cheaper model for search. | [roles.py](../agents/roles.py#L17), [chief_of_staff.py](../agents/chief_of_staff.py#L233), [docs/performance.md](../docs/performance.md) |
| Which model does what? | Luna for the Chief of Staff, Terra for the specialists, gpt-5-mini for web search. | [llm.py](../llm.py#L121) |
| How do you see what happened in a run? | The live steps and Live graph, the Monitor page, Langfuse traces, request IDs in the logs. | [monitor.py](../monitor.py), [tracing.py](../tracing.py#L198) |

For more depth on any part, [docs/architecture.md](../docs/architecture.md) is the full reference.

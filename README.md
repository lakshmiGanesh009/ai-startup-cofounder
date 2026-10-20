# The AI Startup Co-Founder Team: Autonomous Multi-Agent Venture Simulator

## 📌 Problem Statement

Early-stage startups require coordinated decision-making across product strategy, market positioning, technical feasibility, financial planning, and risk assessment. Founders must evaluate incomplete information, debate trade-offs, and align on execution plans---often under uncertainty and resource constraints.

Traditional AI systems generate isolated outputs, but real startup success depends on structured collaboration and leadership-driven synthesis.

## 🌍 Context

The AI Startup Co-Founder Team simulates a founding team where specialized AI agents collaborate under a Chief of Staff (Manager Agent) to evaluate ideas, refine strategies, and produce a cohesive business execution plan.

## 🚧 Key Real-World Challenges

- Startup decisions involve multiple conflicting perspectives.
- Strategy requires iterative refinement, not one-shot responses.
- Founders must balance market opportunity, financial viability, and technical feasibility.
- Poor coordination leads to inconsistent or fragmented plans.
- Decision-making requires structured delegation and synthesis.

## 🎯 Project Goal

Build an Autonomous Multi-Agent System that:

- Models startup roles as specialized agents (Marketing, Finance, Technical, Risk).
- Uses structured reasoning loops (ReAct or Plan--Act--Check).
- Implements hierarchical delegation via a Chief of Staff agent.
- Enables critique and refinement cycles.
- Produces a unified startup launch strategy.

## 🧠 Problem Description

This project focuses on engineering a Stateful Multi-Agent System that:

- Defines clear role-based agent responsibilities.
- Models workflows using state machines (LangGraph).
- Enables inter-agent discussion and critique.
- Applies reflection for output improvement.
- Synthesizes final recommendations into a cohesive strategy document.
- Optimizes workflow for cost, latency, and quality.

The system should support natural language prompts such as:

- "Evaluate this startup idea in the AI healthcare space."
- "Identify risks in our go-to-market plan."
- "Refine the pricing strategy after financial review."

## ⚙️ Functional Requirements

Your system must support:

### 🧩 Role-Based Agents

- Marketing Strategy Agent
- Financial Planning Agent
- Technical Feasibility Agent
- Risk & Compliance Agent

### 🧭 Manager-Led Delegation

- Chief of Staff agent coordinating tasks
- Structured delegation and synthesis logic

### 🔄 Iterative Reasoning

- ReAct or Plan--Act--Check loops
- Reflection and critique cycles

### 🔗 Multi-Agent Coordination

- Back-and-forth workflow between agents
- Conflict resolution and refinement

### 📊 Optimization

- Reduction of redundant reasoning calls
- Improved latency and structured outputs

## 🧪 Technical Details

### 🧑‍💻 Programming Language

- Python

### 🏗️ Core Framework

- LangGraph

### 🧰 Libraries & Tools

| Tool / Library | Purpose |
| --- | --- |
| langgraph | Stateful workflow orchestration |
| langchain | Agent abstractions and tools |
| openai / anthropic | LLM APIs |
| pydantic | Structured outputs |
| fastapi | Backend API (optional) |
| uvicorn | API server |
| dotenv | Environment configuration |

### 🔐 Environment Variables

| Variable | Purpose |
| --- | --- |
| OPENAI_API_KEY | LLM authentication |
| ANTHROPIC_API_KEY | Optional LLM provider |
| MODEL_NAME | Selected LLM |
| DEBUG_MODE | Workflow debugging flag |

### 🏗️ Infrastructure Requirements

- Python environment
- LLM API access
- Optional backend service (FastAPI)
- Local or cloud deployment setup

## 📚 Sample Inputs

- Startup idea description
- Target market segment
- Business constraints (budget, timeline)
- Competitive landscape summary

## 📦 Project Deliverables

### 1️⃣ Functional Multi-Agent System

- Role-based agent implementation
- Manager-led delegation
- Reflection loop integration
- Coordinated workflow execution

### 2️⃣ Architecture & Workflow Design

- State machine diagram
- Delegation logic documentation
- Reasoning loop explanation

### 3️⃣ Optimization & Refactoring

- Modular code structure
- Performance improvement analysis
- Error handling strategy

### 4️⃣ Demonstration

- Live walkthrough of startup evaluation process
- Iterative refinement example

### 5️⃣ Documentation

- Architecture diagram
- Agent role definitions
- Workflow explanation
- Design trade-offs summary

## 🧪 Evaluation Criteria

The system will be evaluated on:

- Multi-agent coordination quality
- Delegation and synthesis effectiveness
- Reflection and self-correction capability
- Workflow clarity and state modeling
- System optimization and performance
- Code quality and modularity
- Documentation clarity

## 🚀 Getting Started

- Define agent roles and responsibilities
- Design state transitions using LangGraph
- Implement base agents
- Add delegation logic
- Integrate reflection loop
- Optimize workflow
- Test with multiple startup scenarios
- Document architecture and reasoning flow

Note: Focus on demonstrating structured collaboration and
hierarchical orchestration rather than producing a single static
business plan.

---

## Implementation

A Chief of Staff agent plans and delegates, four specialists (Marketing, Finance, Technical, Risk & Compliance) analyse the request in parallel, the Chief of Staff reviews and reconciles their reports, and a synthesis step produces one launch strategy. The workflow is a LangGraph state machine served by a FastAPI backend, with a Next.js frontend on top. [docs/architecture.md](docs/architecture.md) explains it in full, and [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) records how it was built step by step.

### Setup

Requires [uv](https://docs.astral.sh/uv/); it installs Python 3.12 and the dependencies.

```bash
uv sync
cp .env.example .env
```

Fill in `.env` with Azure OpenAI or OpenAI credentials. The provider is chosen by which credentials are set.

Sessions, reports and the Monitor's history are kept in [PostgreSQL](https://www.postgresql.org), so a restart loses none of them. Create the database `.env.example` points `DATABASE_URL` at, or leave `DATABASE_URL` unset to keep everything in memory:

```bash
createdb cofounder
```

For the frontend, install its packages with [Node.js](https://nodejs.org/) 20.9 or newer:

```bash
cd frontend
npm install
cp .env.example .env.local
```

### Run the API

```bash
uv run python main.py
```

The API listens on http://localhost:8000, with interactive docs at http://localhost:8000/docs.

- `GET /health` — health check, with the reasoning efforts a request can choose and the configured defaults, where web research can run, and where sessions and reports are kept (`storage`: `postgres` or `memory`, and whether it answers; the status is `degraded` while the database does not).
- `GET /scenarios` — the example scenarios in `scenarios/`, each with a short title, to start a request from.
- `GET /pipeline` — how the team is set up, for the How it works page: the LangGraph graph as a Mermaid diagram, the specialists, and the rules the Chief of Staff decides by (the approval score, the revision and critique rounds, the word limits), read from the running code.
- `GET /monitoring` — what the API has done since it started: whether a warning or error was logged in the last 15 minutes, the evaluations running and ended (the median and 95th-percentile time to a decision), briefs and proposals, requests and server errors, the time (median and 95th percentile), model calls and tokens of each step of the graph, review and conflict counts, research costs, and a log of recent events, warnings and errors (Azure's retries among them), each naming its request. The statistics count since the API started; the latest evaluations and the log are kept in PostgreSQL, so a restart keeps them (in memory without a database).
- `GET /metrics` — the same counters and timings for [Prometheus](https://prometheus.io) to scrape, which keeps their history: requests by route and status with their time, evaluations finished and failed with theirs, each step's time, model calls and tokens, reviews, conflicts, research cost, model retries, warnings and errors, and the process's own figures. In the text format, or OpenMetrics when the scraper asks; not in the interactive docs.
- `GET /templates` — the decision templates in `templates/`: evaluate an idea, plan the go-to-market, set the price, get ready to raise, respond to a competitor. Each is a brief to fill in, with what to look up and ask for that decision.
- `POST /brief/prepare` — prepare a brief before the team runs it. The Chief of Staff plans a few web searches, Azure OpenAI's own web search (Bing, on the team's deployment) or [Tavily](https://tavily.com) runs them (`research_provider`: `azure`, the default, or `tavily`), and the Chief of Staff keeps the facts that bear on the decision, each citing its sources, and asks up to three questions about facts only the founder knows. Body: `prompt`, optional `context`, `template` and `reasoning`. Send the facts the founder keeps and their answers in the evaluation's `context` (`research`, `answers`), and every agent works from them; the report gains a "Web Research" section with the sources. About 10–30 s. With neither provider set up the brief is still checked, and `research_note` says why there is no research; a failed search never fails the request.
- `POST /evaluate` — run the founding team. Body: `prompt`, optional `context` (target market, constraints, competitive landscape), optional `session_id` for a follow-up, optional `reasoning` (`{"specialist": "low", "chief": "high"}`, each `minimal`, `low`, `medium` or `high`) to override the configured efforts for this request, optional `deep_research: true` to research each assigned specialist's area and profile up to three competitors on the web before the specialists start, and `research_provider` for where: `azure` (Azure OpenAI's web search: about half a minute and a few dozen Bing searches, billed to Azure) or `tavily` (Tavily's Research API, for demanding tasks: a minute or two and 150–450 Tavily credits). A follow-up reuses the session's research. The response holds the objective, the per-specialist assignments and analyses, the review history, any conflict resolutions, per-node metrics, the final strategy, and the session's deep `research`, if any: a cited report per area, the competitor profiles, every source numbered once, and the credits used. A full evaluation takes about two minutes at the default efforts, 5–10 minutes with the Chief of Staff at `high`. Missing credentials return 503, and an LLM call that still fails after its retries returns 502.
- `POST /evaluate/stream` — the same evaluation, reported as it happens, as server-sent events. Each step of the graph (`plan`, each specialist, `review`, `critique`, `resolve`, `synthesis`) sends a `start` event and a `done` event; the `done` event carries a one-line summary, such as "Reviewed 4 reports: approved 3, sent back Financial Planning.", and the figures behind it. A `result` event with the body `/evaluate` returns ends the stream. A failure ends it with an `error` event carrying the status `/evaluate` would have returned (503, 502 or 500). The Evaluate page uses this to show the team at work.

Every response carries an `X-Request-ID` header: the ID the request sent, if it is 8–64 letters, digits, dots, dashes or underscores, else a new one. Every log line written while the request was handled names it, as do the Monitor's warnings and errors, so the ID an error shows leads to its lines in the logs. An error the API did not expect answers 500 with `{"detail": ..., "request_id": ...}`.

With `API_KEY` set, every route but `/health` needs it, as `Authorization: Bearer <key>` (or `X-API-Key`); `/metrics` too, so give Prometheus the key. The API also limits what one caller can do: a body over `MAX_REQUEST_BYTES` is refused (413); each caller may send `REQUESTS_PER_MINUTE` requests a minute and start `RUNS_PER_HOUR` evaluations, briefs and proposals an hour; and at most `MAX_CONCURRENT_RUNS` run at once. Over a limit the answer is 429 with `Retry-After`. A request may hold only what a brief needs: a prompt or instruction of 8,000 characters, context fields of 4,000, ten answers, twenty facts and fifty sources, each source a web address (422 otherwise).

The founder's text and the web's are the material of the team's work, never instructions to it. Every agent reads them between `<untrusted>` markers that name their source, cleaned of invisible characters and unable to close their markers early, and every agent's system prompt says what the markers mean. The brief, the context, a follow-up, a requested change, an edited report, each web page and each piece of deep research is also scanned for an attempt to instruct the agents (overriding their instructions, changing their role, asking for their instructions, posing as the system, hidden characters): the sentence is cut out of what the agents read and marked as removed, logged by its matched words, counted on the Monitor and in Prometheus, and named in the response's `guardrails` (for `/evaluate`, `/brief/prepare` and the proposal routes), which the pages show; the run goes on, and your own copy of the text keeps your words. Azure OpenAI's own content filter refuses a prompt it reads as harmful or a jailbreak; should it refuse one the scan missed, the error says so in plain words.

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"prompt": "Evaluate this startup idea in the AI healthcare space."}'
```

Send a follow-up by passing the `session_id` from the first response; only the specialists the follow-up affects rerun, and each builds on its earlier report. The follow-up's response reports only its own reviews, resolutions and metrics.

Each session also has a written report, kept by the API with the session (in PostgreSQL, or in memory without a database):

- `GET /reports` — every session's report, newest first.
- `GET /reports/{session_id}` — the report: a markdown section each for the strategy, the specialists' reports and the decisions on conflicts, with a `version`; once written, the investment `proposal`, its calculated `investment` metrics (revenue and OpEx by year, NPV, IRR, payback, break-even) and any failing `checks` on its figures.
- `PUT /reports/{session_id}` — save edited sections. Send the `version` you edited; if the report changed since, the save is refused with 409.
- `POST /reports/{session_id}/proposal` — the agents write the investment proposal from the report as it stands: executive summary, market and marketing, technical and operational architecture, financial plan, risk matrix and KPIs. Body: `version`, optional `reasoning`. About 1–1.5 minutes at the default efforts.
- `POST /reports/{session_id}/proposal/revise` — apply an instruction to one part (`part`: `executive`, `market`, `technical`, `risk` or `financial`) or to the whole proposal; the parts built on it are brought into line. Body: `version`, `instruction`, optional `part` and `reasoning`. About a minute for one part.
- `PUT /reports/{session_id}/proposal` — save an edited proposal (`version`, `proposal`).
- `POST /reports/{session_id}/reset` — rebuild the report from the session's latest results, dropping edits and the proposal.
- `GET /reports/{session_id}/pdf` — the report as a PDF: the investment proposal with charts once it is written, else the team's report.

### Run the UI

With the API running, start the Next.js frontend in [frontend/](frontend/):

```bash
cd frontend
npm run dev
```

It opens on http://localhost:3000, with three pages in the sidebar. The pages call the API through the app's own `/api` route: the app's server forwards each call to `BACKEND_URL` in `frontend/.env.local` (http://localhost:8000 by default) and adds `API_KEY`, so the key never reaches a browser.

- **Evaluate** — write a brief, fill in a decision template, or start from an example, and add optional context. **Check the brief** has the Chief of Staff research it on the web and ask what it needs to know; you review the facts it found (leaving out any that do not fit), answer or skip its questions, then **Run the team**. Untick "Research it and check the brief first" to run the team straight away (⌘/Ctrl+Enter sends it either way). Tick **Deep research for each specialist** to research every specialist's area and the main competitors on the web first; the specialists cite what they use, and the result's **Research** tab holds it all, with the credits it cost. While the team works, the page follows it step by step: what each agent finished, who is working now, the stages of the work and the time taken. The launch strategy is then set as a memo, with the team's reviews beside it and the specialists' reports, plan, reviews, conflicts and cost below. Follow-ups continue the same session, which is kept in the browser tab, so a reload does not lose it.
- **Reports** — each session's report, read on the page as a document. **Write the investment proposal** has the agents write it up following an investment-proposal template; it then reads as numbered chapters, as in the PDF, each with its charts, the agent that wrote it and an **Edit** button. **Open PDF** shows the document in a pop-up, where you can ask the team to revise one part or the whole proposal, and download it; **Revise with the team** opens it with the prompt ready. **More actions** rewrites the proposal or resets the report to the latest results, after asking.
- **How it works** — the system explained in pictures: the pipeline from a brief to a decision, the agents and what each reads and writes, how the Chief of Staff decides, how the critique works, where the facts come from, the stack, and where your judgement matters. **Show the diagrams** draws the real LangGraph graph, the data flow and the decision routes with Mermaid. The **Monitor** tab is a live dashboard of what the API has done: whether anything went wrong lately, the error rates, the median and 95th-percentile times, and a log of each step, warning and error. It keeps showing what it last heard if the API stops answering, and tries again less often until it does.

The sidebar's **Web research** switch picks where the web research runs: **Azure OpenAI**, the default (Bing search through the team's deployment, billed to Azure per search), or **Tavily**, for demanding tasks (deeper, from Tavily credits). A provider the server has not set up cannot be chosen, and the choice is remembered in the browser. Azure's web search sends the searches to Bing, outside Azure's compliance boundary.

The sidebar has two **Reasoning** sliders, for the specialists and for the Chief of Staff. They start at the configured efforts and apply to every request the pages send: higher reasoning gives more considered answers but slower calls (about 4 s a call at `minimal`, 9 s at `medium`, 27 s at `high`). With the specialists at `low`, the proposal's figures come out more consistent, for about a third more time. See [frontend/README.md](frontend/README.md) for more.

### Demo

Walk through a scenario end to end, printing each stage:

```bash
uv run python demo.py scenarios/healthcare_scheduling.json
```

### Test

```bash
uv run pytest                     # backend
uv run pytest --cov               # the same, with a coverage report; fails below 80%
cd frontend && npm test           # the frontend (npm run test:coverage fails below 80%)
```

Tests use a fake model, and the frontend's a fake backend, so they need no credentials and make no LLM calls. They keep sessions and reports in memory, whatever `.env` says; set `TEST_DATABASE_URL` to a database they may empty (`createdb cofounder_test`) and the PostgreSQL tests run too, through a restart of the API, else they are skipped.

### Configuration

Set in `.env` (see `.env.example`). `DEBUG_MODE` turns on DEBUG logging and LangGraph's step-by-step traces; `LOG_FORMAT=json` writes each log line as a JSON object for a log collector (`text` by default), and either way each line names its request and session; `DATABASE_URL` names the PostgreSQL database that keeps sessions, reports and the Monitor's history (the API will not start if it cannot reach it; unset, they are kept in memory); `MAX_ITERATIONS` and `MAX_CRITIQUE_ROUNDS` bound the review and critique loops (1 by default); `LLM_TIMEOUT` and `LLM_MAX_RETRIES` govern each LLM call, and `LLM_TIMEOUT_HIGH` replaces the timeout for calls at `high` reasoning. `AZURE_OPENAI_REASONING_EFFORT` sets how hard the four specialists reason, and `AZURE_OPENAI_CHIEF_REASONING_EFFORT` how hard the Chief of Staff reasons for its decisions (planning, review, resolving conflicts, synthesis); higher is slower. They are the defaults: the UI's sliders, or a request's `reasoning`, can choose others. On `gpt-5-mini` the maximum that takes effect is `high`: the API accepts `xhigh`, but the model then does no reasoning at all. `API_KEY` is the key callers must send (the frontend's server sends it; unset, the API is open to whoever can reach it, fine only on your own machine); `MAX_REQUEST_BYTES` (1,000,000), `REQUESTS_PER_MINUTE` (300), `RUNS_PER_HOUR` (30) and `MAX_CONCURRENT_RUNS` (4) set the limits above. `CORS_ORIGINS` lists the browser origins allowed to call the API directly (the frontend does not need it: it calls through its own server). Web research runs on Azure OpenAI with the settings above; `TAVILY_API_KEY` adds Tavily as a choice (a free key from [tavily.com](https://tavily.com) gives 1,000 credits a month; a brief's searches use two to four), `SEARCH_TIMEOUT` bounds each search (20 s), and `RESEARCH_TIMEOUT` each deep research task (300 s).

### Project structure

```
main.py                    FastAPI app: /health, /templates, /brief/prepare, /evaluate, /evaluate/stream, /reports
observability.py           Request IDs, text or JSON logs, and the access log
security.py                The API key, the size and rate limits, and the cap on runs at once
persistence.py             Where sessions, reports and the Monitor's history are kept: PostgreSQL or memory
guardrails.py              The founder's and the web's text fenced as data, and attempts to instruct the agents flagged
progress.py                What each step of the graph did, for the streamed evaluation
monitor.py                 What the API has done, for the Monitor and Prometheus
brief.py                   Preparing a brief: the templates, web research and questions
deep_research.py           Deep research for the specialists, and competitor profiles
providers.py               Where web research runs: Azure OpenAI or Tavily
azure_web.py               Azure OpenAI's web search: searches and research tasks
search.py                  Tavily: web search for a brief, research tasks for deep research
config.py                  Environment settings and loop/LLM limits
llm.py                     Chat model client (Azure OpenAI or OpenAI)
state.py                   Shared workflow state and structured models
graph.py                   LangGraph state machine
metrics.py                 Per-node run metrics
agents/roles.py            The four specialist role definitions
agents/specialist.py       Shared specialist node
agents/chief_of_staff.py   Plan, delegate, review, critique, synthesise
agents/proposal_writer.py  Writes and revises the investment proposal
proposal.py                The proposal's parts, and the metrics calculated from them
reports.py                 Each session's written report, and their store
report_pdf.py              Renders a report or proposal as a PDF
report_charts.py           The PDF's charts and visual blocks
assets/fonts/              DejaVu Sans, the PDF's font
scenarios/                 Startup scenarios for the demo and tests
templates/                 Decision templates to write a brief from
demo.py                    Scenario walkthrough script
frontend/                  Next.js frontend (Evaluate and Reports pages)
tests/                     Automated tests
docs/                      Architecture and performance docs
DEVELOPMENT_PLAN.md        Build sequence and status
```

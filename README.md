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

A Chief of Staff agent plans and delegates, four specialists (Marketing, Finance, Technical, Risk & Compliance) analyse the request in parallel, the Chief of Staff reviews and reconciles their reports, and a synthesis step produces one launch strategy. The workflow is a LangGraph state machine served by a FastAPI backend, with a Next.js frontend on top. [docs/architecture.md](docs/architecture.md) explains it in full, [docs/demo.md](docs/demo.md) walks through a demonstration with a recorded run, and [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) records how it was built step by step.

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

### Start it

`start.sh` starts the whole app with one command: locally, the default, or in Docker.

```bash
./start.sh            # asks how to run it and on which ports, then starts it
./start.sh local      # the API and the web app here; Ctrl+C stops both
./start.sh docker     # PostgreSQL, the API and the web app in containers
./start.sh stop       # stops the containers; the data stays
```

Locally it starts the API and the web app as under [Run the API](#run-the-api) and [Run the UI](#run-the-ui) (the API without reloading on edits), on ports 8000 and 3000 unless you choose others (`--api-port`, `--web-port`; a port in use is asked about again, with the next free one offered), and gives the web app's server the API's address and its key from `.env`, so `frontend/.env.local` needs neither. Each server's lines are labelled; one that fails to start, or stops, is reported and the other stopped with it. In Docker it runs the stack under [Run with Docker](#run-with-docker-optional), after offering to make `POSTGRES_PASSWORD` in `.env` if there is none; run again on a running stack, it offers to rebuild it from the checkout. Without a `.env` it offers to make one from `.env.example`. Either way the app answers on this machine only. It needs bash: on Windows, run it from WSL or Git Bash, or use the commands below.

### Run the API

```bash
uv run python main.py
```

The API listens on http://localhost:8000, with interactive docs at http://localhost:8000/docs.

- `GET /health` — health check, with the reasoning efforts a request can choose and the configured defaults, where web research can run, which look-ups are set up (`lookups`: FRED's figures, competitors' own pages), where sessions and reports are kept (`storage`: `postgres` or `memory`, and whether it answers; the status is `degraded` while the database does not), whether model calls are traced in Langfuse (`tracing`: `langfuse`, and how many of the app's `prompts` are registered there), and whether dictation is set up (`voice`: `dictation`).
- `GET /scenarios` — the example scenarios in `scenarios/`, each with a short title, to start a request from.
- `GET /pipeline` — how the team is set up, for the How it works page: the LangGraph graph as a Mermaid diagram, the specialists, and the rules the Chief of Staff decides by (the approval score, the revision and critique rounds, the word limits), read from the running code.
- `GET /monitoring` — what the API has done since it started: whether a warning or error was logged in the last 15 minutes, the evaluations running and ended (the median and 95th-percentile time to a decision), briefs and proposals, requests and server errors, the time (median and 95th percentile), model calls and tokens of each step of the graph, review and conflict counts, research costs, and a log of recent events, warnings and errors (Azure's retries among them), each naming its request. The statistics count since the API started; the latest evaluations and the log are kept in PostgreSQL, so a restart keeps them (in memory without a database).
- `GET /metrics` — the same counters and timings for [Prometheus](https://prometheus.io) to scrape, which keeps their history: requests by route and status with their time, evaluations finished and failed with theirs, each step's time, model calls and tokens, reviews, conflicts, research cost, model retries, warnings and errors, and the process's own figures. In the text format, or OpenMetrics when the scraper asks; not in the interactive docs.
- `GET /templates` — the decision templates in `templates/`: evaluate an idea, plan the go-to-market, set the price, get ready to raise, respond to a competitor. Each is a brief to fill in, with what to look up and ask for that decision.
- `GET /rates/{base}` — today's exchange rates from `base` to the app's other currencies: the European Central Bank's daily reference rates (fetched at most every six hours), with the UAE dirham and the Saudi riyal from their fixed pegs to the US dollar. The Reports page fills the conversion rate in from it; 503 if the ECB cannot be reached, and the founder types the rate instead.
- `POST /brief/prepare` — prepare a brief before the team runs it. The Chief of Staff plans a few web searches, Azure OpenAI's own web search (Bing, on the team's deployment) or [Tavily](https://tavily.com) runs them (`research_provider`: `azure`, the default, or `tavily`), and the Chief of Staff keeps the facts that bear on the decision, each citing its sources, and asks up to three questions about facts only the founder knows. Body: `prompt`, optional `context`, `template` and `reasoning`. Send the facts the founder keeps and their answers in the evaluation's `context` (`research`, `answers`), and every agent works from them; the report gains a "Web Research" section with the sources. About 10–30 s. With neither provider set up the brief is still checked, and `research_note` says why there is no research; a failed search never fails the request.
- `POST /evaluate` — run the founding team. Body: `prompt`, optional `context` (target market, constraints, competitive landscape), optional `session_id` for a follow-up, optional `reasoning` (`{"specialist": "low", "chief": "high"}`, each `minimal`, `low`, `medium` or `high`) to override the configured efforts for this request, optional `deep_research: true` to research each assigned specialist's area and profile up to three competitors on the web before the specialists start, and `research_provider` for where: `azure` (Azure OpenAI's web search: about half a minute and a few dozen Bing searches, billed to Azure) or `tavily` (Tavily's Research API, for demanding tasks: a minute or two and 150–450 Tavily credits). A follow-up reuses the session's research. The response holds the objective, the per-specialist assignments and analyses, the review history, any conflict resolutions, per-node metrics, the final strategy, the official figures looked up (`economic`), and the session's deep `research`, if any: a cited report per area, the competitor profiles, every source numbered once, and the credits used. A full evaluation takes about two minutes at the default efforts, 5–10 minutes with the Chief of Staff at `high`. Missing credentials return 503, and an LLM call that still fails after its retries returns 502.
- `POST /evaluate/stream` — the same evaluation, reported as it happens, as server-sent events. Each step of the graph (`plan`, each specialist, `review`, `critique`, `resolve`, `synthesis`) sends a `start` event and a `done` event; the `done` event carries a one-line summary, such as "Reviewed 4 reports: approved 3, sent back Financial Planning.", and the figures behind it. A `result` event with the body `/evaluate` returns ends the stream. A failure ends it with an `error` event carrying the status `/evaluate` would have returned (503, 502 or 500). The Evaluate page uses this to show the team at work.

Official figures, looked up through MCP servers. With `FRED_API_KEY` set, every evaluation looks up the official figures its plan turns on, beside deep research: the Chief of Staff names up to four searches of FRED, the St. Louis Fed's database (wages, prices, demand in the venture's market); the app's own FRED MCP server (`fred_server.py`, started by the API and spoken to over stdio) finds the series for each, the Chief of Staff picks those that fit the venture's market and place (a state's figures for a venture in that state), and the server reads them, with the 10-year Treasury yield and consumer prices every time; code works out each one's latest value and its change over the year. Every specialist reads them and cites them as `[FRED · DGS10]`; the response's `economic` holds them, the report gains an "Economic Data" section, and a follow-up reuses them. With deep research on Tavily, Tavily's hosted MCP server also finds and reads each competitor's own pricing page, cited in its profile (`site`), for about four more credits. A look-up that fails is left out with a note, and never fails the run.

The founder's documents: files and earlier reports the team works from, and questions about them.

- `POST /transcribe` — the founder's dictation written down in English: the recording as the body (WebM, Ogg, MP4 or M4A, MP3, WAV or FLAC, as its `Content-Type` says, up to 10 MB), sent to Azure OpenAI's Whisper, the speech-to-text model that also translates (its translation route: spoken in any language, English comes back), and not kept. Returns `{"text": ...}`; 503 without Azure OpenAI, 415 for another format, 422 for an empty recording, 502 with what Azure answered when the call fails (a missing deployment says what to deploy). Traced in Langfuse as `transcribe`.
- `POST /uploads?name=plan.pdf` — upload a file for the team to work from, its bytes as the body (up to 10 MB): PDF, Word, PowerPoint, Excel, OpenDocument, CSV, RTF, HTML, Markdown or text, the type told from the content, not the name. Only its text is kept (with the session's data, in PostgreSQL or memory; the newest 500 uploads), as passages that each say where they are: a page, a slide, a sheet's rows, a section's heading. Returns its `upload` (`id`, `kind`, `parts` such as "12 pages", `warnings`, a `preview`) and any `guardrails` flags. A scanned PDF without text, a password-protected one, an older Office file (.doc, .xls, .ppt), an image or an archive that unpacks too far is refused with 422 and why. `GET /uploads/{id}` says what was read.
- Name uploads and earlier reports in a brief's or an evaluation's `context`: `"uploads": [id, ...]` and `"reports": [session_id, ...]`, up to five of each (404 for one that is not there). Each agent reads the passages that bear on its own work (ranked by BM25 within a budget that each document gets an equal share of, so a long report cannot crowd out a short file), fenced as the founder's, and cites each it uses by its mark: `[D1 · page 3]` for the first upload, `[R1 · Launch Strategy]` for the first report. The Chief of Staff's questions take them into account. The report gains a "The Founder's Documents" section and records them in `worked_from`; a follow-up keeps them.
- `POST /ask` — ask the Chief of Staff a question about uploads and reports. Body: `question`, `uploads`, `reports`, optional `reasoning`. It answers from their passages alone, citing each, and says what they do not cover; the response holds the `answer` (markdown) and the `sources` it cites, each with its `mark`, document `name`, `where` and `text`. About 10–20 s.
- `POST /feedback` — the founder's verdict on a strategy, as a score in Langfuse. Body: `session_id`, the run's `trace_id` (from its response), `useful` (true or false) and an optional `comment`. Answers 202 with `recorded`: false when Langfuse is not set up.

Every response carries an `X-Request-ID` header: the ID the request sent, if it is 8–64 letters, digits, dots, dashes or underscores, else a new one. Every log line written while the request was handled names it, as do the Monitor's warnings and errors, so the ID an error shows leads to its lines in the logs. An error the API did not expect answers 500 with `{"detail": ..., "request_id": ...}`.

With `API_KEY` set, every route but `/health` needs it, as `Authorization: Bearer <key>` (or `X-API-Key`); `/metrics` too, so give Prometheus the key. The API also limits what one caller can do: a body over `MAX_REQUEST_BYTES` is refused (413), but an uploaded file may be up to 10 MB; each caller may send `REQUESTS_PER_MINUTE` requests a minute and start `RUNS_PER_HOUR` evaluations, briefs, proposals and questions an hour; and at most `MAX_CONCURRENT_RUNS` run at once. Over a limit the answer is 429 with `Retry-After`. A request may hold only what a brief needs: a prompt or instruction of 8,000 characters, context fields of 4,000, ten answers, twenty facts and fifty sources, each source a web address (422 otherwise).

The founder's text and the web's are the material of the team's work, never instructions to it. Every agent reads them between `<untrusted>` markers that name their source, cleaned of invisible characters and unable to close their markers early, and every agent's system prompt says what the markers mean. The brief, the context, a follow-up, a requested change, an edited report, an uploaded file, a question, each web page and each piece of deep research is also scanned for an attempt to instruct the agents (overriding their instructions, changing their role, asking for their instructions, posing as the system, hidden characters): the sentence is cut out of what the agents read and marked as removed, logged by its matched words, counted on the Monitor and in Prometheus, and named in the response's `guardrails` (for `/evaluate`, `/brief/prepare`, `/uploads`, `/ask` and the proposal routes), which the pages show; the run goes on, and your own copy of the text keeps your words. Azure OpenAI's own content filter refuses a prompt it reads as harmful or a jailbreak; should it refuse one the scan missed, the error says so in plain words.

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"prompt": "Evaluate this startup idea in the AI healthcare space."}'
```

Send a follow-up by passing the `session_id` from the first response; only the specialists the follow-up affects rerun, and each builds on its earlier report. The follow-up's response reports only its own reviews, resolutions and metrics.

Each session also has a written report, kept by the API with the session (in PostgreSQL, or in memory without a database):

- `DELETE /reports/{session_id}` — delete a report for good: with its versions, the results it was built from and the team's saved state for the session. 204, or 404 if there is no such report. The founder's uploaded files stay.
- `GET /reports` — every session's report, newest first, each with what tells it from the others: its `objective`, its `verdict` (the proposal's, else the one its strategy leads with), the proposal's `project_name` and headline `figures` (NPV, IRR, payback, break-even), how many figures disagree (`checks`), its `currency`, who it is `prepared_by`, the specialists in its `team`, its `sections`, the founder's `documents` it worked from, its last `change`, `version`, and whether it was `edited` or is `outdated`; and a `brief` (markdown: the proposal's recommendation and financial case, else the opening of the strategy) with its `key_figures` (the proposal's calculated from its plan, else the ones the strategy and Finance name), made by code.
- `GET /reports/{session_id}` — the report: a markdown section each for the strategy, the specialists' reports and the decisions on conflicts, with a `version`; its `settings` (the `currency` every amount is in, the `units` its measurements were last converted to, who it is `prepared_by`, the sections `hidden` from the document) and the `change` that made this version; once written, the investment `proposal`, its calculated `investment` metrics (revenue and OpEx by year, NPV, IRR, payback, break-even) and any failing `checks` on its figures.
- `PUT /reports/{session_id}` — save edited sections. Send the `version` you edited; if the report changed since, the save is refused with 409.
- `POST /reports/{session_id}/proposal` — the agents write the investment proposal from the report as it stands: executive summary, market and marketing, technical and operational architecture, financial plan, risk matrix and KPIs. Body: `version`, optional `reasoning` and `currency` (an ISO code, else the report's). About 1–1.5 minutes at the default efforts.
- `POST /reports/{session_id}/proposal/revise` — apply an instruction to one part (`part`: `executive`, `market`, `technical`, `risk` or `financial`) or to the whole proposal; the parts built on it are brought into line. Body: `version`, `instruction`, optional `part` and `reasoning`. About a minute for one part. Returns a `draft`, saved only when accepted.
- `POST /reports/{session_id}/revise` — rewrite one text of the report, or only a `passage` of it, as asked: the agent who wrote it rewrites just that and leaves everything else alone. Body: `version`, `path` (`sections.strategy`, `proposal.market.pricing_strategy`...), `instruction`, optional `passage` and `reasoning`. Returns a `draft`.
- `POST /reports/{session_id}/drafts` — a change made exactly by code, as a `draft`: `{"kind": "currency", "to": "EUR", "rate": 0.92}` converts every figure and every amount in the text (`"relabel": true` only shows them in the new currency); `{"kind": "units", "to": "metric"}` converts measurements in the text; `replace` (`find`, `by`, `match_case`, `whole_words`), `redact` (`terms`), `remove` (`path`, `passage`) and `settings` (`prepared_by`, `hidden`). Body: `version`, `change`. A change that would change nothing is refused with 422 and why.
- `POST /reports/{session_id}/accept` — save a draft (`version` it was made from, `content`, `change`); 409 if the report moved on. The version it replaces is kept.
- `GET /reports/{session_id}/versions`, `GET .../versions/{version}`, `POST .../versions/{version}/restore` — the current version and the last 30 before it, each with the change that made it, how many fields it `changed` from the version before it and the `areas` of the report they are in; one as it was; one made the newest again (body: the current `version`).
- `GET /reports/{session_id}/choices` — what the founder chose and told the team while the report was built: the request (`brief`) and the latest `follow_up`, its `target_market`, `constraints` and `competitive_landscape`, their `answers` to the Chief of Staff's questions, the `research` facts they kept with their sources, their `documents`, whether the team did `deep_research` and where (`research_provider`), and the reasoning `efforts` it ran at. Kept with each evaluation's results; a report built before that has them from the session's saved state, else only its brief, facts and documents (`complete` false).
- `GET /reports/{session_id}/versions/{version}/changes` — what changed in a version, field by field, from the version before it (`since`), each value before and after, with the currencies of the amounts before and after; nothing to compare when that version is no longer kept.
- `PUT /reports/{session_id}/proposal` — save an edited proposal (`version`, `proposal`).
- `POST /reports/{session_id}/reset` — rebuild the report from the session's latest results, dropping edits and the proposal.
- `GET /reports/{session_id}/pdf` — the report as a PDF: the investment proposal with charts once it is written, else the team's report, every amount in its currency. `POST` with a draft's or a version's `content` draws that instead, saving nothing.

### Run the UI

With the API running, start the Next.js frontend in [frontend/](frontend/):

```bash
cd frontend
npm run dev
```

It opens on http://localhost:3000, with three pages in the sidebar. The pages call the API through the app's own `/api` route: the app's server forwards each call to `BACKEND_URL` in `frontend/.env.local` (http://localhost:8000 by default) and adds `API_KEY`, so the key never reaches a browser.

- **Evaluate** — write a brief, fill in a decision template, or start from an example, and add optional context. Under **Documents**, add files (choose them or drop them on the page: a plan, a deck, figures) and earlier reports from the app; each shows what was read of it and the mark the agents cite it by (D1, R1), and the result names them and sets each citation as a tag that names its document. **Check the brief** has the Chief of Staff research it on the web and ask what it needs to know; you review the facts it found (leaving out any that do not fit), answer or skip its questions, then **Run the team**. Untick "Research it and check the brief first" to run the team straight away (⌘/Ctrl+Enter sends it either way). Tick **Deep research for each specialist** to research every specialist's area and the main competitors on the web first; the specialists cite what they use, and the result's **Research** tab holds it all, with the credits it cost, beside the official figures looked up on FRED (each with its change over the year and a link to it there); a figure the agents cite is a tag that opens its page on FRED. While the team works, the page follows it step by step: what each agent finished, who is working now, the stages of the work and the time taken. **Live graph**, in the progress card, opens the graph LangGraph runs in the agents' colours, lit up as the team works: the step at work glows, the arrows the work moves along run, each finished step is ticked (or counted when it ran again), and a sidebar says what the team is doing now and each step it has taken; it stays open on the finished run. The launch strategy is then set as a memo, with the team's reviews beside it and the specialists' reports, plan, reviews, conflicts and cost below. Follow-ups continue the same session, which is kept in the browser tab, so a reload does not lose it.
- **Reports** — each session's report, read on the page as a document. **Browse**, beside the title, lists every report with what tells them apart (its verdict, decision, headline figures, team, version and date), searchable and filtered, with a preview of each: its decision in brief, with the figures picked out, its key figures at a glance, your choices while it was built (your brief and its details, your answers to the Chief of Staff's questions, the research facts you kept, your documents and how the team ran, with your figures picked out), and its versions, each with what it changed from the one before, opened field by field with words struck through and highlighted and amounts before and after. The preview's title bar, in view however far the preview scrolls, has **Open this report** and **Delete**, which deletes it once you confirm; **More actions** deletes the open one. **Write the investment proposal** has the agents write it up following an investment-proposal template; it then reads as numbered chapters, as in the PDF, each with its charts, the agent that wrote it and an **Edit** button. Each paragraph has **Revise** and **Remove** buttons: its writer rewrites just that paragraph as you ask, or it is taken out. **Open PDF** opens the document studio on a page of its own, the whole window beside the sidebar: the PDF beside its tools, which fold into a strip of icons to leave the PDF the page, with **Back to the report** (or the browser's Back button) to return to the report as you left it. **Revise** asks the team to revise one part or the whole proposal; **Settings** converts the currency (every figure and every amount in the text, by code, at today's rate, filled in from the European Central Bank, or one you give, or only relabelled) and the units (imperial or metric), and sets who the document is from and which of the team's sections it leaves out; **Text** finds and replaces (a renamed product, say) or redacts names and figures everywhere, the PDF included; **History** lists every version with what changed it, to look at and restore. Every change, the team's included, comes back as a draft: each changed word struck through or highlighted, each amount before and after, and its PDF, saved only when you accept it. The proposal can be written in any of 22 currencies. **Ask about it** puts questions to the report, the files its run worked from and any other files or reports you add: the Chief of Staff answers from them alone, citing each passage, and lists the passages under the answer. **More actions** rewrites the proposal or resets the report to the latest results, after asking.
- **Dictation** — a mic in each input box, on both pages: the brief and its template's fields, the context, the follow-up, your answers, the feedback, what to change in the proposal or a passage, Ask about it, who the document is from, find and replace, and the report search. Press it and speak, in any language (the bars, one in each agent's colour, follow your voice); press it again or Enter, and Azure OpenAI's Whisper writes it down in English where the cursor was. Escape throws the recording away; nothing of it is kept. It needs a Whisper deployment (see below), and says what to deploy when there is none.
- **How it works** — the system explained in pictures: the pipeline from a brief to a decision, the agents and what each reads and writes, how the Chief of Staff decides, how the critique works, where the facts come from, the stack, and where your judgement matters. **Show the diagrams**, under the pipeline, draws the real LangGraph graph, the data flow and the decision routes with Mermaid, each in the agents' colours: every step in the colours of who runs it, the graph's arrows in the colour of the step they leave, the data flow's stretches on bands of who does them, and a legend under each. The **Monitor** tab is a live dashboard of what the API has done: whether anything went wrong lately, the error rates, the median and 95th-percentile times, and a log of each step, warning and error. It keeps showing what it last heard if the API stops answering, and tries again less often until it does.

Each agent has a colour, worn by everything it does: violet for the Chief of Staff, orange for Marketing, aqua for Finance, blue for Technical, magenta for Risk & Compliance. The team's progress, the activity log, the reviews, the reports and chapters, the agents the strategy cites and the Monitor all show who by colour as well as by name.

The button beside the mark folds the sidebar into a narrow rail of the pages' icons, so a page (the document's above all) takes nearly the whole window, and opens it out again; the browser remembers it.

The sidebar's **Appearance** switch picks light, dark (a mid grey, so the colours stay clear) or the system's setting, and the browser remembers it.

The sidebar's **Web research** switch picks where the web research runs: **Azure OpenAI**, the default (Bing search through the team's deployment, billed to Azure per search), or **Tavily**, for demanding tasks (deeper, from Tavily credits). A provider the server has not set up cannot be chosen, and the choice is remembered in the browser. Azure's web search sends the searches to Bing, outside Azure's compliance boundary.

The sidebar has two **Reasoning** sliders, for the specialists and for the Chief of Staff. They start at the configured efforts and apply to every request the pages send: higher reasoning gives more considered answers but slower calls (about 4 s a call at `minimal`, 9 s at `medium`, 27 s at `high`). With the specialists at `low`, the proposal's figures come out more consistent, for about a third more time. See [frontend/README.md](frontend/README.md) for more.

### Run with Docker (optional)

Docker is an option beside running the app locally: the API, the web app and PostgreSQL run together with [Docker Compose](https://docs.docker.com/compose/), with nothing to install but Docker. `./start.sh docker` does it for you; by hand:

```bash
cp .env.example .env          # fill in the model's keys, API_KEY and POSTGRES_PASSWORD
docker compose up --build     # then open http://localhost:3000
```

Compose builds two images, the API from `Dockerfile` and the web app from `frontend/Dockerfile`, starts PostgreSQL with its data in the `db` volume, and starts each service once the one it needs is healthy. The web app and the API are published on 127.0.0.1 only: the browser reaches the API through the web app, and Prometheus (`/metrics`, with the key) and checks reach it on 127.0.0.1:8000. The API logs JSON lines (`docker compose logs -f api`), runs one worker, and gives the evaluations still running 30 s to finish when it stops. Keys and passwords are read from `.env` when the containers start and never enter an image, and both images run as users without privileges. `WEB_PORT` and `API_PORT` change the ports, and `WEB_HOST=0.0.0.0` opens the web app to the network; before it faces the internet, put a reverse proxy that terminates HTTPS in front of it.

### Demo

Walk through a scenario end to end, printing each stage:

```bash
uv run python demo.py scenarios/healthcare_scheduling.json
```

[docs/demo.md](docs/demo.md) is a script for a live walkthrough in the web app, with a recorded run of an evaluation and its refinement.

### Tracing and experiments with Langfuse (optional)

With `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in `.env` (a free [Langfuse Cloud](https://cloud.langfuse.com) project is enough), every request that calls the model is a trace in Langfuse: an evaluation (with each step of the graph and, in each, its model calls, their prompts, replies, tokens and cost), a brief, the proposal and its revisions, a passage rewritten, a question. Traces are grouped by session, so a follow-up sits beside the request it refines, and tagged (first request or follow-up, deep research, a template, a proposal part). Email addresses, phone numbers, card numbers and keys are masked before anything leaves the app.

The prompts stay in the code: at start-up each of the app's 22 is registered in Langfuse (`prompt_library.py`), as a new version labelled `production` when its text has changed, and every call is linked to the version it used, so Langfuse compares prompt versions on cost, speed and scores. Each evaluation is scored with the team's own judgements: the Chief of Staff's review of each report (`review-marketing`, ... and `review-average`), whether every report passed first time, how many were revised, the conflicts settled, the `verdict`, failed specialists and guardrail flags. The founder's verdict on a strategy (useful or not, with a comment) is scored too, from the result's **Was this strategy useful?**, and the result links to its trace. With `LANGFUSE_JUDGE=true`, an LLM judge (`judge.py`) also scores each strategy on constraints, consistency, actionability and grounding, after the answer has gone.

To compare a change (a prompt, the reasoning efforts) with the runs before it, run the team on the example scenarios as a Langfuse experiment: they become the `cofounder-scenarios` dataset, each run is traced and scored by the team's judgements and the LLM judge, and Langfuse shows the runs side by side. It calls the real model, about two minutes a scenario:

```bash
uv run python experiments.py --name "chief at low" --chief low
```

### Test

```bash
uv run pytest                     # backend
uv run pytest --cov               # the same, with a coverage report; fails below 80%
cd frontend && npm test           # the frontend (npm run test:coverage fails below 80%)
```

Tests use a fake model, and the frontend's a fake backend, so they need no credentials and make no LLM calls. They keep sessions and reports in memory, whatever `.env` says; set `TEST_DATABASE_URL` to a database they may empty (`createdb cofounder_test`) and the PostgreSQL tests run too, through a restart of the API, else they are skipped.

On GitLab, `.gitlab-ci.yml` runs the backend's tests (with a PostgreSQL service, so the persistence tests run too) and the frontend's lint, types, tests and build on every push and merge request, and builds both images on the default branch; that job needs a runner that allows Docker-in-Docker, and, Docker being an option, its failure does not fail the pipeline. `tests/test_start.py` covers the launcher's questions, ports and edits to `.env`.

### Configuration

Set in `.env` (see `.env.example`). `DEBUG_MODE` turns on DEBUG logging and LangGraph's step-by-step traces; `LOG_FORMAT=json` writes each log line as a JSON object for a log collector (`text` by default), and either way each line names its request and session; `DATABASE_URL` names the PostgreSQL database that keeps sessions, reports and the Monitor's history (the API will not start if it cannot reach it; unset, they are kept in memory); `MAX_ITERATIONS` and `MAX_CRITIQUE_ROUNDS` bound the review and critique loops (1 by default); `LLM_TIMEOUT` and `LLM_MAX_RETRIES` govern each LLM call, and `LLM_TIMEOUT_HIGH` replaces the timeout for calls at `high` reasoning. `AZURE_OPENAI_REASONING_EFFORT` sets how hard the four specialists reason, and `AZURE_OPENAI_CHIEF_REASONING_EFFORT` how hard the Chief of Staff reasons for its decisions (planning, review, resolving conflicts, synthesis); higher is slower. They are the defaults: the UI's sliders, or a request's `reasoning`, can choose others. On `gpt-5-mini` the maximum that takes effect is `high`: the API accepts `xhigh`, but the model then does no reasoning at all. `API_KEY` is the key callers must send (the frontend's server sends it; unset, the API is open to whoever can reach it, fine only on your own machine); `MAX_REQUEST_BYTES` (1,000,000), `REQUESTS_PER_MINUTE` (300), `RUNS_PER_HOUR` (30) and `MAX_CONCURRENT_RUNS` (4) set the limits above. `CORS_ORIGINS` lists the browser origins allowed to call the API directly (the frontend does not need it: it calls through its own server). Web research runs on Azure OpenAI with the settings above; `TAVILY_API_KEY` adds Tavily as a choice (a free key from [tavily.com](https://tavily.com) gives 1,000 credits a month; a brief's searches use two to four), `SEARCH_TIMEOUT` bounds each search (20 s), and `RESEARCH_TIMEOUT` each deep research task (300 s). `FRED_API_KEY` (free from [FRED](https://fredaccount.stlouisfed.org)) turns on the official figures; `LOOKUP_TIMEOUT` bounds each MCP look-up (30 s), and `TAVILY_MCP_URL` names Tavily's MCP server (its hosted one by default). `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` turn on tracing in Langfuse, `LANGFUSE_BASE_URL` names its region or server (`https://cloud.langfuse.com`, the EU, by default), `LANGFUSE_TRACING_ENVIRONMENT` and `LANGFUSE_RELEASE` label the traces, `LANGFUSE_SAMPLE_RATE` traces a share of requests, and `LANGFUSE_JUDGE` has the LLM judge score live strategies. Dictation uses a Whisper deployment on the same Azure OpenAI resource, named `whisper` (Azure's default) unless `AZURE_OPENAI_TRANSCRIPTION_DEPLOYMENT` names another; a deployment of a model that cannot translate (`gpt-4o-transcribe`) writes the words down as spoken instead. `AZURE_OPENAI_TRANSCRIPTION_API_VERSION` is the API version for it (`2024-10-21` by default).

### Project structure

```
main.py                    FastAPI app: /health, /templates, /brief/prepare, /evaluate, /evaluate/stream, /reports, /uploads, /ask
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
reports.py                 Each session's written report, its settings, its versions, and their store
document.py                Changes code makes exactly, as drafts: conversions, replace, redact, remove
currency.py                Money in the report's currency: shown, and converted in text
rates.py                   Today's exchange rates, from the European Central Bank
tracing.py                 Tracing, prompts and scores in Langfuse; what is masked
prompt_library.py          The app's prompts, by their names in Langfuse
judge.py                   An LLM judge of a strategy, for Langfuse's scores
units.py                   Measurements in text, imperial or metric
lookups.py                 Look-ups through MCP servers: FRED's official figures, competitors' own pricing pages
fred_server.py             The app's own MCP server for FRED, the St. Louis Fed's economic data
extract.py                 The text of an uploaded file, as passages: PDF, Office, OpenDocument, CSV, text
library.py                 The founder's documents: uploads kept, passages chosen for each agent, questions answered
report_pdf.py              Renders a report or proposal as a PDF
report_charts.py           The PDF's charts and visual blocks
assets/fonts/              DejaVu Sans, the PDF's font
scenarios/                 Startup scenarios for the demo and tests
templates/                 Decision templates to write a brief from
demo.py                    Scenario walkthrough script
experiments.py             The scenarios as a Langfuse experiment, scored
frontend/                  Next.js frontend (Evaluate, Reports and How it works pages)
start.sh                   Starts the app: locally, or in Docker
Dockerfile                 The API's image
docker-compose.yml         PostgreSQL, the API and the web app together
.gitlab-ci.yml             The checks on every push, and the images on the default branch
tests/                     Automated tests
docs/                      Architecture, performance and demo docs
DEVELOPMENT_PLAN.md        Build sequence and status
```

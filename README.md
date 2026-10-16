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

A Chief of Staff agent plans and delegates, four specialists (Marketing, Finance, Technical, Risk & Compliance) analyse the request in parallel, the Chief of Staff reviews and reconciles their reports, and a synthesis step produces one launch strategy. The workflow is a LangGraph state machine served by a FastAPI backend, with a Streamlit UI on top and a Next.js frontend scaffolded to replace it. [docs/architecture.md](docs/architecture.md) explains it in full, and [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) records how it was built step by step.

### Setup

Requires [uv](https://docs.astral.sh/uv/); it installs Python 3.12 and the dependencies.

```bash
uv sync
cp .env.example .env
```

Fill in `.env` with Azure OpenAI or OpenAI credentials. The provider is chosen by which credentials are set.

For the Streamlit UI, also install the optional `ui` group:

```bash
uv sync --group ui
```

### Run the API

```bash
uv run python main.py
```

The API listens on http://localhost:8000, with interactive docs at http://localhost:8000/docs.

- `GET /health` — health check.
- `POST /evaluate` — run the founding team. Body: `prompt`, optional `context` (target market, constraints, competitive landscape), and optional `session_id` for a follow-up. The response holds the objective, the per-specialist assignments and analyses, the review history, any conflict resolutions, per-node metrics, and the final strategy. A full evaluation takes about a minute. Missing credentials return 503, and an LLM call that still fails after its retries returns 502.

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Evaluate this startup idea in the AI healthcare space."}'
```

Send a follow-up by passing the `session_id` from the first response; only the specialists the follow-up affects rerun, and each builds on its earlier report. The follow-up's response reports only its own reviews, resolutions and metrics.

Each session also has a written report, kept by the API (in memory, like the sessions):

- `GET /reports` — every session's report, newest first.
- `GET /reports/{session_id}` — the report: a markdown section each for the strategy, the specialists' reports and the decisions on conflicts, with a `version`.
- `PUT /reports/{session_id}` — save edited sections. Send the `version` you edited; if the report changed since, the save is refused with 409.
- `POST /reports/{session_id}/detailed` — each specialist expands its section and the Chief of Staff the strategy (about a minute).
- `POST /reports/{session_id}/reset` — rebuild the report from the session's latest results, dropping edits.
- `GET /reports/{session_id}/pdf` — the report as a PDF.

### Run the UI

With the API running, start the Streamlit UI, the working UI for now:

```bash
uv run --group ui streamlit run streamlit_app.py
```

It opens on http://localhost:8501, with two pages in the sidebar. It finds the API at `API_URL` (http://localhost:8000 by default).

- **Evaluate** — pick a scenario or describe an idea, add optional context, and run the team; once the strategy is shown, send follow-ups in the same session.
- **Reports** — each session's written report. Edit its sections on the left while the PDF preview on the right follows (a change is saved when you click out of its box). **Write the detailed version** has the agents expand their short reports into full sections, **Reset to the latest results** starts again from the evaluation, and **Download PDF** saves it.

The Next.js frontend in [frontend/](frontend/) is a scaffold that will replace the Streamlit UI: it is wired to the API but has no evaluation UI yet. See [frontend/README.md](frontend/README.md) to run it.

### Demo

Walk through a scenario end to end, printing each stage:

```bash
uv run python demo.py scenarios/healthcare_scheduling.json
```

### Test

```bash
uv run pytest              # backend
uv run --group ui pytest   # backend and the Streamlit UI
```

Tests use a fake model, so they need no credentials and make no LLM calls. Without the `ui` group the Streamlit UI tests are skipped.

### Configuration

Set in `.env` (see `.env.example`). `DEBUG_MODE` turns on DEBUG logging and LangGraph's step-by-step traces; `MAX_ITERATIONS` and `MAX_CRITIQUE_ROUNDS` bound the review and critique loops (1 by default); `LLM_TIMEOUT` and `LLM_MAX_RETRIES` govern each LLM call. `CORS_ORIGINS` lists the browser origins allowed to call the API (the Next.js dev server, http://localhost:3000, by default), and `API_URL` tells the Streamlit UI where the API is.

### Project structure

```
main.py                    FastAPI app: /health, /evaluate, /reports
config.py                  Environment settings and loop/LLM limits
llm.py                     Chat model client (Azure OpenAI or OpenAI)
state.py                   Shared workflow state and structured models
graph.py                   LangGraph state machine
metrics.py                 Per-node run metrics
agents/roles.py            The four specialist role definitions
agents/specialist.py       Shared specialist node
agents/chief_of_staff.py   Plan, delegate, review, critique, synthesise
agents/report_writer.py    Detailed version of a report, on demand
reports.py                 Each session's written report, and their store
report_pdf.py              Renders a report as a PDF
assets/fonts/              DejaVu Sans, the PDF's font
scenarios/                 Startup scenarios for the demo and tests
demo.py                    Scenario walkthrough script
streamlit_app.py           Streamlit UI: navigation and sidebar
ui/                        Streamlit pages (Evaluate, Reports) and API client
frontend/                  Next.js frontend (scaffold)
tests/                     Automated tests
docs/                      Architecture and performance docs
DEVELOPMENT_PLAN.md        Build sequence and status
```

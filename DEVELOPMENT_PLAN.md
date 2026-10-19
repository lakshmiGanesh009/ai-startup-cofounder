# Development Plan

Build sequence for the AI Startup Co-Founder Team capstone. The brief is the top section of [README.md](README.md).

We build one step at a time. Each step adds one feature, is small enough to review in one sitting, and ends with checks anyone can run.

**Where we are:** Steps 0-11 are done and verified live against Azure OpenAI on 2026-10-16 (see [Live verification](#live-verification)). The live runs found bugs the fake-model tests could not; they are fixed, each with a test. Step 12 made the API about twice as fast, Step 13 added a Streamlit UI and scaffolded the Next.js frontend, Step 15 added written reports: edited beside a live PDF preview, with a detailed version on demand, Step 16 sharpened every prompt and gave the Chief of Staff deeper reasoning, and Step 17 turned the report into an investment proposal with charts, revisable by instruction from a PDF pop-up, and added reasoning sliders. Step 14 built the Next.js UI's Evaluate and Reports pages; the Streamlit UI retires once the user has checked them. The tests cover 99% of the backend and Streamlit UI, and over 90% of the Next.js frontend; both fail below 80%.

## How we work

1. Take the next step in the status table and build only what it lists.
2. Run its checks: the automated tests first, then the live check against a real model.
3. A reviewer confirms every "Done when" item.
4. Mark the step Done in the status table in the same change.

Automated tests use a fake model, so they need no credentials and make no LLM calls. Live checks need a filled-in `.env`.

## Decisions

Each decision went with its recommended option A, and the steps were built that way. Choosing another option later changes the steps named in its heading.

### D1. Which reasoning loop? (affects Steps 6 and 7)

The brief asks for "ReAct or Plan--Act--Check loops".

- **A (recommended): Plan-Act-Check across the team.** The Chief of Staff plans, the specialists act, and the Chief of Staff checks their reports and sends weak ones back with feedback. This is the hierarchical loop the brief describes, and it needs no external tools.
- **B: also ReAct inside each specialist**, with tools such as web search for market data. The output is better grounded, but it adds a search dependency, more LLM calls and more to debug. It can be added after Step 8 if time allows.

**Chosen: A.** No specialist uses external tools.

### D2. Which LLM providers? (affects Step 1)

The team has Azure OpenAI credentials. The brief's variable table lists `OPENAI_API_KEY`, `MODEL_NAME` and an optional `ANTHROPIC_API_KEY`, and does not mention Azure.

- **A (recommended): Azure OpenAI and OpenAI.** Both use the same library. The provider is chosen by which credentials are in `.env`, and `MODEL_NAME` is honoured. Anthropic is added only if someone will run on it.
- **B: Azure OpenAI, OpenAI and Anthropic.** Matches the brief's full table, at the cost of one more dependency and a code path nobody on the team can test live.
- **C: Azure OpenAI only.** Simplest, but ignores the brief's variables.

**Chosen: A.** See `llm.py`.

### D3. Are follow-up requests in scope? (affects Step 8)

The brief's third sample prompt, "Refine the pricing strategy after financial review.", only makes sense as a follow-up to an earlier run, and the demonstration deliverable asks for an "iterative refinement example".

- **A (recommended): yes.** A session keeps the earlier reports, and a follow-up reruns only the specialists it affects.
- **B: no.** Every request is independent. Step 8 is dropped, and the refinement example is shown through the review loop of Step 6 alone.

**Chosen: A.** Built in Step 8.

### D4. One specialist implementation or four? (affects Steps 2 and 3)

- **A (recommended): one shared specialist node driven by four role definitions.** The four agents differ only in their role text, so this avoids four near-identical files.
- **B: one module per agent.** More duplication, but easier to divide between pairs, and the better fit if D1 goes to option B and the agents get different tools.

**Chosen: A.** See `agents/specialist.py` and `agents/roles.py`.

## Workflow

The workflow as built. Each box names the step that built it. Review comes before cross-critique, so specialists only critique reports that passed review. The exact state machine, generated from the code, is in [docs/architecture.md](docs/architecture.md).

```mermaid
graph TD
    IN([Founder request]) --> PLAN["Chief of Staff: plan (Step 4)"]
    PLAN -.->|assigned specialists only| SPEC["Specialists in parallel (Steps 2-3)<br/>Marketing, Finance, Technical, Risk"]
    SPEC --> REVIEW{"Chief of Staff: review (Step 6)"}
    REVIEW -.->|needs work, with feedback| SPEC
    REVIEW -->|approved| CROSS["Cross-critique, Chief of Staff resolves (Step 7)"]
    CROSS -.->|revise to match a decision, once| SPEC
    CROSS --> SYN["Chief of Staff: synthesis (Step 5)"]
    SYN --> OUT([Unified launch strategy])
```

## Status

| Step | Feature | Brief requirement it covers | Status |
| --- | --- | --- | --- |
| 0 | Project scaffold | Python environment, backend service, environment configuration | Done |
| 1 | LLM connection | LLM API access, environment variables | Done |
| 2 | First specialist, end to end | Role-based agent, state machine, backend API | Done |
| 3 | All four specialists in parallel | Marketing, Financial, Technical and Risk & Compliance agents | Done |
| 4 | Chief of Staff: plan and delegate | Manager-led delegation, structured outputs | Done |
| 5 | Chief of Staff: synthesis | Synthesis into a unified launch strategy | Done |
| 6 | Review and refine loop | Plan--Act--Check loop, reflection and critique cycles | Done |
| 7 | Cross-specialist critique | Back-and-forth between agents, conflict resolution | Done |
| 8 | Follow-up requests | Stateful system, iterative refinement | Done |
| 9 | Scenarios and demo | Testing with multiple scenarios, live walkthrough | Done |
| 10 | Optimization and error handling | Fewer redundant calls, latency, error handling strategy | Done |
| 11 | Documentation | Architecture diagram, role definitions, workflow, trade-offs | Done |
| 12 | Faster API | Improved latency, reduction of redundant reasoning calls | Done |
| 13 | Streamlit UI and Next.js scaffold | Live walkthrough, backend service for a frontend | Done |
| 14 | Next.js UI | Live walkthrough; replaces the Streamlit UI | Built: Evaluate and Reports pages; Streamlit retires once checked |
| 15 | Reports: editor, detailed version and PDF | Synthesis into a cohesive strategy document | Done |
| 16 | Sharper prompts, deeper Chief of Staff reasoning | Delegation and synthesis effectiveness, reflection and self-correction | Done |
| 17 | Investment proposal, charts and reasoning sliders | Synthesis into a cohesive strategy document; structured outputs | Done |

## Live verification

Run on 2026-10-16 against Azure OpenAI `gpt-5-mini` (reasoning effort `minimal`): the API with `DEBUG_MODE=true`, `demo.py`, and two runs of each scenario for [docs/performance.md](docs/performance.md). "As merged" is the code before this verification.

| Step | Live check | Result |
| --- | --- | --- |
| 1 | `uv run python llm.py` | Pass: the deployment replied. |
| 2 | `POST /evaluate` with the healthcare prompt | Pass: four healthcare-specific analyses. Context fields (the $15k budget, EHR incumbents, bookkeepers) appear in the scenario analyses. The log shows LangGraph's step traces and each node. |
| 3 | The four specialists run in parallel | Pass: in every run the specialists' combined time exceeds the time left after the sequential nodes (for example 88 s of specialist work in 38 s). |
| 4 | "Identify risks in our go-to-market plan." against the Step 2 prompt | Pass after fix: Risk and Marketing against all four, and no call for an unassigned specialist. As merged, the planner assigned a single specialist in 3 of 6 first requests, including "Evaluate…" requests. |
| 5 | The Step 2 request returns one strategy | Pass. |
| 6 | Review history, and a report improving between rounds | Pass: for example Risk 4 → 5 and Finance 4 → 5, both approved after revision. |
| 7 | Premium pricing on a small budget shows a conflict and its resolution | Pass after fix: for example Marketing's $15k–$30k four-to-six-week pilot against Finance's $8k one-week pilot, settled, revised and reflected in the strategy. As merged, no conflict was flagged in 10 runs. |
| 8 | "Refine the pricing strategy after financial review." with the same `session_id` | Pass after fix: Finance and Marketing rerun, 13 calls against 21 for the first request. As merged, a follow-up could cost more than the first request, and the follow-up lost the original idea. |
| 9 | `uv run python demo.py scenarios/premium_on_a_budget.json` | Pass: plan, reports, two review rounds, resolutions and strategy, then the follow-up. |
| 10 | Performance numbers | Pass: first requests take 32–39% fewer calls and follow-ups 58–64% fewer (see [docs/performance.md](docs/performance.md)). Error handling is covered by the automated tests; no failure was injected live. |
| 11 | The diagram matches `draw_mermaid()` | Pass: 30 of 30 edges. |
| 12 | The scenarios rerun as in [docs/performance.md](docs/performance.md) | Pass: first requests take 41–59% less time (108–116 s down to 44–64 s) and follow-ups 42–44% less, with the same calls and no rise in rejected reports. Reports run about 450 words and strategies about 570; a healthcare report and strategy read as specific and complete. |
| 13 | The API, the Streamlit UI and the Next.js app together | Pass: `/health` answered in under 2 ms during a 62 s evaluation. A follow-up sent through the Streamlit UI reran Finance and Marketing in the same session (14 calls). Headless Chrome loaded the Next.js app and showed "Connected", and "Can't reach" with the API stopped. The CORS preflight is allowed for `http://localhost:3000` only. |
| 15 | A scenario's report on the Reports page, in headless Chrome against Azure OpenAI | Pass: the report and a 6–10 page preview appear after the evaluation. An edit typed in the browser is saved (version 2), shown in the preview and kept by the detailed version, which took 29–34 s and grew the sections from about 330–640 words to about 970–1,340 (13–15 pages). No errors on the page. |
| 16 | The three scenarios with the Chief of Staff at `medium` and at `high`, against the old prompts; the Reports flow in headless Chrome | Pass: evaluations take 89–130 s at `medium` (50–56 s before) and 5–9.5 minutes at `high`; `medium` was chosen. `xhigh` is accepted but does no reasoning on `gpt-5-mini`. Review caught two weak reports that came back improved; decisions and the strategy are concrete and consistent. The Reports flow passed 14 of 14 checks. |
| 17 | Two scenarios evaluated, their proposals written and revised against Azure OpenAI; the PDFs read page by page; the Reports page in headless Chrome | Pass after fixes: writing takes 57–82 s and a one-part revision 40–54 s. The live runs moved the projections' arithmetic into code, added the figure checks and the financial case, retried a content-filtered reply, and fixed an IRR above 1,000% shown as "none" (see [docs/performance.md](docs/performance.md)). In the browser, 27 of 27 checks: the sliders, a tab per section, no inner scroll boxes, an edit saved, and the PDF pop-up's revision adding the requested risk, with no console errors from the app. |

### Fixed during live verification

- **Delegation (Step 4).** The planner saw only the specialists' names. It now sees what each covers (`focus` in `agents/roles.py`), is told that evaluating a whole idea needs all four, and keeps tasks to one or two sentences.
- **Cross-critique (Step 7).** The prompt asked for "genuine conflicts" and the model never found one, even for a $8k against $15k pilot price. Specialists now flag up to two concrete disagreements in their own area. All of a round's conflicts are settled in one call. Several decisions for one specialist used to overwrite each other, and names written as "Finance specialist" were ignored; both are fixed. Synthesis now receives the decisions.
- **Critique loop (Steps 7 and 10).** A critique revision always triggered a second critique and resolve pass, although no further revision was allowed, and it replaced the first round's resolutions in the response. The revised report now goes straight to synthesis.
- **Follow-ups (Step 8).** The original request was lost and reassigned specialists started from scratch; both now see the original request and their earlier report. Metrics, review history and resolutions piled up across requests in a session; they now cover the current request only. Every report was critiqued again; now only the reassigned ones are. The planner reassigned three or four specialists; it now reassigns those who own what the follow-up changes.
- **Checkpointer.** LangGraph warned that it would block the unregistered state models in a future version, which would break follow-ups. They are now registered.
- **Debugging (Step 2).** `DEBUG_MODE` did not turn on LangGraph's step traces; it does now.

A code review after the live runs found more, also fixed with tests:

- **Blocked server (Step 2).** `POST /evaluate` ran the blocking `graph.invoke` inside an async endpoint, so one evaluation froze the whole server, `/health` included. It now awaits `graph.ainvoke`.
- **500 on an LLM failure (Step 10).** Any failed Chief of Staff call returned 500. A failed review, critique or resolve call is now skipped; a failed plan or synthesis call returns 502 with the reason.
- **Stacked retries (Step 10).** A structured call retried every error once on top of the client's own retries, so one timeout could cost six 60-second attempts. It now retries only a reply that does not parse.
- **Token metrics (Step 10).** The `tokens` metric left out every structured call, about half the real total. It now includes them.
- **Specialist names (Steps 4 and 7).** The fix for names written as "Finance specialist" covered only the resolve step, and missed "financial". The structured outputs now allow only the four names.

## Steps

### Step 0 - Project scaffold (Done)

**Goal:** everyone can install, run and test the project the same way.

**Built:**

- `pyproject.toml`, `uv.lock`, `.python-version`: dependencies managed by uv on Python 3.12.
- `.env.example`, `config.py`: environment configuration, including `DEBUG_MODE`.
- `main.py`: FastAPI app with `GET /health`.
- `tests/`: pytest set up with one API test.
- `llm.py`, `state.py`, `graph.py`, `agents/`: empty placeholders, each naming the step that fills it in.

**Check:**

```bash
uv sync
uv run pytest            # 1 passed
uv run python main.py    # then open http://localhost:8000/health
```

### Step 1 - LLM connection (Done)

**Goal:** every agent gets its chat model from one place, configured only through `.env`.

**Build:**

- `llm.py`: `get_llm()` returns the chat model for the provider whose credentials are set (see D2). The model is created on first use, so the app and the tests start without credentials.
- A clear error that names any missing variable.
- `uv run python llm.py` sends one prompt and prints the reply.
- `.env.example`: the variables for each supported provider.
- `tests/conftest.py`: a fixture that strips real credentials during tests, so no test can reach a real model.

**Check:**

- Automated: `uv run pytest tests/test_llm.py` covers provider selection and the missing-variable errors.
- Live: `uv run python llm.py` prints a reply from the team's Azure deployment.

**Done when:**

- The tests pass on a machine with no `.env`.
- The live check works with real credentials.
- `.env` is not tracked by git.

### Step 2 - First specialist, end to end (Done)

**Goal:** prove the whole path once: API request, LangGraph, one agent, the LLM, and back.

**Build:**

- `state.py`: the shared state, holding the founder's request, the optional context (target market, constraints, competitive landscape) and the specialists' analyses.
- `agents/roles.py`: the Marketing Strategy Agent's role definition.
- `agents/specialist.py`: a node that answers the request from one role's point of view (see D4).
- `graph.py`: `START -> marketing -> END`. With `DEBUG_MODE=true`, LangGraph prints each step.
- `main.py`: `POST /evaluate` runs the graph and returns the analysis. Missing credentials return 503 with the reason.
- `tests/conftest.py`: the fake model that every later test reuses.

**Check:**

- Automated: `uv run pytest` covers the graph and the API with the fake model.
- Live:

  ```bash
  curl -X POST http://localhost:8000/evaluate \
    -H "Content-Type: application/json" \
    -d '{"prompt": "Evaluate this startup idea in the AI healthcare space."}'
  ```

**Done when:**

- The response holds a marketing analysis specific to the request, not generic advice.
- Context fields, when sent, show up in the analysis.
- `DEBUG_MODE=true` shows the graph steps in the server log.

### Step 3 - All four specialists in parallel (Done)

**Goal:** the full team of specialists answers the same request at the same time.

**Build:**

- `agents/roles.py`: Financial Planning, Technical Feasibility and Risk & Compliance roles.
- `graph.py`: fan out from `START` to all four specialists, then `END`.
- `state.py`: analyses are merged by specialist name, because they arrive together.

**Check:**

- Automated: four analyses come back, each produced under its own role.
- Live: the Step 2 request returns four analyses, and the total time is close to the slowest specialist, not the sum of all four.

**Done when:**

- Each analysis stays inside its own area of responsibility.
- The four role definitions read clearly enough to go into the documentation unchanged.

### Step 4 - Chief of Staff: plan and delegate (Done)

**Goal:** a manager agent decides who works on what, instead of everyone answering everything.

**Build:**

- `state.py`: a structured delegation plan (pydantic) with the objective and one task for each specialist the request needs.
- `agents/chief_of_staff.py`: a planning node that produces the plan, and routing that sends each task only to its specialist.
- `agents/specialist.py`: works on its assigned task rather than the raw request.
- If the plan comes back with no assignments, every specialist is assigned, so a request is never dropped.

**Check:**

- Automated: a narrow plan runs only the assigned specialists; two tasks for one specialist are merged; an empty plan falls back to all four.
- Live: "Identify risks in our go-to-market plan." involves Risk and Marketing rather than all four, while the Step 2 request involves all four.

**Done when:**

- The response shows the objective and who was given which task.
- No LLM call is made for a specialist that was not assigned.

### Step 5 - Chief of Staff: synthesis (Done)

**Goal:** the founder gets one strategy, not a pile of separate reports.

**Build:**

- `agents/chief_of_staff.py`: a synthesis node that merges the reports into one launch strategy with a recommendation, the reasoning, where the specialists pull in different directions, and prioritised next steps.
- `graph.py`: every specialist leads to synthesis, then `END`.
- `main.py`: the response gains `final_strategy`.

**Check:**

- Automated: synthesis runs exactly once, after the assigned specialists, and receives every report.
- Live: the Step 2 request returns one coherent strategy.

**Done when:**

- The strategy uses only what the specialists reported.
- A request delegated to only two specialists still produces a strategy.

### Step 6 - Review and refine loop (Done)

**Goal:** weak reports are caught and improved before they reach the strategy. This closes the Plan-Act-Check loop (see D1).

The initial version bounds refinement to a single revision (`max_iterations = 1`), matching the minimal example: a report is reviewed, revised at most once, then accepted. The cap is configurable so later rounds can be allowed without code changes.

**Build:**

- `state.py`: a review result per report (approved or not, score, feedback), an iteration count and the review history.
- `agents/chief_of_staff.py`: a review node that checks each report against its task.
- `graph.py`: reports that need work go back to their specialist with the feedback. The loop ends when every report is approved or `max_iterations` is reached (1 in the initial version).
- `agents/specialist.py`: revises its previous report using the feedback.

**Check:**

- Automated: a rejected report is revised, and the revision request contains the feedback; approved reports are not rerun; the loop stops at `max_iterations`.
- Live: the response includes the review history, and at least one request shows a report improving between rounds.

**Done when:**

- Only rejected reports cost another LLM call.
- The loop always terminates.

### Step 7 - Cross-specialist critique (Done)

**Goal:** specialists challenge each other, and the Chief of Staff settles the disagreements.

**Build:**

- A cross-critique node where each specialist reads the others' reports and flags conflicts with its own area, such as Finance on Marketing's pricing.
- `agents/chief_of_staff.py`: resolves each conflict, records the decision in the state, and sends the affected specialist back to revise.
- A cap on the number of rounds.

**Check:**

- Automated: a planted conflict is flagged, resolved, and reaches the affected specialist; with no conflicts there is no extra round.
- Live: a request with built-in tension, such as premium pricing on a very small budget, shows the conflict and its resolution in the response and in the final strategy.

**Done when:**

- Every conflict in the response has a recorded resolution.
- A request with no conflicts costs no more than it did after Step 6.

### Step 8 - Follow-up requests (Done)

**Goal:** the founder can come back to the same venture and refine one part of it (see D3).

**Build:**

- `graph.py`: a checkpointer, so a session's state survives between requests.
- `main.py`: a `session_id` on the request and the response.
- `agents/chief_of_staff.py`: for a follow-up, planning keeps the reports that still stand and assigns only the specialists the follow-up affects.

**Check:**

- Automated: a second request in the same session sees the first one's reports; only the affected specialists rerun; a different session starts clean.
- Live: run the Step 2 request, then send "Refine the pricing strategy after financial review." with the same `session_id`.

**Done when:**

- The follow-up changes the pricing part of the strategy and leaves unrelated parts intact.
- The follow-up makes fewer LLM calls than a full evaluation.

### Step 9 - Scenarios and demo (Done)

**Goal:** fixed scenarios that we test against, measure with, and present.

**Build:**

- `scenarios/`: at least three startup scenarios with the brief's sample inputs (idea, target market, constraints, competitive landscape), covering the brief's three sample prompts.
- `demo.py`: runs a scenario and prints each stage as it happens: plan, reports, critique, reviews, strategy.

**Check:**

- Automated: every scenario file loads and passes request validation.
- Live: `uv run python demo.py scenarios/<name>.json` walks through a whole run, including one refinement.

**Done when:**

- Someone who has not seen the code can follow the walkthrough.
- One scenario shows an iterative refinement from start to finish.

### Step 10 - Optimization and error handling (Done)

**Goal:** the workflow is measurably cheaper and faster, and fails gracefully.

**Build:**

- Per-run metrics in the response and the logs: LLM calls, tokens and time per node.
- A baseline measured on the Step 9 scenarios, then the redundant calls removed. Candidates: skip cross-critique when one specialist was assigned, cap review rounds, trim what each prompt carries.
- Error handling: timeouts and retries on LLM calls, one retry on malformed structured output, and a failed specialist does not sink the run because the strategy names the gap instead.
- `docs/performance.md`: the before and after numbers.

**Check:**

- Automated: with one specialist failing, the run still returns a strategy that names the gap; the metrics are present in the response.
- Live: rerun the scenarios and record the numbers.

**Done when:**

- `docs/performance.md` shows a measured improvement over the baseline, and what was given up for it.
- No single failed LLM call produces a 500 response.

### Step 11 - Documentation (Done)

**Goal:** the brief's documentation deliverables, written from the finished system.

**Build:**

- `docs/architecture.md`: the state machine diagram generated from the compiled graph, the agent role definitions, the delegation logic, the reasoning loop, a walkthrough of one request, and the design trade-offs.
- `README.md`: the Implementation section brought up to date. The brief above it stays untouched.

**Check:**

- The diagram matches the output of `build_graph().get_graph().draw_mermaid()`.
- A reviewer can trace one request through the document without opening the code.

**Done when:**

- Every item under "Documentation" and "Architecture & Workflow Design" in the brief has a section.

### Step 12 - Faster API (Done)

**Goal:** a request takes about half as long, with no fewer checks.

**Built:**

- `agents/chief_of_staff.py`: a round's review calls, and the specialists' critique calls, run at the same time; a failed call is still skipped on its own.
- `llm.py`: the chat model is built once and reused, so every call shares one connection pool.
- `agents/roles.py`, `agents/chief_of_staff.py`: reports are asked to keep to 250 words and the strategy to 500, and review judges substance, not length.

**Check:**

- Automated: review and critique calls overlap in time; the model is built once; the word limits are in the prompts.
- Live: rerun the scenarios as in [docs/performance.md](docs/performance.md) and compare the seconds.

**Done when:**

- Requests take markedly less time than before, with no rise in rejected reports.
- A reviewer has read a strategy and a report from the live runs and finds them still specific and complete.

### Step 13 - Streamlit UI and Next.js scaffold (Done)

**Goal:** the founding team can be run from a browser, and the Next.js frontend that will replace the Streamlit UI is set up.

**Built:**

- `streamlit_app.py`: a Streamlit UI over `POST /evaluate`: scenario prefill, request and context, follow-ups in the same session, and the plan, reports, reviews, conflicts, metrics and strategy. Streamlit is in the optional `ui` dependency group.
- `main.py`, `config.py`: CORS for browser frontends, from `CORS_ORIGINS` (default `http://localhost:3000`).
- `frontend/`: a Next.js 16 app (TypeScript, App Router, Tailwind, ESLint) with a typed API client and a home page that checks it can reach the backend.

**Check:**

- Automated: `uv run --group ui pytest` drives the Streamlit UI against canned API responses; the CORS preflight is allowed for the frontend's origin only; `npm run lint` and `npm run build` pass in `frontend/`.
- Live: run the API and the Streamlit UI, evaluate a scenario, then send a follow-up; open the Next.js app and see "Connected".

**Done when:**

- A full evaluation and a follow-up work end to end in the Streamlit UI.
- The Next.js app reaches the backend from the browser.

### Step 14 - Next.js UI (Built; Streamlit retires once checked)

**Goal:** the Next.js frontend does everything the Streamlit UI does, so the Streamlit UI can be retired.

Built in two parts, each checked by the user before the next.

**Part 1, the Evaluate page (built):**

- `main.py`: `GET /scenarios` serves the example scenarios, which a browser cannot read from disk.
- `frontend/`: the request form with scenarios and context; a progress panel with a running clock while the team works; the results (strategy, plan, reports, reviews, conflicts, metrics) with assumptions highlighted; follow-ups in the same session, the session kept in the browser tab; and a sidebar with the backend's status and the two reasoning sliders.
- `frontend/`: Vitest and React Testing Library tests against a fake backend, failing below 80% coverage.

**Part 2, the Reports page (built):**

- `frontend/`: the report picker (the session in the address, else the Evaluate page's, else the newest); the team's report, read or edited; writing and rewriting the proposal with a progress panel; a tab per section with its charts (market size, funnel, roadmap, costs, projections, cash position, risk matrix and cards), source badges, calculated figures and failing checks; an edit form per part, tables included; the PDF in a pop-up on the browser's `<dialog>`, with the download and the revise prompt; reset; and a reload with a notice when the report changed elsewhere.
- `frontend/`: tests for every action and failure against a stateful fake of the `/reports` endpoints, its sample report exported from the backend's own models.

**Left:** retiring the Streamlit UI and its `ui` dependency group, once the user has checked the Next.js UI.

Optionally, a streaming endpoint (LangGraph's `astream`) so the UI can show each stage as it finishes instead of one long wait.

**Done when:**

- Everything the Streamlit UI shows is in the Next.js UI, and the Streamlit UI and its `ui` dependency group are removed.

### Step 15 - Reports: editor, detailed version and PDF (Done)

**Goal:** each session's result becomes a document the founder can edit, expand and hand out as a PDF. Built before Step 14 because the team asked for it first; the numbering stays, so earlier references to Step 14 still hold.

**Built:**

- `reports.py`: each session's report, recorded by `/evaluate`: a markdown section each for the strategy, the specialists' reports and the decisions on conflicts. Kept in memory with a version number; a save made to an older version is refused.
- `agents/report_writer.py`: on request, each specialist expands its section from its current text, all at once, then the Chief of Staff rewrites the strategy from the expanded sections.
- `report_pdf.py`, `assets/fonts/`: the report as a PDF, laid out by fpdf2 in the bundled DejaVu Sans font.
- `main.py`: `GET /reports`, `GET`/`PUT /reports/{session_id}`, `POST .../detailed`, `POST .../reset` and `GET .../pdf`.
- `ui/reports_page.py`: a Reports page in the Streamlit UI with the sections in editable boxes beside the PDF preview, and buttons for the detailed version, reset and download. The Streamlit UI is split into pages under `ui/`.

**Check:**

- Automated: a report is recorded and refreshed by evaluations; edits are saved and a stale save is refused; the detailed version expands each section from its current text and a failed section keeps its text; the PDF renders characters the core fonts lack; the Reports page saves edits, reloads after a detailed version or a conflicting edit.
- Live: run a scenario, open its report, edit a section, then write the detailed version, and read the PDF.

**Done when:**

- An edit appears in the PDF preview after it is saved.
- The detailed version keeps the edits and every recommendation, and the PDF reads as one document.

### Step 16 - Sharper prompts, deeper Chief of Staff reasoning (Done)

**Goal:** better decisions from the same workflow: sharper specialists, and a Chief of Staff that reasons harder about what it decides.

**Built:**

- `agents/roles.py`, `agents/specialist.py`: each specialist is an expert persona with concrete deliverables (for example the marketer's beachhead niche, channels and validation experiment with its success threshold), leads with its recommendation, names concrete figures, shows its arithmetic and marks assumptions. A revised or follow-up report is rewritten whole.
- `agents/chief_of_staff.py`: planning states the objective as the decision at stake and gives each task its question and binding constraint; review scores against a rubric, and the score decides the verdict (`APPROVAL_SCORE`, 4); resolving conflicts follows a decision order (hard constraints, then evidence, then optionality; law and safety first) with the reports in view; synthesis leads with go, go with conditions, or not yet, and keeps figures consistent. Review, resolve and synthesis all see the founder's request and constraints.
- `llm.py`, `config.py`: the Chief of Staff's calls use their own reasoning effort (`AZURE_OPENAI_CHIEF_REASONING_EFFORT`, `medium`), the specialists' theirs (`minimal`); the per-call timeout is 120 s, a few times the slowest normal call, so a stalled Azure request is retried sooner.
- `agents/report_writer.py`: the detailed sections and strategy are written to the same standard, the strategy on the Chief of Staff's model (replaced by the proposal writer in Step 17).

**Check:**

- Automated: the Chief of Staff's calls run on its model and the specialists' on theirs; review, resolve and synthesis see the founder's request and constraints; the score decides the verdict; the effort settings and their fallback.
- Live: the scenarios at each effort, timed, and their outputs compared with the old prompts (see [docs/performance.md](docs/performance.md)).

**Done when:**

- The decisions and strategy are measurably more concrete and consistent, and the extra time is known and chosen.

### Step 17 - Investment proposal, charts and reasoning sliders (Done)

**Goal:** the report becomes an investment proposal an investor can read: the founder's template (executive summary, market and marketing, technical and operational architecture, financial plan, risk matrix, KPIs) with charts, each part marked with the agent it came from; the Reports page easier to read; and the founder choosing how hard the agents reason.

**Built:**

- `proposal.py`: the proposal as structured data, one model per part. Finance gives each year's drivers (customers, fixed costs, one-off fees); each year's revenue and OpEx and the investment metrics (NPV, IRR, payback, break-even, net margins) are calculated from them, and `figure_checks` flags figures that disagree (year one's costs against the launch OpEx, revenue against the SOM, average against year-end customers).
- `agents/proposal_writer.py` (replaces `agents/report_writer.py` and the detailed version): the agents write their parts from the report as it stands, in three waves (Marketing, Technical and Risk together; then Finance, from the market and technical parts; then the Chief of Staff's executive summary and KPIs, from all four and the metrics). Finance is given what the other parts commit to spend, and a failed figure check sends its plan back once for correction. The executive summary includes a required financial case that faces weak returns. A revision applies the founder's instruction to one part or all of them, and brings the parts written from it into line. A reply withheld by Azure's content filter is retried once.
- `report_charts.py`, `report_pdf.py`: the proposal PDF: a cover with the document control and recommendation, the template's sections with charts drawn by fpdf2 (market-size circles, funnel, roadmap, cost bars, revenue against costs, cash position, risk heat map and risk cards, stat tiles, KPI cards), source labels on every section ("written by" an agent, or "calculated"), highlighted assumptions, failing figure checks, and the team's report as an appendix.
- `main.py`: `POST /reports/{id}/proposal`, `POST .../proposal/revise`, `PUT .../proposal` (replacing `POST .../detailed`); the report carries the calculated `investment` metrics; `/evaluate` and the proposal requests take `reasoning` per role; `/health` reports the efforts.
- `llm.py`, `config.py`: a request's efforts held in a context variable that the worker threads inherit; one model client per effort; `LLM_TIMEOUT_HIGH` (300 s) for calls at `high`.
- `ui/reports_page.py`, `ui/proposal_view.py`, `ui/reasoning.py`: the Reports page shows the report as text, tables and charts with no inner scroll boxes, a tab per proposal section with an "Edit" switch, the PDF in a pop-up with an inline prompt to revise a part, and two reasoning sliders in the sidebar.

**Check:**

- Automated: revenue, OpEx and the metrics on known drivers; the figure checks, and Finance's one correction; the proposal written in waves from the edited report, with the other parts' commitments summed for Finance; a part revision reaching the parts built on it; a whole-proposal instruction reaching every part; a failed part kept on revision and a new proposal with a part missing refused; stale versions refused; edits saved; the PDF drawn for loss-making, empty and over-long figures; chosen efforts reaching every call, including worker threads, and `xhigh` refused; the Reports page's proposal, edits and pop-up revision.
- Live: a scenario evaluated, its proposal written and one part revised against Azure OpenAI, timed, the PDF read page by page, and the Reports page in headless Chrome.

**Done when:**

- The proposal follows the template with charts drawn from its figures, its numbers agree across parts, a revision changes what it was asked to, and the founder can read, edit, revise and download it from the Reports page.

## Target layout

```
main.py                    FastAPI app                        Step 0, then 2, 5, 8, 13, 15, 17
config.py                  Environment settings               Step 0
llm.py                     Chat model client                  Step 1
state.py                   Shared workflow state              Step 2 onward
graph.py                   LangGraph state machine            Step 2 onward
metrics.py                 Per-node run metrics               Step 10
agents/roles.py            Specialist role definitions        Steps 2-3
agents/specialist.py       Specialist node                    Steps 2, 4, 6
agents/chief_of_staff.py   Plan, delegate, review, synthesise Steps 4-8
proposal.py                Investment proposal and metrics    Step 17
agents/proposal_writer.py  Writes and revises the proposal    Step 17
reports.py                 Written reports and their store    Steps 15, 17
report_pdf.py              Report as a PDF                    Steps 15, 17
report_charts.py           The PDF's charts                   Step 17
assets/fonts/              The PDF's font                     Step 15
tests/                     Automated tests                    every step
scenarios/                 Startup scenarios                  Step 9
demo.py                    Walkthrough script                 Step 9
docs/                      Architecture and performance docs  Steps 10-11
streamlit_app.py, ui/      Streamlit UI and its pages         Steps 13, 15, 17
frontend/                  Next.js frontend                   Steps 13-14
```

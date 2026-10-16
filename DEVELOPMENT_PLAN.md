# Development Plan

Build sequence for the AI Startup Co-Founder Team capstone. The brief is the top section of [README.md](README.md).

We build one step at a time. Each step adds one feature, is small enough to review in one sitting, and ends with checks anyone can run.

**Where we are:** all steps are done. The full workflow is built, tested with a fake model, and documented. The remaining live checks (real-model runs and the performance numbers in `docs/performance.md`) need a filled-in `.env`.

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
| 4 | Chief of Staff: plan and delegate | Manager-led delegation, structured outputs | Next |
| 5 | Chief of Staff: synthesis | Synthesis into a unified launch strategy | To do |
| 6 | Review and refine loop | Plan--Act--Check loop, reflection and critique cycles | To do |
| 7 | Cross-specialist critique | Back-and-forth between agents, conflict resolution | Done |
| 8 | Follow-up requests | Stateful system, iterative refinement | Done |
| 9 | Scenarios and demo | Testing with multiple scenarios, live walkthrough | Done |
| 10 | Optimization and error handling | Fewer redundant calls, latency, error handling strategy | Done |
| 11 | Documentation | Architecture diagram, role definitions, workflow, trade-offs | Done |

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

## Target layout

```
main.py                    FastAPI app                        Step 0, then 2, 5, 8
config.py                  Environment settings               Step 0
llm.py                     Chat model client                  Step 1
state.py                   Shared workflow state              Step 2 onward
graph.py                   LangGraph state machine            Step 2 onward
agents/roles.py            Specialist role definitions        Steps 2-3
agents/specialist.py       Specialist node                    Steps 2, 4, 6
agents/chief_of_staff.py   Plan, delegate, review, synthesise Steps 4-8
tests/                     Automated tests                    every step
scenarios/                 Startup scenarios                  Step 9
demo.py                    Walkthrough script                 Step 9
docs/                      Architecture and performance docs  Steps 10-11
```

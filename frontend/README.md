# Frontend (Next.js)

The Next.js frontend for the AI Startup Co-Founder Team, its UI (it replaced the Streamlit UI in Step 14). It has three pages: **Evaluate**, to prepare a brief with the Chief of Staff, run the founding team on it, follow it as it works and send follow-ups; **Reports**, to read and edit each session's report, have the agents write it up as an investment proposal with charts, and get the PDF; and **How it works**, to see how the team turns a brief into a decision and what the API has been doing. The sidebar's reasoning sliders apply to every request.

Created with `create-next-app` 16.4.2: TypeScript, App Router, Tailwind CSS and ESLint, with the code under `src/`.

## Setup

Requires Node.js 20.9 or newer.

```bash
cd frontend
npm install
cp .env.example .env.local
```

`.env.local` holds where the API is (`BACKEND_URL`, http://localhost:8000 by default) and its key (`API_KEY`, the same as the backend's; empty when the backend has none). Only this app's server reads them: the pages call the API through the app's own `/api` route, which forwards each call with the key, so neither reaches the browser.

## Security

- **The proxy** (`src/app/api/[...path]/route.ts`) forwards only the API routes the pages use, caps a body at `MAX_REQUEST_BYTES` (1,000,000) before holding it, sends the browser's address on for the API's per-caller limits, and passes back only what a page needs (the type, the file name, the request ID, `Retry-After`), streaming an evaluation's events as they come. An API it cannot reach is a 502 that says so.
- **Guardrails.** When the API names text that tried to instruct the agents (`guardrails` in its answers; see the root README), a notice says so and where: on the brief's review for a web page, on the result for the brief or the answers, and in the PDF pop-up for a requested change. It was taken out of what the agents read, and the run went on.
- **Every page** is served with a content security policy (everything from this app; inline scripts for Next and inline styles for the diagrams; eval only in development; the PDF from a blob in a frame; no framing by other sites), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, a strict referrer policy and no camera, microphone or location (`next.config.ts`).

## Run

Start the backend from the repository root, then the frontend:

```bash
uv run python main.py    # repository root: the API on port 8000
npm run dev              # frontend/: http://localhost:3000
```

The sidebar shows whether the browser can reach the backend, checking again every 30 s while the page is shown, so it follows an outage and the recovery. If it can't, check that the backend is running and that `BACKEND_URL` and `API_KEY` in `.env.local` match it.

## The Evaluate page

- **What do you need decided?** offers the decision templates the API serves (`GET /templates`): pick one and fill in its few fields, and the page shows the brief they make; or write **your own brief**. **Context** adds the target market, constraints and competition. **Or start from an example** fills both from the scenarios (`GET /scenarios`).
- **Check the brief** (or ⌘/Ctrl+Enter) has the Chief of Staff prepare it (`POST /brief/prepare`, about half a minute): it searches the web, with the provider the sidebar's switch names, then shows what it found under **Before the team starts**: the facts, each citing its sources (leave out any that do not fit your case), the sources and searches, and up to three questions about facts only you know, with likely answers to pick or your own words. **Run the team** sends the brief with your answers and the facts you kept. With no research provider set up on the server, the brief is still checked, and the page says research is off. Untick **Research it and check the brief first** to run the team straight away.
- **Deep research for each specialist** (off by default) researches every assigned specialist's area and profiles up to three competitors before the specialists start, with the sidebar's provider: on Azure OpenAI about half a minute and a few dozen Bing searches, on Tavily a minute or two and about 150–450 credits, as shown beside the switch. The live view shows it as the **Research** stage, and the result's **Research** tab holds each area's report, the competitor profiles, anything Tavily could not research, and every source, numbered as the agents cite them; the summary beside the memo gives the credits it cost.
- While the team works (about two minutes at the default efforts), the page follows it through the streamed evaluation (`POST /evaluate/stream`): a log of what each agent finished, with the time, a line saying who is working now, and the five stages of the work, with each specialist writing, revising or done. A clock shows the time taken.
- The result is the launch strategy, set as a memo under its objective, with the team's reviews beside it: each specialist's score and verdict, the conflicts the Chief of Staff settled, the research it drew on, and the request's model calls, tokens and time. Tabs below hold the specialists' reports, the research (your answers, the brief's facts, the deep research and their sources), the plan, each round of reviews, the conflicts and their decisions, and the time each step took. Figures the agents marked as assumptions are highlighted.
- A follow-up reuses the session; a scenario's own follow-up is filled in. Each request in the session stays, one click away.
- The session is kept in the browser tab, so a reload does not lose a result. **Start a new session** clears it.
- The sidebar's **Web research** switch picks where web research runs, for the brief and for deep research: **Azure OpenAI**, the default (Bing search through the team's deployment), or **Tavily**, for demanding tasks. A provider the server has not set up is disabled, and this browser remembers the choice.
- The sidebar's **Reasoning** sliders set how hard the specialists and the Chief of Staff reason for every request. They start at the backend's configured efforts, and this browser remembers a change.
- **Open the report** goes to the session's report on the Reports page.

## The Reports page

- **Report** picks a session's report: the one in the address (`/reports?session=…`), else the Evaluate page's, else the newest.
- Before the proposal, the page shows the team's report (the strategy, each specialist's report, the decisions on conflicts), each section labelled with the agent that wrote it. **Edit the team's report** turns it into markdown boxes, saved together.
- **Write the investment proposal** has the agents write it (a minute or two at the default efforts). It then reads as chapters, numbered as in the PDF: executive summary, market and marketing, technical and operations, the financial plan, risk and compliance, success metrics, and the team's report as an appendix. Each has its text, tables and charts (market size, funnel, roadmap, costs, projections, cash position, risk matrix), the agent that wrote it, and "calculated" on the figures the API works out; figures that fail a check are flagged. **Edit** turns a chapter into a form, tables included.
- **Open PDF** shows the document in a pop-up, in the browser's PDF viewer, with its download. There, **Ask the team to revise** sends an instruction for one part, or the whole proposal; the parts built on it follow, and the PDF is drawn again. **Revise with the team** opens the pop-up with the prompt ready.
- **More actions** holds **Rewrite the proposal** and **Reset to the latest results**, which ask before they replace anything. A change refused because the report changed elsewhere reloads it and says so.

## The How it works page

- **The pipeline** explains the system in pictures: the steps from a brief to a decision (each links to its explanation; dashed steps are optional, a hand marks your decisions), the agents and what each reads and writes, the Chief of Staff's five decisions, a matrix of which step reads and writes each part of the shared state, a worked example of the critique, where the facts come from (Azure OpenAI against Tavily, as measured), where your judgement matters, the stack layer by layer, and your path through the app. Its numbers (the approval score, the rounds, the word limits) come from the backend (`GET /pipeline`), so it says what the code does.
- **Show the diagrams** opens Mermaid drawings of the real LangGraph graph (from the compiled graph), the data flow from your brief to the memo, and the routes the Chief of Staff's decisions take, with their source to copy. Mermaid is loaded only then, draws one diagram at a time, and takes the page's colours, drawing again when the colour scheme changes.
- **Monitor** is a dashboard of what the API has done since it started (`GET /monitoring`), refreshed every five seconds while it is open and the page is shown: whether a warning or error was logged in the last 15 minutes (**Show them** filters the log to them) and how many evaluations are running; totals with the error rates, the median and 95th-percentile time to a decision, and calls and tokens averaged over the evaluations that finished; each step's median time as a bar, with a tick at its 95th percentile; the latest evaluations; and a log you can filter, where a warning or error names its request. Its statistics count since the API started; the latest evaluations and the log are history, kept in PostgreSQL when the API has a database (the header says so), so a restart keeps them. It asks once at a time and gives up on an answer after 10 s; while the API is not answering it keeps showing what it last heard, says why, and tries again after 10, 20, 40 and then 60 s (**Try now** asks at once). Pause stops the refresh.
- **Errors name their request.** Every error from the API shows the request's ID, from its `X-Request-ID` header, such as "(request 3f2a9c1b7d4e5f60)": the API's log lines for that request carry the same ID.

## Design

The pages read like the documents they hold. The agents' writing (strategies, reports, the proposal) is set in Newsreader, a serif, and the interface in Geist, with Geist Mono for times and IDs. Colours are tokens in `src/app/globals.css`: warm paper and ink, hairline rules, one navy for primary actions, and a data palette for the charts (blue and orange for two series, a blue ramp for ordered stages, red only for cash below zero). Each has a dark-mode value, chosen rather than inverted. Status colours (good, warning, bad) always sit beside a word. `.doc` sets the agents' markdown; a short line on its own before a list ("Key risks") is set as a heading, since the agents write section labels that way.

## Check

```bash
npm run lint
npm test                 # unit tests (Vitest and React Testing Library)
npm run test:coverage    # the same, failing below 80% coverage
npm run typecheck        # the whole project, tests included
npm run build            # the production build
```

The tests replace the backend with a fake (`src/test/backend.ts`, and `src/test/reports.ts` for the reports), so they need no server. `src/test/sample-report.json` is a report exported from the backend's own models, so the fixture matches what the API sends.

## What's here

```
src/app/layout.tsx                         Root layout and fonts: the sidebar and the backend provider
src/app/globals.css                        Colour tokens (light and dark), document type (.doc), sliders
src/app/page.tsx                           The Evaluate page
src/app/reports/page.tsx                   The Reports page
src/app/api/[...path]/route.ts             The proxy to the API, which adds its key
src/components/evaluate/evaluate-app.tsx   The session: requests, follow-ups, the live run, errors
src/components/evaluate/composer.tsx       The first request: a template or the brief, context and examples
src/components/evaluate/brief-review.tsx   Before the team starts: the questions, and the research to keep
src/components/evaluate/research.tsx       The research's facts, citing their sources, and the sources
src/components/evaluate/result-view.tsx    (also) the Research tab: answers, facts, deep research, competitors
src/components/evaluate/activity-log.tsx   What the team has done so far, and who is working now
src/components/evaluate/team-progress.tsx  The five stages of the team's work, idle or live
src/components/evaluate/result-view.tsx    One result: the strategy memo, the reviews, the team's work
src/components/reports/reports-app.tsx     The Reports page: cover, chapters, writing, editing, resetting
src/components/reports/proposal-view.tsx   The proposal's chapters on screen
src/components/reports/charts.tsx          The proposal's charts, in HTML and CSS
src/components/reports/edit-form.tsx       The forms that edit each part, tables included
src/components/reports/pdf-panel.tsx       The PDF pop-up: the revise prompt, download and viewer
src/components/reports/team-report.tsx     The team's report, read or edited
src/components/sidebar.tsx                 Pages, backend status and reasoning sliders (a menu on phones)
src/components/reasoning-sliders.tsx       The two reasoning sliders
src/components/research-switch.tsx         Where web research runs: Azure OpenAI or Tavily
src/app/how-it-works/page.tsx              The How it works page
src/components/how/how-app.tsx             The page: the pipeline and the Monitor, and the diagrams
src/components/how/pipeline-map.tsx        The pipeline at a glance
src/components/how/explainer.tsx           The agents, decisions, state, critique, research, judgement, stack
src/components/how/diagrams.tsx            Mermaid diagrams, loaded on demand
src/components/how/monitor-view.tsx        The live dashboard and log
src/lib/how.ts                             The page's steps, state matrix, judgement points, stack and diagrams
src/components/backend-status.tsx          Whether the browser can reach the API
src/components/guardrail-notice.tsx        What tried to instruct the agents, named to the founder
src/components/markdown.tsx                The agents' markdown: assumptions highlighted, labels as headings
src/components/ui/                         Buttons, fields, notices, badges, menu, tabs, dialog, icons,
                                           the page header, the progress panel and the team's mark
src/lib/api.ts                             Typed client for the backend, the stream reader included
src/lib/backend.tsx                        The backend's status, the chosen efforts and research provider, app-wide
src/lib/team.ts                            The team: names, stages, what it is doing, how long it takes
src/lib/proposal.ts                        The proposal's parts, and its metrics in words
src/lib/brief.ts                           Templates filled in, and the research the founder keeps
```

The types in `src/lib/api.ts` mirror the backend's request and response models in `main.py`, `state.py` and `brief.py`, and its `Step` the summaries in `progress.py`; change them together.

`npm audit` reports one high-severity advisory, in `braces`, which only the linter uses (through `eslint-config-next`); nothing the browser runs depends on it. `npm audit fix --force` would downgrade `eslint-config-next` to Next.js 14, so it is left until that package updates.

`AGENTS.md` is written by Next.js for coding agents. It points them to the docs that ship with this version (`node_modules/next/dist/docs/`), which differ from older Next.js versions.

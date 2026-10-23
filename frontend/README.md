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

## Docker

An option beside the local run. `Dockerfile` builds Next.js's standalone server (`next.config.ts` asks for it when `BUILD_STANDALONE` is set, as the Dockerfile does, so `npm run build` and `npm start` work as usual) and runs it as the unprivileged `node` user on port 3000. It reads `BACKEND_URL` and `API_KEY` when it starts, so one image serves any environment; no `.env` file enters the build. `./start.sh docker` or `docker compose up --build`, from the repository root, runs it with the API and PostgreSQL (see the root README).

## Security

- **The proxy** (`src/app/api/[...path]/route.ts`) forwards only the API routes the pages use, caps a body at `MAX_REQUEST_BYTES` (1,000,000), or an uploaded file at `MAX_UPLOAD_BYTES` (10,000,000), before holding it, sends the browser's address on for the API's per-caller limits, and passes back only what a page needs (the type, the file name, the request ID, `Retry-After`), streaming an evaluation's events as they come. An API it cannot reach is a 502 that says so.
- **Guardrails.** When the API names text that tried to instruct the agents (`guardrails` in its answers; see the root README), a notice says so and where: on the brief's review for a web page, on the result for the brief or the answers, and on the document's page for a requested change. It was taken out of what the agents read, and the run went on.
- **Dictation** asks for the microphone only when its mic is pressed, and sends the recording only to this app's `/api/transcribe`, which forwards it to the API (and its body cap is the upload limit).
- **Every page** is served with a content security policy (everything from this app; inline scripts for Next and inline styles for the diagrams; eval only in development; the PDF from a blob in a frame; no framing by other sites), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, a strict referrer policy, and no camera or location; the microphone only for the app's own pages, for dictation (`next.config.ts`).

## Run

Start the backend from the repository root, then the frontend:

```bash
uv run python main.py    # repository root: the API on port 8000
npm run dev              # frontend/: http://localhost:3000
```

Or start both with `./start.sh local` from the repository root, which asks for other ports if these are taken and hands this app's server the API's address and key itself.

On a large screen the button beside the mark (**Collapse the sidebar**) folds the sidebar into a narrow rail of the pages' icons, each named on hover, so a page, the document's above all, takes nearly the whole window; **Expand the sidebar** opens it out. This browser remembers it (`src/lib/sidebar.ts`): like the theme, it is an attribute on `<html>` (`data-sidebar`) set by a small script before the page first paints, which the layout's CSS follows (the `rail` variant and `--sidebar-width`). On a phone the sidebar is a bar with a menu, as before.

The sidebar shows whether the browser can reach the backend, checking again every 30 s while the page is shown, so it follows an outage and the recovery. If it can't, check that the backend is running and that `BACKEND_URL` and `API_KEY` in `.env.local` match it.

## The Evaluate page

- **What do you need decided?** offers the decision templates the API serves (`GET /templates`): pick one and fill in its few fields, and the page shows the brief they make; or write **your own brief**. **Context** adds the target market, constraints and competition. **Or start from an example** fills both from the scenarios (`GET /scenarios`).
- **Documents** adds the founder's files and earlier reports (`components/documents.tsx`). **Add files**, or drop them on the box: each is uploaded at once (`POST /uploads`) and shows what was read (its kind and length, any warning, and whether text in it tried to instruct the agents), or why it could not be; a file over 10 MB or a sixth is refused before it is sent. **Add an earlier report** picks one of the app's reports. Each wears the mark the agents cite it by, D1 for the first file and R1 for the first report; the brief waits until every file is read, and sends them in `context.uploads` and `context.reports`. The brief's review, and the result, name them, and each citation in the agents' text (`[D1 · page 3]`) is a tag that names its document on hover.
- **Check the brief** (or ⌘/Ctrl+Enter) has the Chief of Staff prepare it (`POST /brief/prepare`, about half a minute): it searches the web, with the provider the sidebar's switch names, then shows what it found under **Before the team starts**: the facts, each citing its sources (leave out any that do not fit your case), the sources and searches, and up to three questions about facts only you know, with likely answers to pick or your own words. **Run the team** sends the brief with your answers and the facts you kept. With no research provider set up on the server, the brief is still checked, and the page says research is off. Untick **Research it and check the brief first** to run the team straight away.
- **Deep research for each specialist** (off by default) researches every assigned specialist's area and profiles up to three competitors before the specialists start, with the sidebar's provider: on Azure OpenAI about half a minute and a few dozen Bing searches, on Tavily a minute or two and about 150–450 credits, as shown beside the switch. The live view shows it as the **Research** stage, and the result's **Research** tab holds each area's report, the competitor profiles, anything Tavily could not research, and every source, numbered as the agents cite them; the summary beside the memo gives the credits it cost.
- With a FRED key on the server, the team looks up the official figures its plan turns on (the research stage shows it). The result's **Research** tab lists them, each with its change over the year and a link to it on FRED, the summary counts them, and a figure the agents cite (`[FRED · DGS10]`) is a tag that opens its page there. With deep research on Tavily, each competitor's profile adds what its own pricing page says.
- While the team works (about two minutes at the default efforts), the page follows it through the streamed evaluation (`POST /evaluate/stream`): a log of what each agent finished, with the time, a line saying who is working now, and the five stages of the work, with each specialist writing, revising or done. A clock shows the time taken.
- **Live graph**, in the progress card while the team works, opens the graph LangGraph runs (`GET /pipeline`), drawn as on How it works and lit up as the steps stream in (`components/evaluate/live-graph.tsx`, `lib/live-graph.ts`): the step at work glows in its agent's colour, the arrows the work is moving along run, the arrows taken stand out, a finished step is ticked, or counted ("×2") when it ran again, and the steps the run went past are faint and dashed. Mermaid draws the graph once; each step's state is a class on its node and edges, so it changes without being drawn again, and it keeps still for those who ask for less motion. Beside it, a sidebar says what the team is doing now and lists each turn of each step, newest first, with its times and what it did. When the run ends, the pop-up stays open on the finished run.
- The result is the launch strategy, set as a memo under its objective, with the team's reviews beside it: each specialist's score and verdict, the conflicts the Chief of Staff settled, the research it drew on, and the request's model calls, tokens and time. Tabs below hold the specialists' reports, the research (your answers, the brief's facts, the deep research and their sources), the plan, each round of reviews, the conflicts and their decisions, and the time each step took. Figures the agents marked as assumptions are highlighted.
- With Langfuse set up on the server, a run links to its trace (**Open the run in Langfuse**, beside the reviews and in the Run tab), and **Was this strategy useful?** under the strategy sends the founder's verdict, with an optional comment, as a score on that trace (`POST /feedback`, `components/evaluate/feedback.tsx`). Without Langfuse neither shows.
- A follow-up reuses the session; a scenario's own follow-up is filled in. Each request in the session stays, one click away.
- The session is kept in the browser tab, so a reload does not lose a result. **Start a new session** clears it.
- The sidebar's **Web research** switch picks where web research runs, for the brief and for deep research: **Azure OpenAI**, the default (Bing search through the team's deployment), or **Tavily**, for demanding tasks. A provider the server has not set up is disabled, and this browser remembers the choice.
- The sidebar's **Reasoning** sliders set how hard the specialists and the Chief of Staff reason for every request. They start at the backend's configured efforts, and this browser remembers a change.
- **Open the report** goes to the session's report on the Reports page.

## The Reports page

- The report shown is the one in the address (`/reports?session=…`), else the Evaluate page's, else the newest. The button beside the title (`report-picker.tsx`) names it, with its kind, date and verdict, and **Browse** opens every report: a list, searchable by name, decision, verdict or session, filtered by kind and sorted, each entry with its verdict, decision, version, date, NPV and whether it was edited or has newer results; beside it, a preview of the one highlighted with its recommendation and its brief under it (amounts, shares and spans of time picked out by Markdown's `figures` option), headline figures (NPV, IRR, payback, break-even), key figures (a proposal's calculated from its plan, a team report's as the team gave them), figures that disagree, the founder's choices while it was built (`report-choices.tsx`: their brief, clipped until asked for whole, and its follow-up; the target market, constraints and competition; their answers to the Chief of Staff's questions; the research facts they kept, each with a link to its source; their documents; deep research and the efforts it ran at; every amount, share and span of time in their words picked out by `Figured`, from `markdown.tsx`), its versions (`report-versions.tsx`: a timeline, newest first, each with what made it, how many fields it changed and where; **What changed** opens them field by field from the version before, shown as a draft's changes are), the objective, the team, who it is from, its currency and what it worked from. Opening it loads the list afresh. The arrow keys move through the list and Enter opens; on a phone a tap opens. The preview has a title bar that stays in view as the rest scrolls: the report's kind, version and name, with **Delete** and **Open this report** beside them. **Delete** deletes a report for good (`DELETE /reports/{session_id}`) once the founder confirms, with Keep it focused; **More actions** has **Delete this report** for the open one, on any screen. When the open report is deleted, the newest left opens, and the page says what went.
- Before the proposal, the page shows the team's report (the strategy, each specialist's report, the decisions on conflicts), each section labelled with the agent that wrote it. **Edit the team's report** turns it into markdown boxes, saved together.
- **Write the investment proposal** has the agents write it (a minute or two at the default efforts). It then reads as chapters, numbered as in the PDF: executive summary, market and marketing, technical and operations, the financial plan, risk and compliance, success metrics, and the team's report as an appendix. Each has its text, tables and charts (market size, funnel, roadmap, costs, projections, cash position, risk matrix), the agent that wrote it, and "calculated" on the figures the API works out; figures that fail a check are flagged. **Edit** turns a chapter into a form, tables included.
- Each paragraph and list item has **Revise** and **Remove** buttons (on hover, or faint on a phone): the agent that wrote it rewrites just that, or it is taken out (`components/reports/passages.tsx`).
- **Open PDF** opens the document studio (`pdf-panel.tsx`) on a page of its own (`document-page.tsx`): the whole window beside the sidebar, all of it on a phone, with **Back to the report** and the document's title and version at the top. The page is in the address (`?session=…&view=document`), so the browser's Back button returns to the report, which is as it was left (its chapter, its scroll), and a reload opens the document again. It holds the PDF in the browser's viewer, with its download, beside four tools. **Hide the tools** folds them into a strip of their icons (a row on a phone), each opening the tools on it, with the download, so the PDF takes the page; this browser remembers it, and a change to accept or an earlier version to restore always shows them. **Revise** asks the team to revise one part or the whole proposal; an instruction that asks for a conversion points to Settings. **Settings** converts the currency at today's rate, filled in from the European Central Bank (`GET /rates/{base}`) with its date, or at the founder's own (kept per currency, with the ECB's one click away), or only relabels it, converts measurements to metric or imperial, and sets who the document is from and which of the team's sections it leaves out. **Text** finds and replaces, or redacts. **History** lists every version, to look at and restore. **Revise with the team**, **Currency, units and text** and **History** open it on their tool.
- **Every change is a draft** (`draft-review.tsx`): what it does, each changed field with the words it removes struck through and those it adds highlighted (`lib/diff.ts`), each amount before and after in its currency, and its PDF beside them, marked "not saved". **Accept and save** saves it as a new version; **Discard** leaves the report as it was.
- Amounts are shown in the report's currency everywhere: the chapters, the charts and the edit forms' labels (`CurrencyContext` in `lib/proposal.ts`, with the same symbols as the PDF). **Write the investment proposal** can write it in another currency from the start.
- **Ask about it** opens questions about the report (`components/reports/ask-panel.tsx`): the report, the files its run worked from and its earlier reports start in the list beside, and more files or reports can be added. The Chief of Staff answers from them alone (`POST /ask`), each citation a tag, and the passages it cites are listed under the answer to check.
- **More actions** holds **Rewrite the proposal** and **Reset to the latest results**, which ask before they replace anything. A change refused because the report changed elsewhere reloads it and says so.

## The How it works page

- **The pipeline** explains the system in pictures: the steps from a brief to a decision (each links to its explanation; dashed steps are optional, a hand marks your decisions), the agents and what each reads and writes, the Chief of Staff's five decisions, a matrix of which step reads and writes each part of the shared state, a worked example of the critique, where the facts come from (Azure OpenAI against Tavily, as measured), where your judgement matters, the stack layer by layer, and your path through the app. Its numbers (the approval score, the rounds, the word limits) come from the backend (`GET /pipeline`), so it says what the code does.
- **Show the diagrams**, under the pipeline map, opens Mermaid drawings of the real LangGraph graph (from the compiled graph), the data flow from your brief to the memo, and the routes the Chief of Staff's decisions take, with their source to copy. Each is drawn in the agents' colours, with a legend (`lib/how.ts` writes them, `components/how/diagrams.tsx` finishes them): every step in the colours of who runs it, the four specialists together in all four; the graph's arrows in the colour of the step they leave, its nodes and edges in the order the work runs and the routes back to a specialist drawn the other way round, so it reads from top to bottom; the data flow's stretches on bands of who does them. Mermaid is loaded only then, draws one diagram at a time, and takes the page's colours, drawing again when the colour scheme changes.
- **Monitor** is a dashboard of what the API has done since it started (`GET /monitoring`), refreshed every five seconds while it is open and the page is shown: whether a warning or error was logged in the last 15 minutes (**Show them** filters the log to them) and how many evaluations are running; the providers (Azure OpenAI, Tavily, FRED), a card each with what the app uses it for, how it stands now (Answering, Failing when its latest call failed, In use or Ready, Not set up, with the setting to add), and what each service did since the API started (calls and failures, tokens in and out, credits, the last call), with the last failure's reason; totals with the error rates, the median and 95th-percentile time to a decision, and calls and tokens averaged over the evaluations that finished; each step's median time as a bar, with a tick at its 95th percentile; the latest evaluations; and a log you can filter, where a warning or error names its request. Its statistics count since the API started; the latest evaluations and the log are history, kept in PostgreSQL when the API has a database (the header says so), so a restart keeps them. It asks once at a time and gives up on an answer after 10 s; while the API is not answering it keeps showing what it last heard, says why, and tries again after 10, 20, 40 and then 60 s (**Try now** asks at once). Pause stops the refresh.
- **Dictation** (`components/voice.tsx`): every input box where the founder tells the team something, and every one-line field, has a mic, the same everywhere: a ring of the five agents' colours; pressed, it records (MediaRecorder: Opus in WebM, or MP4 on Safari), opening into five bars, one an agent, that follow the voice through an analyser, with the time and a stop. Pressing it again or Enter sends the recording (`POST /transcribe`), which Azure OpenAI's Whisper writes down in English, whatever language was spoken; the words go in where the cursor was, a space from the words either side, as if typed, so the page's own state has them. Escape throws the recording away; it stops by itself at two minutes. The focus stays in the box. Without Azure OpenAI on the API (`voice.dictation` in `/health`) or a Whisper deployment, or without a microphone, or when the call fails, a note under the box says why. The editing areas (the team's sections, the proposal's fields, redaction) have none.
- **Errors name their request.** Every error from the API shows the request's ID, from its `X-Request-ID` header, such as "(request 3f2a9c1b7d4e5f60)": the API's log lines for that request carry the same ID.

## Design

The pages read like the documents they hold. The agents' writing (strategies, reports, the proposal) is set in Newsreader, a serif, and the interface in Geist, with Geist Mono for times and IDs. Colours are tokens in `src/app/globals.css`: warm paper and ink, hairline rules, one navy for primary actions, and a data palette for the charts (blue and orange for two series, a blue ramp for ordered stages, red only for cash below zero). Each has a dark-mode value, chosen rather than inverted: a mid grey rather than black, so the agents' colours and their tints read clearly, every mark clearing 3:1 against it. The sidebar's **Appearance** switch picks System, Light or Dark, remembered in the browser (`src/lib/theme.ts`): the choice is a `data-theme` attribute on `<html>` that the tokens follow, set by a small script before the page first paints so a remembered theme shows without a flash, and the diagrams draw again when it changes. Status colours (good, warning, bad) always sit beside a word.

Each agent has a colour, worn by everything it does: violet for the Chief of Staff, orange for Marketing, aqua for Finance, blue for Technical and magenta for Risk & Compliance, with web research in a neutral slate (`src/lib/agents.ts` says who does each step, part and section). The five come from the chart palette and were checked as neighbours, in the order they appear, in light and dark. A stage of the team's work, an entry in the activity log, a review, a report, a chapter and a bar on the Monitor are in their agent's colour. A stage several agents share is a ring of their colours, and the agents the Chief of Staff cites in its strategy (`[finance]`) are tags in theirs. A colour always sits beside the agent's name or icon (`components/ui/agent.tsx`), and text stays in ink. Wrapping an element in `agent-finance` (or another agent's class) lets anything inside it use `bg-agent`, `bg-agent-soft`, `text-agent-deep` and `border-agent`. `.doc` sets the agents' markdown; a short line on its own before a list ("Key risks") is set as a heading, since the agents write section labels that way.

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
src/components/evaluate/feedback.tsx       The founder's verdict on a strategy, for Langfuse
src/components/evaluate/live-graph.tsx     The team at work, lit up on the graph, with what it is doing
src/lib/live-graph.ts                      Each step's state and the edges taken, from the streamed steps
src/components/evaluate/result-view.tsx    One result: the strategy memo, the reviews, the team's work
src/components/reports/reports-app.tsx     The Reports page: cover, chapters, writing, editing, resetting
src/components/reports/report-picker.tsx   Every report, searchable, with a preview of the one highlighted
src/components/reports/report-versions.tsx A report's versions, each with what it changed from the one before
src/components/reports/report-choices.tsx  What the founder chose and told the team while a report was built
src/components/reports/proposal-view.tsx   The proposal's chapters on screen
src/components/reports/charts.tsx          The proposal's charts, in HTML and CSS
src/components/reports/edit-form.tsx       The forms that edit each part, tables included
src/components/reports/pdf-panel.tsx       The document studio: the PDF beside the revise, settings, text and history tools
src/components/reports/document-page.tsx   The studio's page: the whole window beside the sidebar, and the way back
src/components/reports/draft-review.tsx    A change before it is saved: its diffs, accept or discard
src/components/reports/passages.tsx        Revise or remove one paragraph of the report
src/components/reports/team-report.tsx     The team's report, read or edited
src/components/reports/ask-panel.tsx       Questions about a report and its documents, answered with sources
src/components/documents.tsx               The founder's documents: files uploaded, earlier reports, their marks
src/components/sidebar.tsx                 Pages, backend status and reasoning sliders; folds into a rail (a menu on phones)
src/lib/sidebar.ts                         Whether the sidebar is folded, remembered in the browser
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
src/components/markdown.tsx                The agents' markdown: assumptions highlighted, labels as headings, citations as tags
src/components/voice.tsx                   Dictation: the mic in the input boxes
src/components/ui/                         Buttons, fields, notices, badges, menu, tabs, dialog, icons,
                                           the page header, the progress panel and the team's mark
src/lib/api.ts                             Typed client for the backend, the stream reader included
src/lib/backend.tsx                        The backend's status, the chosen efforts and research provider, app-wide
src/lib/team.ts                            The team: names, stages, what it is doing, how long it takes
src/lib/proposal.ts                        The proposal's parts, and its metrics in words
src/lib/dates.ts                           Dates as the pages show them
src/lib/brief.ts                           Templates filled in, and the research the founder keeps
```

The types in `src/lib/api.ts` mirror the backend's request and response models in `main.py`, `state.py` and `brief.py`, and its `Step` the summaries in `progress.py`; change them together.

`npm audit` reports one high-severity advisory, in `braces`, which only the linter uses (through `eslint-config-next`); nothing the browser runs depends on it. `npm audit fix --force` would downgrade `eslint-config-next` to Next.js 14, so it is left until that package updates.

`AGENTS.md` is written by Next.js for coding agents. It points them to the docs that ship with this version (`node_modules/next/dist/docs/`), which differ from older Next.js versions.

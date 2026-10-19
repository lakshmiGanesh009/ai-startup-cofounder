# Frontend (Next.js)

The Next.js frontend for the AI Startup Co-Founder Team, its UI (it replaced the Streamlit UI in Step 14). It has two pages: **Evaluate**, to run the founding team on an idea and send follow-ups, and **Reports**, to read and edit each session's report, have the agents write it up as an investment proposal with charts, and get the PDF. The sidebar's reasoning sliders apply to both.

Created with `create-next-app` 16.4.2: TypeScript, App Router, Tailwind CSS and ESLint, with the code under `src/`.

## Setup

Requires Node.js 20.9 or newer.

```bash
cd frontend
npm install
cp .env.example .env.local
```

`.env.local` holds the backend's address (`NEXT_PUBLIC_API_URL`, http://localhost:8000 by default). It is built into the browser bundle, so it must never hold a secret.

## Run

Start the backend from the repository root, then the frontend:

```bash
uv run python main.py    # repository root: the API on port 8000
npm run dev              # frontend/: http://localhost:3000
```

The sidebar shows whether the browser can reach the backend. If it can't, check that the backend is running and that its `CORS_ORIGINS` (in the root `.env`) includes this app's origin, http://localhost:3000 by default.

## The Evaluate page

- **Start from a scenario** fills the form from the example scenarios the API serves (`GET /scenarios`); or describe an idea and add optional context.
- While the team works (about two minutes at the default efforts), a panel shows a running clock and what the team is doing.
- The result shows the objective and the launch strategy, with tabs for the plan, the specialists' reports, the reviews, the conflicts and their decisions, and the metrics. Figures the agents marked as assumptions are highlighted.
- A follow-up reuses the session; a scenario's own follow-up is filled in. Earlier requests stay, collapsed.
- The session is kept in the browser tab, so a reload does not lose a result. **Start a new session** clears it.
- The sidebar's **Reasoning** sliders set how hard the specialists and the Chief of Staff reason for every request. They start at the backend's configured efforts, and this browser remembers a change.
- **Open this session's report** goes to the Reports page.

## The Reports page

- **Report** picks a session's report: the one in the address (`/reports?session=…`), else the Evaluate page's, else the newest.
- Before the proposal, the page shows the team's report (the strategy, each specialist's report, the decisions on conflicts), each section labelled with the agent that wrote it. **Edit the team's report** turns it into markdown boxes, saved together.
- **Write the investment proposal** has the agents write it (a minute or two at the default efforts). It then has a tab per section: executive summary, market, technical, financial, risk and compliance, KPIs, and the team's report. Each shows its text, tables and charts (market size, funnel, roadmap, costs, projections, cash position, risk matrix), the agent that wrote it, and "calculated" on the figures the API works out; figures that fail a check are flagged. **Edit** turns a section into a form, tables included.
- **Open PDF** shows the document in a pop-up, in the browser's PDF viewer, with its download. There, **Ask the team to revise the proposal** sends an instruction for one part, or the whole proposal; the parts built on it follow, and the PDF is drawn again.
- **Rewrite the proposal** and **Reset to the latest results** ask before they replace anything. A change refused because the report changed elsewhere reloads it and says so.

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
src/app/layout.tsx                         Root layout: the sidebar and the backend provider
src/app/page.tsx                           The Evaluate page
src/app/reports/page.tsx                   The Reports page
src/components/evaluate/evaluate-app.tsx   The session: requests, follow-ups, progress, errors
src/components/evaluate/request-form.tsx   The first request: scenario, idea and context
src/components/evaluate/result-view.tsx    One result: strategy, plan, reports, reviews, conflicts, metrics
src/components/evaluate/working.tsx        Progress while the team works (also used for the proposal)
src/components/reports/reports-app.tsx     The Reports page: choosing, writing, editing, resetting
src/components/reports/proposal-view.tsx   The proposal's sections on screen
src/components/reports/charts.tsx          The proposal's charts, in HTML and CSS
src/components/reports/edit-form.tsx       The forms that edit each part, tables included
src/components/reports/pdf-panel.tsx       The PDF pop-up: the revise prompt, download and viewer
src/components/reports/team-report.tsx     The team's report, read or edited
src/components/sidebar.tsx                 Pages, backend status and reasoning sliders
src/components/reasoning-sliders.tsx       The two reasoning sliders
src/components/markdown.tsx                The agents' markdown, with assumptions highlighted
src/components/ui/tabs.tsx                 Accessible tabs
src/components/ui/dialog.tsx               The modal pop-up, on the browser's <dialog>
src/components/ui/badge.tsx                Small labels (sources, verdicts, states)
src/lib/api.ts                             Typed client for the backend
src/lib/backend.tsx                        The backend's status and the chosen efforts, app-wide
src/lib/team.ts                            The team's names and how long a request takes
src/lib/proposal.ts                        The proposal's parts, and its metrics in words
```

The types in `src/lib/api.ts` mirror the backend's request and response models in `main.py` and `state.py`; change them together.

`npm audit` reports two advisories, both in build-time tooling, not in the app the browser runs: a high-severity one in `braces` (through `eslint-config-next`, linting only) and a moderate one in `postcss-selector-parser` (through `@tailwindcss/typography`, which only parses this project's own CSS at build time). `npm audit fix --force` would downgrade `eslint-config-next` to Next.js 14 and the typography plugin to an old release, so both are left until those packages update.

`AGENTS.md` is written by Next.js for coding agents. It points them to the docs that ship with this version (`node_modules/next/dist/docs/`), which differ from older Next.js versions.

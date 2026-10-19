# Frontend (Next.js)

The Next.js frontend for the AI Startup Co-Founder Team, which will replace the Streamlit UI. It has the **Evaluate** page: run the founding team on an idea and send follow-ups in the same session, with reasoning sliders in the sidebar. The Reports page comes next; until then the sidebar links to the Streamlit UI's.

Created with `create-next-app` 16.4.2: TypeScript, App Router, Tailwind CSS and ESLint, with the code under `src/`.

## Setup

Requires Node.js 20.9 or newer.

```bash
cd frontend
npm install
cp .env.example .env.local
```

`.env.local` holds the backend's address (`NEXT_PUBLIC_API_URL`, http://localhost:8000 by default) and the Streamlit UI's (`NEXT_PUBLIC_STREAMLIT_URL`, for the Reports link). Both are built into the browser bundle, so they must never hold a secret.

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

## Check

```bash
npm run lint
npm test                 # unit tests (Vitest and React Testing Library)
npm run test:coverage    # the same, failing below 80% coverage
npm run build            # also type-checks
```

The tests replace the backend with a fake (`src/test/backend.ts`), so they need no server.

## What's here

```
src/app/layout.tsx                         Root layout: the sidebar and the backend provider
src/app/page.tsx                           The Evaluate page
src/components/evaluate/evaluate-app.tsx   The session: requests, follow-ups, progress, errors
src/components/evaluate/request-form.tsx   The first request: scenario, idea and context
src/components/evaluate/result-view.tsx    One result: strategy, plan, reports, reviews, conflicts, metrics
src/components/evaluate/working.tsx        Progress while the team works
src/components/sidebar.tsx                 Pages, backend status and reasoning sliders
src/components/reasoning-sliders.tsx       The two reasoning sliders
src/components/markdown.tsx                The agents' markdown, with assumptions highlighted
src/components/ui/tabs.tsx                 Accessible tabs
src/lib/api.ts                             Typed client for the backend
src/lib/backend.tsx                        The backend's status and the chosen efforts, app-wide
src/lib/team.ts                            The team's names and how long a request takes
```

The types in `src/lib/api.ts` mirror the backend's request and response models in `main.py` and `state.py`; change them together.

`npm audit` reports two advisories, both in build-time tooling, not in the app the browser runs: a high-severity one in `braces` (through `eslint-config-next`, linting only) and a moderate one in `postcss-selector-parser` (through `@tailwindcss/typography`, which only parses this project's own CSS at build time). `npm audit fix --force` would downgrade `eslint-config-next` to Next.js 14 and the typography plugin to an old release, so both are left until those packages update.

`AGENTS.md` is written by Next.js for coding agents. It points them to the docs that ship with this version (`node_modules/next/dist/docs/`), which differ from older Next.js versions.

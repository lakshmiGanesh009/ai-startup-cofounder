# Frontend (Next.js)

The Next.js frontend for the AI Startup Co-Founder Team. It is a scaffold: it is wired to the FastAPI backend, but the evaluation UI is not built yet. Until it is, use the Streamlit UI (`streamlit_app.py` in the repository root).

Created with `create-next-app` 16.4.2: TypeScript, App Router, Tailwind CSS and ESLint, with the code under `src/`.

## Setup

Requires Node.js 20.9 or newer.

```bash
cd frontend
npm install
cp .env.example .env.local
```

`NEXT_PUBLIC_API_URL` in `.env.local` is the backend's address, http://localhost:8000 by default. It is built into the browser bundle, so it must never hold a secret.

## Run

Start the backend from the repository root, then the frontend:

```bash
uv run python main.py    # repository root: the API on port 8000
npm run dev              # frontend/: http://localhost:3000
```

The home page shows whether the browser can reach the backend. If it can't, check that the backend is running and that its `CORS_ORIGINS` (in the root `.env`) includes this app's origin, http://localhost:3000 by default.

## Check

```bash
npm run lint
npm run build
```

## What's here

```
src/app/page.tsx                   Home page (placeholder)
src/app/layout.tsx                 Root layout and page metadata
src/components/backend-status.tsx  Shows whether the backend is reachable
src/lib/api.ts                     Typed client for GET /health and POST /evaluate
```

The types in `src/lib/api.ts` mirror the backend's request and response models in `main.py` and `state.py`; change them together.

A full evaluation takes a minute or more, so the UI should show progress while `evaluate()` runs.

`AGENTS.md` is written by Next.js for coding agents. It points them to the docs that ship with this version (`node_modules/next/dist/docs/`), which differ from older Next.js versions.

`npm audit` reports a high-severity advisory in `braces`, which comes in through `eslint-config-next`. It affects linting only, not the app, and `npm audit fix --force` would downgrade `eslint-config-next` to Next.js 14, so it is left until `eslint-config-next` updates.

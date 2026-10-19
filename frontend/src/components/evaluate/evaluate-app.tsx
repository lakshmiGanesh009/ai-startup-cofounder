"use client";

// The Evaluate page: run the founding team on an idea, then send follow-ups in
// the same session. The session's requests are kept in this browser tab, so a
// reload does not lose a result that took minutes.

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { RequestForm } from "@/components/evaluate/request-form";
import { ResultView } from "@/components/evaluate/result-view";
import { Working } from "@/components/evaluate/working";
import { evaluate, type EvaluateResponse, getScenarios, type RequestContext, type Scenario } from "@/lib/api";
import { useBackend } from "@/lib/backend";

const STORAGE_KEY = "cofounder-session";

type Run = { prompt: string; result: EvaluateResponse };
type Saved = { runs: Run[]; followUp: string };

function restore(): Saved {
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) ?? "") as Partial<Saved>;
    return { runs: saved.runs ?? [], followUp: saved.followUp ?? "" };
  } catch {
    return { runs: [], followUp: "" };
  }
}

const neverChanges = () => () => {};

export function EvaluateApp() {
  // The session is kept in this tab's storage, which the server cannot read,
  // so it is read only once the page runs in the browser.
  const inBrowser = useSyncExternalStore(neverChanges, () => true, () => false);
  return inBrowser ? <Session /> : <Intro />;
}

function Intro({ children }: { children?: React.ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Evaluate an idea</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          The Chief of Staff plans the work, four specialists analyse it, and the team reviews and
          reconciles their reports into one launch strategy.
        </p>
      </div>
      {children}
    </header>
  );
}

function Session() {
  const { reasoning } = useBackend();
  const [saved] = useState(restore);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [runs, setRuns] = useState<Run[]>(saved.runs);
  const [followUp, setFollowUp] = useState(saved.followUp);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getScenarios()
      .then(setScenarios)
      .catch(() => setScenarios([]));
  }, []);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ runs, followUp }));
    } catch {
      // Storage can be full or unavailable; the page still works without it.
    }
  }, [runs, followUp]);

  const latest = runs.at(-1);

  async function send(prompt: string, context: RequestContext) {
    setError(null);
    setPending(prompt);
    try {
      const result = await evaluate({
        prompt,
        context: Object.keys(context).length ? context : null,
        session_id: latest?.result.session_id ?? null,
        reasoning,
      });
      setRuns((current) => [...current, { prompt, result }]);
      return true;
    } catch (reason) {
      setError((reason as Error).message);
      return false;
    } finally {
      setPending(null);
    }
  }

  function startOver() {
    setRuns([]);
    setFollowUp("");
    setError(null);
  }

  return (
    <div className="space-y-8">
      <Intro>
        {latest && (
          <div className="flex items-center gap-3 text-xs text-zinc-500">
            <span>Session {latest.result.session_id.slice(0, 8)}</span>
            <button
              type="button"
              onClick={startOver}
              disabled={Boolean(pending)}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              Start a new session
            </button>
          </div>
        )}
      </Intro>

      {!latest && !pending && (
        <RequestForm
          scenarios={scenarios}
          busy={Boolean(pending)}
          onSubmit={send}
          onScenario={(scenario) => setFollowUp(scenario?.follow_up ?? "")}
        />
      )}

      {runs.slice(0, -1).map((run, index) => (
        <details key={run.result.session_id + index} className="rounded-lg border border-zinc-200 dark:border-zinc-800">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium">
            Request {index + 1}: {run.prompt}
          </summary>
          <div className="border-t border-zinc-200 p-4 dark:border-zinc-800">
            <ResultView result={run.result} />
          </div>
        </details>
      ))}

      {latest && (
        <section aria-labelledby="latest-request" className="space-y-4">
          <h2 id="latest-request" className="text-lg font-semibold">
            Request {runs.length}: {latest.prompt}
          </h2>
          <ResultView result={latest.result} />
          <Link
            href={`/reports?session=${encodeURIComponent(latest.result.session_id)}`}
            className="inline-flex rounded-md border border-accent px-3 py-1.5 text-sm font-medium text-accent-strong hover:bg-accent-soft/40 dark:text-accent-soft dark:hover:bg-accent/10"
          >
            Open this session&apos;s report: edit it, write the investment proposal, get the PDF
          </Link>
        </section>
      )}

      {pending && <Working prompt={pending} reasoning={reasoning} />}

      {error && (
        <p role="alert" className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {error}
        </p>
      )}

      {latest && (
        <form
          aria-label="Follow-up"
          className="flex flex-col gap-2 border-t border-zinc-200 pt-6 sm:flex-row dark:border-zinc-800"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!followUp.trim()) return;
            if (await send(followUp.trim(), {})) setFollowUp("");
          }}
        >
          <label htmlFor="follow-up" className="sr-only">
            Follow-up in this session
          </label>
          <input
            id="follow-up"
            value={followUp}
            onChange={(event) => setFollowUp(event.target.value)}
            placeholder="Follow-up in this session, e.g. Refine the pricing strategy after financial review."
            className="flex-1 rounded-md border border-zinc-300 bg-surface px-3 py-2 text-sm focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none dark:border-zinc-700"
          />
          <button
            type="submit"
            disabled={Boolean(pending) || !followUp.trim()}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send follow-up
          </button>
        </form>
      )}
    </div>
  );
}

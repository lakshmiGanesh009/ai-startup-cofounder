"use client";

// The Evaluate page: run the founding team on an idea and watch it work, then
// send follow-ups in the same session. The session's requests are kept in this
// browser tab, so a reload does not lose a result that took minutes.

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { ActivityLog } from "@/components/evaluate/activity-log";
import { Composer } from "@/components/evaluate/composer";
import { ResultView, type Run } from "@/components/evaluate/result-view";
import { TeamProgress } from "@/components/evaluate/team-progress";
import { Button } from "@/components/ui/button";
import { inputClass, Label } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { Clock } from "@/components/ui/progress";
import { evaluateStream, getScenarios, type RequestContext, type Scenario, type Step } from "@/lib/api";
import { useBackend } from "@/lib/backend";
import { evaluationWait } from "@/lib/team";

const STORAGE_KEY = "cofounder-session";
const DESCRIPTION =
  "Describe an idea or a decision. The Chief of Staff plans the work, four specialists analyse it, and the team reviews and reconciles their reports into one launch strategy.";

type Saved = { runs: Run[]; followUp: string };
type Pending = { prompt: string; steps: Step[] };

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
  return inBrowser ? <Session /> : <PageHeader title="Evaluate an idea" description={DESCRIPTION} />;
}

function LiveRun({ pending, wait }: { pending: Pending; wait: string }) {
  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    section.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, []);

  return (
    <section ref={section} aria-label="The team is working" aria-busy="true" className="scroll-mt-8">
      <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-3 border-b border-rule pb-6">
        <div className="max-w-3xl">
          <p className="kicker flex items-center gap-2">
            <span aria-hidden className="working-dot size-1.5 rounded-full bg-primary" />
            The team is working
          </p>
          <p className="mt-2 font-serif text-xl leading-snug">{pending.prompt}</p>
        </div>
        <div className="text-right">
          <Clock className="text-lg" />
          <p className="mt-0.5 text-xs text-ink-3">{wait}</p>
        </div>
      </div>
      <div className="mt-8 grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <ActivityLog steps={pending.steps} />
        <TeamProgress steps={pending.steps} live />
      </div>
    </section>
  );
}

function Session() {
  const { reasoning } = useBackend();
  const [saved] = useState(restore);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [runs, setRuns] = useState<Run[]>(saved.runs);
  // The request shown; null for the latest.
  const [shown, setShown] = useState<number | null>(null);
  const [followUp, setFollowUp] = useState(saved.followUp);
  const [pending, setPending] = useState<Pending | null>(null);
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
  const index = shown === null ? runs.length - 1 : Math.min(shown, runs.length - 1);
  const wait = evaluationWait(reasoning);

  async function send(prompt: string, context: RequestContext) {
    setError(null);
    setPending({ prompt, steps: [] });
    let seconds: number | undefined;
    try {
      const result = await evaluateStream(
        {
          prompt,
          context: Object.keys(context).length ? context : null,
          session_id: latest?.result.session_id ?? null,
          reasoning,
        },
        (step) => {
          seconds = step.at;
          setPending((current) => current && { ...current, steps: [...current.steps, step] });
        },
      );
      setRuns((current) => [...current, { prompt, result, seconds }]);
      setShown(null);
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
    setShown(null);
    setFollowUp("");
    setError(null);
  }

  return (
    <div>
      <PageHeader
        title="Evaluate an idea"
        description={DESCRIPTION}
        aside={
          latest && (
            <div className="flex items-center gap-3">
              <span className="text-xs text-ink-3">
                Session <span className="font-mono">{latest.result.session_id.slice(0, 8)}</span>
              </span>
              <Button size="sm" onClick={startOver} disabled={Boolean(pending)}>
                Start a new session
              </Button>
            </div>
          )
        }
      />

      {!latest && !pending && (
        <div className="mt-10 grid grid-cols-1 gap-14 lg:grid-cols-[minmax(0,1fr)_19rem]">
          <Composer
            scenarios={scenarios}
            wait={wait}
            busy={Boolean(pending)}
            onSubmit={send}
            onScenario={(scenario) => setFollowUp(scenario.follow_up ?? "")}
          />
          <TeamProgress steps={[]} live={false} />
        </div>
      )}

      {runs.length > 1 && (
        <nav aria-label="Requests in this session" className="mt-8 flex gap-2 overflow-x-auto pb-1">
          {runs.map((run, number) => (
            <button
              key={`${run.result.session_id}-${number}`}
              type="button"
              aria-current={number === index ? "true" : undefined}
              onClick={() => setShown(number)}
              className={`w-64 shrink-0 rounded-md border px-3 py-2 text-left transition-colors ${
                number === index
                  ? "border-ink-3 bg-surface"
                  : "border-rule text-ink-2 hover:border-rule-strong hover:bg-surface/60"
              }`}
            >
              <span className="kicker block">Request {number + 1}</span>
              <span className="mt-0.5 block truncate text-sm">{run.prompt}</span>
            </button>
          ))}
        </nav>
      )}

      {runs[index] && (
        <div className="mt-10">
          <ResultView run={runs[index]} number={index + 1} />
        </div>
      )}

      {pending && (
        <div className="mt-12">
          <LiveRun pending={pending} wait={wait} />
        </div>
      )}

      {error && (
        <Notice tone="bad" className="mt-8">
          {error}
        </Notice>
      )}

      {latest && !pending && (
        <form
          aria-label="Follow-up"
          className="mt-16 rounded-lg border border-rule bg-surface p-5"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!followUp.trim()) return;
            if (await send(followUp.trim(), {})) setFollowUp("");
          }}
        >
          <Label htmlFor="follow-up">Follow up in this session</Label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              id="follow-up"
              value={followUp}
              onChange={(event) => setFollowUp(event.target.value)}
              placeholder="Refine the pricing strategy after financial review."
              className={inputClass}
            />
            <Button type="submit" variant="primary" disabled={!followUp.trim()}>
              Send follow-up
            </Button>
          </div>
          <p className="mt-2 text-xs text-ink-3">
            Only the specialists the follow-up concerns work again; the rest keep their reports. {wait}
          </p>
        </form>
      )}
    </div>
  );
}

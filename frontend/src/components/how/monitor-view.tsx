"use client";

// The Monitor: what the API has done since it started (GET /monitoring),
// refreshed every few seconds while it is open: the totals, where the time goes
// step by step, the latest evaluations, and a log of each step, run, brief and
// proposal, with the warnings and errors, Azure's retries among them.

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { ArrowRightIcon, PulseIcon, RefreshIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/notice";
import { getMonitoring, type MonitorEvent, type Monitoring } from "@/lib/api";
import { formatSeconds, specialistTitle } from "@/lib/team";

const REFRESH_MS = 5000;

// The graph's steps, in the order they run.
const NODE_ORDER = ["plan", "research", "marketing", "finance", "technical", "risk", "review", "critique", "resolve", "synthesis"];
const NODE_NAMES: Record<string, string> = {
  plan: "Plan",
  research: "Research",
  review: "Review",
  critique: "Cross-check",
  resolve: "Resolve",
  synthesis: "Strategy",
  evaluate: "Evaluation",
  brief: "Brief",
  proposal: "Proposal",
};

function nodeName(node: string): string {
  return NODE_NAMES[node] ?? specialistTitle(node);
}

function compact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(Math.round(value));
}

// An average count: "2", or "1.5", never "2.0".
function mean(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const KIND_TONE: Record<MonitorEvent["kind"], "neutral" | "primary" | "good" | "warn" | "bad"> = {
  start: "neutral",
  done: "good",
  run: "primary",
  brief: "primary",
  proposal: "primary",
  warning: "warn",
  error: "bad",
};

const FILTERS = {
  all: { label: "All", kinds: null },
  steps: { label: "Steps", kinds: ["start", "done"] },
  work: { label: "Runs, briefs, proposals", kinds: ["run", "brief", "proposal"] },
  problems: { label: "Warnings and errors", kinds: ["warning", "error"] },
} as const;
type Filter = keyof typeof FILTERS;

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="bg-surface px-4 py-3.5">
      <p className="kicker">{label}</p>
      <p className="mt-1 text-[1.6rem] leading-tight font-medium tabular">{value}</p>
      <p className="mt-0.5 text-xs text-ink-3">{note}</p>
    </div>
  );
}

function Totals({ data }: { data: Monitoring }) {
  const { totals } = data;
  // The averages are over the evaluations that finished: one that failed
  // never reached the strategy.
  const finished = Math.max(totals.evaluations - totals.failures, 1);
  const share = totals.reviewed ? Math.round((totals.approved / totals.reviewed) * 100) : 0;
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-rule bg-rule md:grid-cols-4">
      <Tile
        label="Evaluations"
        value={String(totals.evaluations)}
        note={totals.failures ? `${totals.failures} failed` : "none failed"}
      />
      <Tile label="Average time" value={formatSeconds(totals.seconds / finished)} note="from brief to strategy" />
      <Tile label="Model calls" value={compact(totals.calls)} note={`${mean(totals.calls / finished)} an evaluation`} />
      <Tile label="Tokens" value={compact(totals.tokens)} note={`${compact(totals.tokens / finished)} an evaluation`} />
      <Tile
        label="Reports approved"
        value={totals.reviewed ? `${totals.approved} of ${totals.reviewed}` : "–"}
        note={totals.reviewed ? `${share}% passed review` : "no reviews yet"}
      />
      <Tile label="Conflicts settled" value={String(totals.conflicts)} note="by the Chief of Staff" />
      <Tile
        label="Web research"
        value={`${totals.searches} · ${totals.credits}`}
        note="Bing searches · Tavily credits"
      />
      <Tile label="Briefs · proposals" value={`${totals.briefs} · ${totals.proposals}`} note="prepared · written" />
    </div>
  );
}

function TimeByStep({ data }: { data: Monitoring }) {
  const nodes = [...data.nodes].sort((a, b) => NODE_ORDER.indexOf(a.node) - NODE_ORDER.indexOf(b.node));
  const longest = Math.max(1, ...nodes.map((node) => node.seconds / Math.max(node.runs, 1)));
  return (
    <section aria-labelledby="time-heading" className="max-w-2xl">
      <h3 id="time-heading" className="kicker">
        Where the time goes, per evaluation
      </h3>
      <ul className="mt-3 space-y-2.5">
        {nodes.map((node) => {
          const runs = Math.max(node.runs, 1);
          const seconds = node.seconds / runs;
          const calls = node.calls / runs;
          return (
            <li key={node.node} className="grid grid-cols-[8.5rem_minmax(0,1fr)] items-center gap-3 text-sm">
              <span className="truncate text-ink-2">{nodeName(node.node)}</span>
              <span>
                <span className="flex items-baseline justify-between gap-3 text-xs">
                  <span className="font-medium text-ink tabular">{seconds.toFixed(1)} s</span>
                  <span className="text-ink-3 tabular">
                    {mean(calls)} {calls === 1 ? "call" : "calls"} · {compact(node.tokens / runs)} tokens
                  </span>
                </span>
                <span className="mt-1 block h-1.5 rounded-full bg-sunken">
                  <span
                    className="block h-full rounded-full"
                    title={`${nodeName(node.node)}: ${seconds.toFixed(1)} s on average over ${node.runs} runs`}
                    style={{ width: `${Math.max(1.5, (seconds / longest) * 100)}%`, background: "var(--data-1)" }}
                  />
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-ink-3">
        The specialists run at the same time, so an evaluation takes far less than these add up to.
      </p>
    </section>
  );
}

function Runs({ data }: { data: Monitoring }) {
  return (
    <section aria-labelledby="runs-heading">
      <h3 id="runs-heading" className="kicker">
        Latest evaluations
      </h3>
      <div className="relative mt-3 overflow-x-auto">
        <table className="w-full min-w-[46rem] text-left text-sm">
          <thead>
            <tr className="border-b border-rule-strong text-xs text-ink-3">
              {["At", "Session", "Team", "Time", "Calls", "Tokens", "Approved", "Conflicts", "Research", ""].map((head) => (
                <th key={head} className="py-2 pr-4 font-medium">
                  {head}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {data.runs.map((run) => (
              <tr key={`${run.session}-${run.at}`} className="align-top">
                <td className="py-2 pr-4 font-mono text-xs text-ink-3">{clock(run.at)}</td>
                <td className="py-2 pr-4 font-mono text-xs">{run.session}</td>
                <td className="py-2 pr-4 tabular">{run.specialists.length || "–"}</td>
                <td className="py-2 pr-4 tabular">{formatSeconds(run.seconds)}</td>
                <td className="py-2 pr-4 tabular">{run.ok ? run.calls : "–"}</td>
                <td className="py-2 pr-4 tabular">{run.ok ? compact(run.tokens) : "–"}</td>
                <td className="py-2 pr-4 tabular">{run.ok ? `${run.approved} of ${run.reviewed}` : "–"}</td>
                <td className="py-2 pr-4 tabular">{run.ok ? run.conflicts : "–"}</td>
                <td className="py-2 pr-4 text-xs text-ink-2">
                  {run.research
                    ? `${run.research}${run.searches ? `, ${run.searches} searches` : ""}${run.credits ? `, ${run.credits} credits` : ""}`
                    : "–"}
                </td>
                <td className="py-2" title={run.error ?? undefined}>
                  {run.ok ? <Badge tone="good">Done</Badge> : <Badge tone="bad">Failed</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Log({ data }: { data: Monitoring }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [shown, setShown] = useState(40);
  const kinds: readonly string[] | null = FILTERS[filter].kinds;
  const events = data.events.filter((event) => !kinds || kinds.includes(event.kind));
  return (
    <section aria-labelledby="log-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="log-title" className="kicker">
          Log
        </h3>
        <div role="group" aria-label="Show in the log" className="flex flex-wrap gap-1.5">
          {(Object.keys(FILTERS) as Filter[]).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
              className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                filter === key ? "border-primary bg-primary-soft text-ink" : "border-rule-strong text-ink-2 hover:text-ink"
              }`}
            >
              {FILTERS[key].label}
            </button>
          ))}
        </div>
      </div>
      {events.length ? (
        <ol className="mt-3 divide-y divide-rule border-y border-rule">
          {events.slice(0, shown).map((event, index) => (
            <li key={`${event.at}-${index}`} className="grid grid-cols-[4.5rem_6.5rem_minmax(0,1fr)] gap-3 py-2 text-sm">
              <span className="pt-0.5 font-mono text-xs text-ink-3">{clock(event.at)}</span>
              <span>
                <Badge tone={KIND_TONE[event.kind]}>{event.kind}</Badge>
              </span>
              <span className="min-w-0">
                <span className="font-medium text-ink">{nodeName(event.source)}</span>{" "}
                <span className={event.kind === "error" ? "text-bad" : event.kind === "warning" ? "text-warn" : "text-ink-2"}>
                  {event.message}
                </span>
                {event.session && <span className="ml-2 font-mono text-[11px] text-ink-3">{event.session}</span>}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-3 text-sm text-ink-3">Nothing here yet.</p>
      )}
      {events.length > shown && (
        <Button size="sm" className="mt-3" onClick={() => setShown((current) => current + 60)}>
          Show older
        </Button>
      )}
    </section>
  );
}

export function MonitorView({ active }: { active: boolean }) {
  const [data, setData] = useState<Monitoring | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [updated, setUpdated] = useState<string | null>(null);

  const refresh = useCallback(() => {
    getMonitoring()
      .then((answer) => {
        setData(answer);
        setProblem(null);
        setUpdated(new Date().toISOString());
      })
      .catch((error: Error) => setProblem(error.message));
  }, []);

  useEffect(() => {
    if (!active || paused) return;
    refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [active, paused, refresh]);

  const quiet = data && !data.events.length && !data.runs.length;
  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm text-ink-2">
          <PulseIcon className="size-4 text-primary" />
          {data ? `Since the API started at ${clock(data.started_at)}.` : "Asking the API…"}
          {updated && <span className="text-ink-3">Updated at {clock(updated)}.</span>}
        </p>
        <div className="flex gap-2">
          <Button size="sm" aria-pressed={paused} onClick={() => setPaused((current) => !current)}>
            {paused ? "Resume" : "Pause"}
          </Button>
          <Button size="sm" onClick={refresh}>
            <RefreshIcon className="size-3.5" />
            Refresh
          </Button>
        </div>
      </div>
      {problem && <Notice tone="bad">{problem}</Notice>}
      {quiet && (
        <div className="rounded-lg border border-rule bg-surface p-6">
          <p className="font-serif text-xl">Nothing has run since the API started.</p>
          <p className="mt-1 text-sm text-ink-2">
            Evaluate an idea, and each step, its time and its cost show up here as it happens. The monitor lives in the
            API&apos;s memory, so a restart empties it.
          </p>
          <ButtonLink href="/" variant="primary" className="mt-4">
            Evaluate an idea
            <ArrowRightIcon className="size-3.5" />
          </ButtonLink>
        </div>
      )}
      {data && !quiet && (
        <>
          <Totals data={data} />
          {data.nodes.length > 0 && (
            <div className="grid grid-cols-1 gap-10 2xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
              <TimeByStep data={data} />
              {data.runs.length > 0 && <Runs data={data} />}
            </div>
          )}
          <Log data={data} />
        </>
      )}
    </div>
  );
}

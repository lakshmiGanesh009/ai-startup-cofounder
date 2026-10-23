"use client";

// The Monitor: what the API has done since it started (GET /monitoring),
// refreshed every few seconds while it is open: whether anything went wrong
// lately, which providers it calls (Azure OpenAI, Tavily, FRED) and how
// each stands and is used, the totals and error rates, how long an evaluation and each of its
// steps take (the median and the 95th percentile), the latest evaluations, and
// a log of each step, run, brief, proposal, file and question, with the warnings and errors.
// It asks one request at a time; when the API stops answering it keeps showing
// what it last heard and waits longer between tries.

import { useCallback, useEffect, useRef, useState } from "react";

import { AgentAvatar, AgentStack } from "@/components/ui/agent";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { AlertIcon, ArrowRightIcon, CheckIcon, PulseIcon, RefreshIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/notice";
import {
  getMonitoring,
  type MonitorEvent,
  type MonitorHealth,
  type Monitoring,
  type ProviderKey,
  type ProviderUse,
  type ServiceUse,
} from "@/lib/api";
import { agentFill, agentOf, agentsOf, agentsOfSource } from "@/lib/agents";
import { formatSeconds, stepName } from "@/lib/team";

const REFRESH_MS = 5000;
// An answer slower than this counts as a failure; and the longest wait between
// tries while the API is not answering.
const PATIENCE_MS = 10_000;
const LONGEST_WAIT_MS = 60_000;

// The graph's steps, in the order they run.
const NODE_ORDER = ["plan", "research", "marketing", "finance", "technical", "risk", "review", "critique", "resolve", "synthesis"];
function compact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(Math.round(value));
}

// An average count: "2", or "1.5", never "2.0".
function mean(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function percent(value: number): string {
  if (value === 0 || value >= 10) return `${Math.round(value)}%`;
  return `${value.toFixed(1)}%`;
}

function plural(count: number, one: string): string {
  return `${count} ${count === 1 ? one : `${one}s`}`;
}

function clock(time: string | number): string {
  return new Date(time).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const KIND_TONE: Record<MonitorEvent["kind"], "neutral" | "primary" | "good" | "warn" | "bad"> = {
  start: "neutral",
  done: "good",
  run: "primary",
  brief: "primary",
  proposal: "primary",
  document: "primary",
  warning: "warn",
  error: "bad",
  system: "neutral",
};

const FILTERS = {
  all: { label: "All", kinds: null },
  steps: { label: "Steps", kinds: ["start", "done"] },
  work: { label: "Runs, briefs, proposals, files", kinds: ["run", "brief", "proposal", "document"] },
  problems: { label: "Warnings and errors", kinds: ["warning", "error"] },
} as const;
type Filter = keyof typeof FILTERS;

const HEALTH = {
  healthy: { tone: "bg-good-soft text-good", Glyph: CheckIcon, label: "Healthy" },
  warnings: { tone: "bg-warn-soft text-warn", Glyph: AlertIcon, label: "Warnings" },
  errors: { tone: "bg-bad-soft text-bad", Glyph: AlertIcon, label: "Errors" },
};

function HealthStrip({ health, running, onShow }: { health: MonitorHealth; running: number; onShow: () => void }) {
  const { tone, Glyph, label } = HEALTH[health.status];
  const problems = [
    health.errors ? plural(health.errors, "error") : "",
    health.warnings ? plural(health.warnings, "warning") : "",
  ]
    .filter(Boolean)
    .join(" and ");
  return (
    <div role="status" className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg px-4 py-3 text-sm ${tone}`}>
      <span className="flex items-center gap-2 font-medium">
        <Glyph className="size-4" />
        {label}
      </span>
      <span className="text-ink-2">
        {problems
          ? `${problems} in the last ${health.minutes} minutes.`
          : `No warnings or errors in the last ${health.minutes} minutes.`}
      </span>
      {problems && (
        <Button size="sm" onClick={onShow}>
          Show them
        </Button>
      )}
      <span className="flex items-center gap-2 text-ink-2 sm:ml-auto">
        {running > 0 && (
          <span aria-hidden className="size-2 animate-pulse rounded-full bg-primary motion-reduce:animate-none" />
        )}
        {running ? `${plural(running, "evaluation")} running now` : "Nothing running now"}
      </span>
    </div>
  );
}

// ---- The providers ----

const PROVIDER_NAMES: Record<ProviderKey, string> = {
  azure: "Azure OpenAI",
  openai: "OpenAI",
  tavily: "Tavily",
  fred: "FRED",
};

const SERVICE_NAMES: Record<ServiceUse["service"], string> = {
  model: "Model",
  "web search": "Web search",
  research: "Research",
  speech: "Dictation",
  figures: "Figures",
  "competitor pages": "Pricing pages",
};

// What to set to turn a provider on.
const SET_UP_WITH: Record<ProviderKey, string> = {
  azure: "Set AZURE_OPENAI_API_KEY, with its endpoint and deployment.",
  openai: "Set OPENAI_API_KEY.",
  tavily: "Set TAVILY_API_KEY to research on Tavily.",
  fred: "Set FRED_API_KEY for official economic figures.",
};

type Standing = { label: string; tone: "good" | "warn" | "bad" | "neutral"; dot: string };

function standingOf(provider: ProviderUse, calls: number): Standing {
  switch (provider.status) {
    case "answering":
      return { label: "Answering", tone: "good", dot: "bg-good" };
    case "failing":
      return { label: "Failing", tone: "bad", dot: "bg-bad" };
    case "ready":
      return calls ? { label: "In use", tone: "good", dot: "bg-good" } : { label: "Ready", tone: "neutral", dot: "bg-ink-3" };
    default:
      return { label: "Not set up", tone: "neutral", dot: "bg-rule-strong" };
  }
}

function ServiceLine({ use }: { use: ServiceUse }) {
  const details = [
    use.tokens_in || use.tokens_out ? `${compact(use.tokens_in)} in · ${compact(use.tokens_out)} out` : "",
    use.credits ? plural(use.credits, "credit") : "",
    use.last_at ? `last at ${clock(use.last_at)}` : "",
  ].filter(Boolean);
  return (
    <li className="py-2 first:pt-0 last:pb-0">
      <p className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-ink">{SERVICE_NAMES[use.service]}</span>
        <span className="text-ink-2 tabular">
          {plural(use.calls, "call")}
          {use.failed > 0 && <span className="text-bad"> · {use.failed} failed</span>}
        </span>
      </p>
      {details.length > 0 && <p className="mt-0.5 text-xs text-ink-3 tabular">{details.join(" · ")}</p>}
    </li>
  );
}

function ProviderCard({ provider }: { provider: ProviderUse }) {
  const name = PROVIDER_NAMES[provider.provider];
  const calls = provider.services.reduce((sum, use) => sum + use.calls, 0);
  const standing = standingOf(provider, calls);
  const failure = provider.services
    .filter((use) => use.last_failure && use.last_failure_at)
    .sort((a, b) => (b.last_failure_at ?? "").localeCompare(a.last_failure_at ?? ""))[0];
  const role = provider.role.charAt(0).toUpperCase() + provider.role.slice(1);
  return (
    <article
      aria-label={name}
      className={`flex flex-col rounded-lg border bg-surface p-4 ${standing.tone === "bad" ? "border-bad/40" : "border-rule"} ${
        provider.set_up || calls ? "" : "opacity-75"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <h4 className="min-w-0 font-medium text-ink">{name}</h4>
        <span className="shrink-0 whitespace-nowrap">
          <Badge tone={standing.tone}>
            <span aria-hidden className={`mr-1.5 size-1.5 rounded-full ${standing.dot}`} />
            {standing.label}
          </Badge>
        </span>
      </div>
      <p className="mt-0.5 text-xs leading-relaxed text-ink-3">{role}</p>
      {provider.services.length > 0 ? (
        <ul aria-label={`What ${name} was called for`} className="mt-3 divide-y divide-rule border-t border-rule pt-2.5">
          {provider.services.map((use) => (
            <ServiceLine key={use.service} use={use} />
          ))}
        </ul>
      ) : (
        <p className="mt-3 border-t border-rule pt-2.5 text-[13px] text-ink-3">
          {provider.set_up ? "Not called since the API started." : SET_UP_WITH[provider.provider]}
        </p>
      )}
      {failure && (
        <div title={failure.last_failure ?? undefined} className="mt-3 rounded-md bg-bad-soft px-3 py-2 text-xs text-bad">
          <p className="line-clamp-4 leading-relaxed">
            <span className="font-medium">Last failure at {clock(failure.last_failure_at ?? "")}:</span>{" "}
            {failure.last_failure}
          </p>
        </div>
      )}
    </article>
  );
}

function Providers({ providers }: { providers: ProviderUse[] }) {
  return (
    <section aria-labelledby="providers-heading">
      <h3 id="providers-heading" className="kicker">
        Providers
      </h3>
      <p className="mt-1 text-sm text-ink-2">Who the API calls, how each stands now, and what each did since it started.</p>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {providers.map((provider) => (
          <ProviderCard key={provider.provider} provider={provider} />
        ))}
      </div>
    </section>
  );
}

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
  const { totals, evaluation_seconds: spread } = data;
  // The averages are over the evaluations that finished: one that failed
  // never reached the strategy.
  const finished = Math.max(totals.evaluations - totals.failures, 1);
  const share = totals.reviewed ? Math.round((totals.approved / totals.reviewed) * 100) : 0;
  const failed = totals.brief_failures + totals.proposal_failures;
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-rule bg-rule md:grid-cols-4">
      <Tile
        label="Evaluations"
        value={String(totals.evaluations)}
        note={
          totals.failures
            ? `${totals.failures} failed, ${percent((totals.failures / totals.evaluations) * 100)}`
            : "none failed"
        }
      />
      <Tile
        label="Time to a decision"
        value={spread ? formatSeconds(spread.p50) : "–"}
        note={
          spread
            ? `median · p95 ${formatSeconds(spread.p95)} · slowest ${formatSeconds(spread.max)}`
            : "none finished yet"
        }
      />
      <Tile
        label="Server errors"
        value={String(totals.server_errors)}
        note={
          totals.requests
            ? `${percent((totals.server_errors / totals.requests) * 100)} of ${plural(totals.requests, "request")}`
            : "no requests yet"
        }
      />
      <Tile
        label="Model calls"
        value={compact(totals.calls)}
        note={`${mean(totals.calls / finished)} an evaluation${totals.retries ? ` · ${totals.retries} retried` : ""}`}
      />
      <Tile label="Tokens" value={compact(totals.tokens)} note={`${compact(totals.tokens / finished)} an evaluation`} />
      <Tile
        label="Reports approved"
        value={totals.reviewed ? `${totals.approved} of ${totals.reviewed}` : "–"}
        note={
          totals.reviewed
            ? `${share}% passed review · ${plural(totals.conflicts, "conflict")} settled`
            : "no reviews yet"
        }
      />
      <Tile label="Web research" value={`${totals.searches} · ${totals.credits}`} note="Bing searches · Tavily credits" />
      <Tile
        label="Briefs · proposals"
        value={`${totals.briefs} · ${totals.proposals}`}
        note={failed ? `prepared · written; ${failed} failed` : "prepared · written"}
      />
    </div>
  );
}

function TimeByStep({ data }: { data: Monitoring }) {
  const nodes = [...data.nodes].sort((a, b) => NODE_ORDER.indexOf(a.node) - NODE_ORDER.indexOf(b.node));
  const longest = Math.max(1, ...nodes.map((node) => node.p95));
  const at = (seconds: number) => `${Math.min(100, (seconds / longest) * 100)}%`;
  return (
    <section aria-labelledby="time-heading" className="max-w-2xl">
      <h3 id="time-heading" className="kicker">
        Where the time goes, per evaluation
      </h3>
      <ul className="mt-3 space-y-2.5">
        {nodes.map((node) => {
          const runs = Math.max(node.runs, 1);
          const calls = node.calls / runs;
          return (
            <li
              key={node.node}
              className="grid grid-cols-1 gap-1 text-sm sm:grid-cols-[11.5rem_minmax(0,1fr)] sm:items-center sm:gap-3"
            >
              <span className="flex min-w-0 items-center gap-2 text-ink-2">
                {agentsOf(node.node).length > 1 ? (
                  <AgentStack agents={agentsOf(node.node)} />
                ) : (
                  <AgentAvatar agent={agentOf(node.node)} size="xs" />
                )}
                <span className="truncate">{stepName(node.node)}</span>
              </span>
              <span>
                <span className="flex flex-wrap items-baseline justify-between gap-x-3 text-xs">
                  <span className="whitespace-nowrap tabular">
                    <span className="font-medium text-ink">{node.p50.toFixed(1)} s</span>
                    <span className="text-ink-3"> · p95 {node.p95.toFixed(1)} s</span>
                  </span>
                  <span className="whitespace-nowrap text-ink-3 tabular">
                    {mean(calls)} {calls === 1 ? "call" : "calls"} · {compact(node.tokens / runs)} tokens
                  </span>
                </span>
                <span
                  className="relative mt-1 block h-1.5 rounded-full bg-sunken"
                  title={`${stepName(node.node)}: median ${node.p50.toFixed(1)} s, p95 ${node.p95.toFixed(1)} s, over ${plural(node.runs, "evaluation")}`}
                >
                  <span
                    className="block h-full rounded-full"
                    style={{ width: `max(4px, ${at(node.p50)})`, background: agentFill(agentsOf(node.node)) }}
                  />
                  <span
                    aria-hidden
                    className="absolute -top-0.5 h-2.5 w-0.5 rounded-full bg-ink"
                    style={{ left: `calc(${at(node.p95)} - 1px)` }}
                  />
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-3">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="h-1.5 w-4 rounded-full" style={{ background: agentFill(["chief"]) }} /> median, in
          the colour of the agent who does the step
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="h-2.5 w-0.5 rounded-full bg-ink" /> 95th percentile
        </span>
        <span>The specialists run at the same time, so an evaluation takes far less than these add up to.</span>
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

function Log({
  data,
  filter,
  onFilter,
  sectionRef,
}: {
  data: Monitoring;
  filter: Filter;
  onFilter: (filter: Filter) => void;
  sectionRef: React.Ref<HTMLElement>;
}) {
  const [shown, setShown] = useState(40);
  const kinds: readonly string[] | null = FILTERS[filter].kinds;
  const events = data.events.filter((event) => !kinds || kinds.includes(event.kind));
  return (
    <section ref={sectionRef} tabIndex={-1} aria-labelledby="log-title" className="scroll-mt-8 outline-none">
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
              onClick={() => onFilter(key)}
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
            <li
              key={`${event.at}-${index}`}
              className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 py-2 text-sm sm:grid-cols-[4.5rem_6.5rem_minmax(0,1fr)]"
            >
              <span className="pt-0.5 font-mono text-xs text-ink-3">{clock(event.at)}</span>
              <span>
                <Badge tone={KIND_TONE[event.kind]}>{event.kind}</Badge>
              </span>
              <span className="col-span-2 min-w-0 sm:col-span-1">
                {agentsOfSource(event.source).length === 1 && (
                  <AgentAvatar agent={agentsOfSource(event.source)[0]} size="xs" className="mr-1.5 align-[-5px]" />
                )}
                {agentsOfSource(event.source).length > 1 && (
                  <span className="mr-1.5 inline-flex align-[-5px]">
                    <AgentStack agents={agentsOfSource(event.source)} />
                  </span>
                )}
                <span className="font-medium text-ink">{stepName(event.source)}</span>{" "}
                <span className={event.kind === "error" ? "text-bad" : event.kind === "warning" ? "text-warn" : "text-ink-2"}>
                  {event.message}
                </span>
                {event.session && <span className="ml-2 font-mono text-[11px] text-ink-3">{event.session}</span>}
                {/* The request a problem happened in, to find its lines in the API's logs. */}
                {event.request && (event.kind === "warning" || event.kind === "error") && (
                  <span className="ml-2 font-mono text-[11px] text-ink-3" title={`Request ${event.request}`}>
                    request {event.request.slice(0, 8)}
                  </span>
                )}
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

type Asked = { ok: true } | { ok: false; message: string };
// Why the API is not being heard from, and when it is asked again (none while paused).
type Trouble = { message: string; next: number | null };

export function MonitorView({ active }: { active: boolean }) {
  const [data, setData] = useState<Monitoring | null>(null);
  const [trouble, setTrouble] = useState<Trouble | null>(null);
  const [paused, setPaused] = useState(false);
  const [updated, setUpdated] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  // Bumped to ask again now, from the start.
  const [round, setRound] = useState(0);
  const asking = useRef<Promise<Asked> | null>(null);
  const logRef = useRef<HTMLElement>(null);

  // One request at a time: asking while one is on its way waits for that one.
  // A request is given up after PATIENCE_MS.
  const ask = useCallback((): Promise<Asked> => {
    asking.current ??= (async (): Promise<Asked> => {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), PATIENCE_MS);
      try {
        const answer = await getMonitoring(controller.signal);
        setData(answer);
        setTrouble(null);
        setUpdated(new Date().toISOString());
        return { ok: true };
      } catch (error) {
        const message = controller.signal.aborted
          ? `The API took more than ${PATIENCE_MS / 1000} s to answer.`
          : (error as Error).message;
        return { ok: false, message };
      } finally {
        window.clearTimeout(timer);
        asking.current = null;
      }
    })();
    return asking.current;
  }, []);

  // While shown and not paused: every REFRESH_MS, or after a failure 10, 20,
  // 40 and then 60 s, and at once when the page is shown again.
  useEffect(() => {
    if (!active || paused) return;
    let stopped = false;
    let timer: number | undefined;
    let failures = 0;
    let latest = 0; // only the latest poll sets the next one

    async function poll() {
      window.clearTimeout(timer);
      const mine = ++latest;
      const asked = await ask();
      if (stopped || mine !== latest) return;
      failures = asked.ok ? 0 : failures + 1;
      const wait = failures ? Math.min(LONGEST_WAIT_MS, REFRESH_MS * 2 ** failures) : REFRESH_MS;
      if (!asked.ok) setTrouble({ message: asked.message, next: Date.now() + wait });
      timer = window.setTimeout(() => {
        if (document.visibilityState === "visible") void poll();
      }, wait);
    }

    function shown() {
      if (document.visibilityState === "visible") void poll();
    }

    void poll();
    document.addEventListener("visibilitychange", shown);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", shown);
    };
  }, [active, paused, round, ask]);

  function refresh() {
    if (!paused) {
      setRound((current) => current + 1);
      return;
    }
    void ask().then((asked) => {
      if (!asked.ok) setTrouble({ message: asked.message, next: null });
    });
  }

  function showProblems() {
    setFilter("problems");
    logRef.current?.focus();
  }

  // Nothing has run when the log holds no more than the API's own start.
  const quiet = data && !data.runs.length && data.events.every((event) => event.kind === "system");
  return (
    <div className="space-y-10">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex flex-wrap items-center gap-x-2 text-sm text-ink-2">
            <PulseIcon className="size-4 text-primary" />
            {data ? `Since the API started at ${clock(data.started_at)}.` : trouble ? "" : "Asking the API…"}
            {data?.kept_in === "postgres" && <span className="text-ink-3">History kept in PostgreSQL.</span>}
            {updated && (
              <span className={trouble ? "text-warn" : "text-ink-3"}>
                Updated at {clock(updated)}
                {trouble ? ", not since." : "."}
              </span>
            )}
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
        {/* While the API is not answering, this stands in for the health it last reported. */}
        {trouble ? (
          <Notice tone="bad">
            <p>
              {data ? "The API stopped answering" : "The API is not answering"}: {trouble.message}
              {data && updated ? ` Showing what it reported at ${clock(updated)}.` : ""}
              {trouble.next ? ` Trying again at ${clock(trouble.next)}.` : ""}
            </p>
            <Button size="sm" className="mt-2" onClick={refresh}>
              Try now
            </Button>
          </Notice>
        ) : (
          data && <HealthStrip health={data.health} running={data.running} onShow={showProblems} />
        )}
      </div>
      {data?.providers && data.providers.length > 0 && <Providers providers={data.providers} />}
      {quiet && (
        <div className="rounded-lg border border-rule bg-surface p-6">
          <p className="font-serif text-xl">Nothing has run since the API started.</p>
          <p className="mt-1 text-sm text-ink-2">
            Evaluate an idea, and each step, its time and its cost show up here as it happens.{" "}
            {data?.kept_in === "postgres"
              ? "The latest evaluations and the log are kept in PostgreSQL, so a restart keeps them; "
              : "The monitor lives in the API's memory, so a restart empties it; "}
            Prometheus can keep the counters from <code>/metrics</code>.
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
          <Log data={data} filter={filter} onFilter={setFilter} sectionRef={logRef} />
        </>
      )}
    </div>
  );
}

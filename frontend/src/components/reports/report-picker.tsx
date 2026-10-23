"use client";

// The Reports page's report picker: the open report on a button, and a pop-up
// of every report, each with what tells it from the others (its kind, verdict,
// headline figures, team, version and when it changed), searchable, filtered
// by kind and sorted, beside a preview of the one highlighted: its decision in
// brief, with its figures picked out, the figures to see at a glance, what the
// founder chose and told the team while it was built (report-choices.tsx), and
// its versions, each with what it changed from the one before (report-versions.tsx).
// The search box drives the list: the arrow keys move through it and Enter
// opens. On a phone, where there is no room for the preview, a tap opens. The
// preview can also delete a report, once the founder confirms it.

import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";

import { AgentAvatar } from "@/components/ui/agent";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/markdown";
import { YourChoices } from "@/components/reports/report-choices";
import { Versions } from "@/components/reports/report-versions";
import { Dialog } from "@/components/ui/dialog";
import { inputClass, Select } from "@/components/ui/field";
import { ArrowRightIcon, DocumentIcon, SearchIcon, TrashIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/notice";
import { Voice } from "@/components/voice";
import { AGENTS, specialistAgent } from "@/lib/agents";
import type { KeyFigure, Report, ReportFigures, ReportSummary } from "@/lib/api";
import { stamp } from "@/lib/dates";
import { CURRENCIES, money, percent } from "@/lib/proposal";

type Verdict = NonNullable<ReportSummary["verdict"]>;
type Kind = "all" | "proposal" | "team";
type Sort = "newest" | "oldest" | "title";

const VERDICT_TONE: Record<Verdict, Tone> = { Go: "good", "Go with conditions": "warn", "Not yet": "bad" };
const VERDICT_DOT: Record<Verdict, string> = { Go: "bg-good", "Go with conditions": "bg-warn", "Not yet": "bg-bad" };
const KINDS: [Kind, string][] = [
  ["all", "All"],
  ["proposal", "Investment proposals"],
  ["team", "Team reports"],
];

// "19 Oct": the day alone, for a line with no room for the time.
function day(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

function ago(iso: string, now: number): string {
  const minutes = Math.round((now - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

const name = (report: ReportSummary) => report.project_name || report.title;
const kindOf = (report: ReportSummary) => (report.has_proposal ? "Investment proposal" : "Team report");
const shortKind = (report: ReportSummary) => (report.has_proposal ? "Proposal" : "Team report");

// The open report as the list would give it, so its entry follows the changes
// made since the list was loaded.
export function withOpen(listed: ReportSummary, report: Report): ReportSummary {
  const metrics = report.investment;
  return {
    ...listed,
    title: report.title,
    objective: report.objective,
    version: report.version,
    has_proposal: Boolean(report.proposal),
    edited: report.edited,
    outdated: report.outdated,
    updated_at: report.updated_at,
    change: report.change,
    currency: report.settings.currency,
    prepared_by: report.settings.prepared_by,
    project_name: report.proposal?.executive.project_name ?? null,
    verdict: report.proposal?.executive.verdict ?? listed.verdict,
    figures: metrics
      ? {
          npv: metrics.npv,
          irr: metrics.irr,
          payback_months: metrics.payback_months,
          break_even_customers: metrics.break_even_customers,
        }
      : null,
    checks: report.checks.length,
  };
}

function irrText(irr: number | null): string {
  if (irr === null) return "None";
  return irr > 10 ? "> 1,000%" : percent(irr);
}

function paybackText(months: number | null): string {
  if (months === null) return "After year 3";
  if (months < 1) return "Under a month";
  const rounded = Math.round(months);
  return `${rounded} month${rounded === 1 ? "" : "s"}`;
}

function breakEvenText(customers: number | null): string {
  if (customers === null) return "Never";
  return `${customers.toLocaleString("en-US")} customer${customers === 1 ? "" : "s"}`;
}

function VerdictPill({ verdict }: { verdict: Verdict }) {
  return (
    <Badge tone={VERDICT_TONE[verdict]}>
      <span aria-hidden className={`mr-1.5 size-1.5 rounded-full ${VERDICT_DOT[verdict]}`} />
      {verdict}
    </Badge>
  );
}

function KindMark({ proposal }: { proposal: boolean }) {
  return (
    <span
      aria-hidden
      className={`flex size-9 shrink-0 items-center justify-center rounded-lg ${
        proposal ? "bg-primary-soft text-primary" : "bg-sunken text-ink-3"
      }`}
    >
      <DocumentIcon className="size-[18px]" />
    </span>
  );
}

// ---- The list ----

function Row({
  report,
  id,
  active,
  open,
  onPick,
  onOpen,
}: {
  report: ReportSummary;
  id: string;
  active: boolean;
  open: boolean;
  onPick: () => void;
  onOpen: () => void;
}) {
  const figures = report.figures;
  return (
    <li
      id={id}
      role="option"
      aria-selected={active}
      onClick={onPick}
      onDoubleClick={onOpen}
      className={`cursor-pointer rounded-lg border px-3.5 py-3 transition-colors ${
        active ? "border-ink-3 bg-surface shadow-[0_1px_2px_rgb(0_0_0/0.06)]" : "border-transparent hover:bg-surface/70"
      }`}
    >
      <div className="flex items-start gap-3">
        <KindMark proposal={report.has_proposal} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <p className="min-w-0 truncate font-medium text-ink">{name(report)}</p>
            {open && (
              <span className="shrink-0">
                <Badge tone="primary">Open</Badge>
              </span>
            )}
            {report.verdict && (
              // Beside the name where there is room; on a phone, on the line below.
              <span className="ml-auto hidden shrink-0 pl-1 sm:inline-flex">
                <VerdictPill verdict={report.verdict} />
              </span>
            )}
          </div>
          {report.objective && <p className="mt-0.5 line-clamp-1 text-[13px] text-ink-2">{report.objective}</p>}
          <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
            {report.verdict && (
              <span className="sm:hidden">
                <VerdictPill verdict={report.verdict} />
              </span>
            )}
            <span>{shortKind(report)}</span>
            <span aria-hidden>·</span>
            <span className="tabular">v{report.version}</span>
            <span aria-hidden>·</span>
            <span className="tabular" title={stamp(report.updated_at, true)}>
              {day(report.updated_at)}
            </span>
            {figures && (
              <>
                <span aria-hidden>·</span>
                <span className="tabular">NPV {money(figures.npv, report.currency)}</span>
              </>
            )}
            {report.edited && <Badge>Edited</Badge>}
            {report.outdated && <Badge tone="warn">Newer results</Badge>}
          </p>
        </div>
      </div>
    </li>
  );
}

// ---- The preview ----

// A figure's number, and what it is per or of after it ("/sprint", " a month", " customers").
const NUMBER_FIRST = /^(.*?\d[\d,.]*(?:\s?[–-]\s?\d[\d,.]*)?(?:\s?(?:k|K|m|M|bn|B|million|billion)\b|%)?)(.*)$/;

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  const [, number, unit] = value.match(NUMBER_FIRST) ?? [value, value, ""];
  return (
    <div className="rounded-lg border border-rule bg-surface px-3.5 py-3">
      <dt className="kicker">{label}</dt>
      <dd className="mt-1.5 font-serif leading-tight text-ink tabular [overflow-wrap:anywhere]">
        <span className="text-xl font-medium">{number}</span>
        {unit && <span className="text-sm text-ink-3">{unit}</span>}
      </dd>
      {note && <dd className="mt-1 text-xs text-ink-3">{note}</dd>}
    </div>
  );
}

function Figures({ figures, currency }: { figures: ReportFigures; currency: string }) {
  return (
    <section aria-label="Headline figures">
      <p className="kicker mb-2">The investment case</p>
      <dl className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Figure label="NPV" value={money(figures.npv, currency)} note="three years" />
        <Figure label="IRR" value={irrText(figures.irr)} />
        <Figure label="Payback" value={paybackText(figures.payback_months)} />
        <Figure label="Break-even" value={breakEvenText(figures.break_even_customers)} />
      </dl>
    </section>
  );
}

// The figures to see at a glance: a proposal's, calculated from its plan; a
// team report's, as the team wrote them.
function KeyFigures({ figures, proposal }: { figures: KeyFigure[]; proposal: boolean }) {
  return (
    <section aria-label="Key figures">
      <p className="mb-2 flex flex-wrap items-baseline gap-x-2">
        <span className="kicker">{proposal ? "The plan" : "Key figures"}</span>
        <span className="text-xs text-ink-3">{proposal ? "calculated from its financial plan" : "as the team gave them"}</span>
      </p>
      <dl className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {figures.map((figure) => (
          <Figure key={figure.label} label={figure.label} value={figure.value} />
        ))}
      </dl>
    </section>
  );
}

function Detail({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-ink-3">{term}</dt>
      <dd className="min-w-0 text-ink">{children}</dd>
    </>
  );
}

function Preview({
  report,
  open,
  now,
  onOpen,
  onDelete,
}: {
  report: ReportSummary;
  open: boolean;
  now: number;
  onOpen: () => void;
  onDelete: () => Promise<void>;
}) {
  const currency = report.currency ?? "USD";
  const team = Array.isArray(report.team) ? report.team : [];
  const keyFigures = Array.isArray(report.key_figures) ? report.key_figures : [];
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const keep = useRef<HTMLButtonElement>(null);

  // Asked to confirm, the safe answer has the focus: Enter keeps the report.
  useEffect(() => {
    if (confirming) keep.current?.focus();
  }, [confirming]);

  async function remove() {
    setDeleting(true);
    setProblem(null);
    try {
      await onDelete();
    } catch (error) {
      setProblem((error as Error).message);
      setDeleting(false);
    }
  }
  return (
    <article aria-label="The report highlighted" className="flex h-full flex-col">
      {/* The title bar: what the report is and what can be done with it, in view however far the rest scrolls. */}
      <header className="shrink-0 border-b border-rule bg-surface px-7 pt-4 pb-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <p className="kicker flex flex-wrap items-center gap-2">
            {kindOf(report)} · Version {report.version}
            {open && <Badge tone="primary">Open now</Badge>}
            {report.edited && <Badge>Edited</Badge>}
          </p>
          {!confirming && (
            <div className="ml-auto flex items-center gap-1">
              <button
                type="button"
                onClick={() => setConfirming(true)}
                className="inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium text-bad transition-colors hover:bg-bad-soft"
              >
                <TrashIcon />
                Delete
              </button>
              <Button variant="primary" onClick={onOpen} disabled={open} title={open ? undefined : "Or press Enter"}>
                {open ? "This report is open" : "Open this report"}
                {!open && <ArrowRightIcon className="size-3.5" />}
              </Button>
            </div>
          )}
        </div>
        <h3 className="mt-2 font-serif text-[1.5rem] leading-tight font-medium tracking-[-0.01em] text-ink">{name(report)}</h3>
        {report.project_name && <p className="mt-1 text-sm leading-relaxed text-ink-3">{report.title}</p>}
        {confirming && (
          <section aria-label="Delete this report?" className="mt-3 rounded-lg border border-bad/40 bg-bad-soft px-4 py-3.5">
            <p className="text-sm font-medium text-bad">Delete “{name(report)}”?</p>
            <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
              The report and its earlier versions go, with the team&apos;s saved work for this session, and cannot
              be brought back. Files the founder uploaded stay, for other reports that worked from them.
            </p>
            {problem && (
              <p role="alert" className="mt-2 text-[13px] text-bad">
                {problem}
              </p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <Button ref={keep} onClick={() => setConfirming(false)} disabled={deleting}>
                Keep it
              </Button>
              <Button variant="danger" onClick={remove} disabled={deleting}>
                <TrashIcon />
                {deleting ? "Deleting…" : "Delete the report"}
              </Button>
            </div>
          </section>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
        <section
          aria-label="The decision"
          className={`rounded-lg border-l-[3px] bg-surface px-4 py-3.5 ${
            report.verdict === "Go" ? "border-good" : report.verdict === "Not yet" ? "border-bad" : report.verdict ? "border-warn" : "border-rule-strong"
          }`}
        >
          <p className="flex items-center gap-2.5">
            <span className="kicker">Recommendation</span>
            {report.verdict ? <VerdictPill verdict={report.verdict} /> : <span className="text-xs text-ink-3">Not stated</span>}
          </p>
          {report.brief ? (
            <div className="mt-2.5 [&_.doc]:text-[15px] [&_.doc]:leading-relaxed [&_.doc_h4]:text-[13px] [&_.doc_h4]:text-ink-2">
              <Markdown compact labels={4} figures>
                {report.brief}
              </Markdown>
            </div>
          ) : (
            report.objective && <p className="mt-2 font-serif text-[15px] leading-relaxed text-ink-2">{report.objective}</p>
          )}
        </section>

        {report.figures && (
          <div className="mt-5">
            <Figures figures={report.figures} currency={currency} />
          </div>
        )}
        {keyFigures.length > 0 && (
          <div className="mt-5">
            <KeyFigures figures={keyFigures} proposal={report.has_proposal} />
          </div>
        )}

        {((report.checks ?? 0) > 0 || report.outdated) && (
          <div className="mt-4 space-y-2">
            {(report.checks ?? 0) > 0 && (
              <Notice tone="warn">
                {report.checks === 1 ? "One of the proposal's figures disagrees" : `${report.checks} of the proposal's figures disagree`}{" "}
                with the others; its chapters say where.
              </Notice>
            )}
            {report.outdated && (
              <Notice tone="warn">A later evaluation in this session has newer results, which this report does not include.</Notice>
            )}
          </div>
        )}

        <div className="mt-6 border-t border-rule pt-5">
          <YourChoices sessionId={report.session_id} version={report.version} />
        </div>

        <div className="mt-6 border-t border-rule pt-5">
          <Versions sessionId={report.session_id} version={report.version} />
        </div>

        <section aria-label="About this report" className="mt-6 border-t border-rule pt-5">
          <dl className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-sm">
            {report.brief && report.objective && <Detail term="Objective">{report.objective}</Detail>}
            {team.length > 0 && (
              <Detail term="The team">
                <span className="flex flex-wrap gap-x-3 gap-y-1.5">
                  {team.map((member) => (
                    <span key={member} className="inline-flex items-center gap-1.5">
                      <AgentAvatar agent={specialistAgent(member)} size="xs" />
                      {AGENTS[specialistAgent(member)].short}
                    </span>
                  ))}
                </span>
              </Detail>
            )}
            <Detail term="Prepared by">{report.prepared_by ?? "AI Startup Co-Founder Team"}</Detail>
            <Detail term="Currency">
              {CURRENCIES[currency]?.name ?? currency} ({currency})
            </Detail>
            {typeof report.sections === "number" && (
              <Detail term="Contents">
                {report.sections} section{report.sections === 1 ? "" : "s"}
                {report.has_proposal ? ", and the proposal's six chapters" : ""}
              </Detail>
            )}
            {typeof report.documents === "number" && (
              <Detail term="Worked from">
                {report.documents ? `${report.documents} of the founder's document${report.documents === 1 ? "" : "s"}` : "The brief alone"}
              </Detail>
            )}
            <Detail term="Updated">
              <span className="tabular">{stamp(report.updated_at, true)}</span>
              <span className="text-ink-3"> · {ago(report.updated_at, now)}</span>
            </Detail>
            <Detail term="Session">
              <span className="font-mono text-[13px] text-ink-2">{report.session_id}</span>
            </Detail>
          </dl>
        </section>
      </div>
    </article>
  );
}

// ---- The pop-up ----

const WIDE = "(min-width: 64rem)";

function subscribeWide(change: () => void) {
  const query = typeof window.matchMedia === "function" ? window.matchMedia(WIDE) : null;
  query?.addEventListener("change", change);
  return () => query?.removeEventListener("change", change);
}

// Room for the preview beside the list: a large screen.
function useWide(): boolean {
  return useSyncExternalStore(
    subscribeWide,
    () => typeof window.matchMedia !== "function" || window.matchMedia(WIDE).matches,
    () => true,
  );
}

function matches(report: ReportSummary, words: string[]): boolean {
  const text = [report.title, report.project_name, report.objective, report.verdict, report.session_id, kindOf(report)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return words.every((word) => text.includes(word));
}

function Browser({
  reports,
  openId,
  onOpen,
  onDelete,
}: {
  reports: ReportSummary[];
  openId: string;
  onOpen: (sessionId: string) => void;
  onDelete: (sessionId: string) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<Kind>("all");
  const [sort, setSort] = useState<Sort>("newest");
  const [highlighted, setHighlighted] = useState(openId);
  // The time the pop-up opened, for "2 h ago".
  const [now] = useState(() => Date.now());
  const wide = useWide();
  const list = useId();
  const search = useRef<HTMLInputElement>(null);

  // After the dialog has opened, which first puts the focus on its own button.
  useEffect(() => {
    search.current?.focus();
  }, []);

  const counts: Record<Kind, number> = {
    all: reports.length,
    proposal: reports.filter((report) => report.has_proposal).length,
    team: reports.filter((report) => !report.has_proposal).length,
  };
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const visible = reports
    .filter((report) => kind === "all" || (kind === "proposal") === report.has_proposal)
    .filter((report) => matches(report, words))
    .sort((a, b) =>
      sort === "title"
        ? name(a).localeCompare(name(b))
        : (sort === "newest" ? -1 : 1) * (new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime()),
    );
  const active = visible.find((report) => report.session_id === highlighted) ?? visible[0];
  const optionId = (report: ReportSummary) => `${list}-${report.session_id}`;

  function move(step: number) {
    if (!visible.length) return;
    const at = active ? visible.indexOf(active) : -1;
    const next = visible[Math.min(visible.length - 1, Math.max(0, at + step))];
    setHighlighted(next.session_id);
    document.getElementById(optionId(next))?.scrollIntoView?.({ block: "nearest" });
  }

  function keys(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") move(1);
    else if (event.key === "ArrowUp") move(-1);
    else if (event.key === "Enter" && active) onOpen(active.session_id);
    else return;
    event.preventDefault();
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-rule px-5 py-3.5">
        <div className="relative min-w-[14rem] flex-1">
          <Voice label="the search">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
            <input
              type="search"
              role="combobox"
              aria-label="Search the reports"
              aria-controls={list}
              aria-expanded="true"
              aria-activedescendant={active ? optionId(active) : undefined}
              ref={search}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={keys}
              placeholder="Search by name, decision, verdict or session"
              className={`${inputClass} pl-9`}
            />
          </Voice>
        </div>
        <div role="group" aria-label="Show" className="flex rounded-md border border-rule-strong bg-sunken p-0.5">
          {KINDS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={kind === value}
              onClick={() => setKind(value)}
              className={`rounded-[5px] px-2.5 py-1.5 text-[13px] whitespace-nowrap transition-colors ${
                kind === value ? "bg-surface font-medium text-ink shadow-[0_1px_2px_rgb(0_0_0/0.08)]" : "text-ink-2 hover:text-ink"
              }`}
            >
              {label} <span className="text-ink-3 tabular">{counts[value]}</span>
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-[13px] text-ink-2">
          Sort
          <span className="w-36">
            <Select value={sort} onChange={(event) => setSort(event.target.value as Sort)} className="py-1.5">
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="title">By name</option>
            </Select>
          </span>
        </label>
      </div>

      <div className="min-h-0 flex-1 lg:grid lg:grid-cols-[minmax(0,27rem)_minmax(0,1fr)]">
        <div className="h-full overflow-y-auto px-3 py-3 lg:border-r lg:border-rule">
          <p aria-live="polite" className="px-1.5 pb-2 text-xs text-ink-3">
            {visible.length === reports.length
              ? `${reports.length} report${reports.length === 1 ? "" : "s"}`
              : `${visible.length} of ${reports.length} reports`}
          </p>
          {visible.length ? (
            <ul id={list} role="listbox" aria-label="Reports" className="space-y-1.5">
              {visible.map((report) => (
                <Row
                  key={report.session_id}
                  id={optionId(report)}
                  report={report}
                  active={report === active}
                  open={report.session_id === openId}
                  onPick={() => (wide ? setHighlighted(report.session_id) : onOpen(report.session_id))}
                  onOpen={() => onOpen(report.session_id)}
                />
              ))}
            </ul>
          ) : (
            <div id={list} role="listbox" aria-label="Reports" className="px-1.5 py-10 text-center">
              <p className="text-sm text-ink-2">No report matches{query ? ` “${query}”` : " this filter"}.</p>
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setKind("all");
                }}
                className="mt-2 text-sm font-medium text-ink underline underline-offset-4"
              >
                Show them all
              </button>
            </div>
          )}
        </div>
        {active && (
          <div className="hidden h-full min-h-0 bg-sunken/40 lg:block">
            <Preview
              // A preview of its own for each report, so a half-made deletion does not carry over.
              key={active.session_id}
              report={active}
              open={active.session_id === openId}
              now={now}
              onOpen={() => onOpen(active.session_id)}
              onDelete={() => onDelete(active.session_id)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function ReportPicker({
  reports,
  openId,
  onOpen,
  onDelete,
  onBrowse,
}: {
  reports: ReportSummary[];
  openId: string;
  onOpen: (sessionId: string) => void;
  // Deletes a report for good; throws, with why, if it could not.
  onDelete: (sessionId: string) => Promise<void>;
  // The pop-up opens: the time to load the list afresh.
  onBrowse?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const current = reports.find((report) => report.session_id === openId);
  if (!current) return null;

  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-label={`Report: ${name(current)}. Choose another of ${reports.length}.`}
        onClick={() => {
          setOpen(true);
          onBrowse?.();
        }}
        className="group flex w-full items-center gap-3 rounded-lg border border-rule-strong bg-surface px-3.5 py-2.5 text-left shadow-[0_1px_2px_rgb(0_0_0/0.04)] transition-colors hover:border-ink-3 sm:w-[24rem]"
      >
        <KindMark proposal={current.has_proposal} />
        <span className="min-w-0 flex-1">
          <span className="kicker flex items-center gap-2">
            Report · {reports.length} in all
          </span>
          <span className="mt-0.5 block truncate text-sm font-medium text-ink">{name(current)}</span>
          <span className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-3">
            <span className="truncate">
              {shortKind(current)} · {day(current.updated_at)}
            </span>
            {current.verdict && (
              <>
                <span aria-hidden>·</span>
                <span aria-hidden className={`size-1.5 shrink-0 rounded-full ${VERDICT_DOT[current.verdict]}`} />
                <span className="shrink-0">{current.verdict}</span>
              </>
            )}
          </span>
        </span>
        <span className="shrink-0 rounded-md border border-rule px-2 py-1 text-xs font-medium text-ink-2 transition-colors group-hover:border-rule-strong group-hover:text-ink">
          Browse
        </span>
      </button>
      <Dialog
        open={open}
        title="Reports"
        description="Every session's report: choose one to open."
        onClose={() => setOpen(false)}
      >
        <Browser
          reports={reports}
          openId={openId}
          onOpen={(sessionId) => {
            setOpen(false);
            if (sessionId !== openId) onOpen(sessionId);
          }}
          onDelete={onDelete}
        />
      </Dialog>
    </>
  );
}

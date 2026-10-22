"use client";

// The document studio, on a page of its own. On the right, the document in the
// browser's own PDF viewer: as saved, as a change would leave it, or as an
// earlier version was. On the left, the tools: ask the team to revise the
// proposal; the document's settings (the currency and the units, converted by
// code; who it is from; the sections left out); find and replace, or redact;
// and the history. Every change comes back as a draft to accept or discard.
// The tools fold into a strip of their icons, which this browser remembers,
// leaving the PDF the page; a draft or an earlier version always shows them.

import { useEffect, useRef, useState } from "react";

import { GuardrailNotice } from "@/components/guardrail-notice";
import { DraftReview } from "@/components/reports/draft-review";
import { AgentAvatar, AgentStack } from "@/components/ui/agent";
import { Button, buttonClass } from "@/components/ui/button";
import { inputClass, Label, Select } from "@/components/ui/field";
import { ClockIcon, DownloadIcon, PencilIcon, SearchIcon, SidebarIcon, SlidersIcon } from "@/components/ui/icons";
import { Notice, type Tone } from "@/components/ui/notice";
import { Progress } from "@/components/ui/progress";
import {
  ApiError,
  contentOf,
  type Draft,
  type DraftChange,
  getRates,
  getVersion,
  type GuardrailFlag,
  listVersions,
  makeDraft,
  type PartKey,
  type Rates,
  type Reasoning,
  type Report,
  reportPdf,
  restoreVersion,
  reviseProposal,
  type VersionSummary,
} from "@/lib/api";
import { PART_AGENT, TEAM } from "@/lib/agents";
import { CURRENCIES, PART_AGENTS, PART_TITLES } from "@/lib/proposal";
import { proposalWait } from "@/lib/team";

type Message = { tone: Tone; text: string };
export type Tool = "revise" | "settings" | "text" | "history";
// What the PDF on the right shows.
type Shown =
  | { kind: "saved" }
  | { kind: "draft"; draft: Draft; failed?: string[]; flags?: GuardrailFlag[] }
  | { kind: "version"; report: Report };
type Pdf = { key: string; url: string } | { key: string; error: string };

const PARTS = Object.keys(PART_TITLES) as PartKey[];
const TOOLS: [Tool, string, (props: { className?: string }) => React.ReactNode][] = [
  ["revise", "Revise", PencilIcon],
  ["settings", "Settings", SlidersIcon],
  ["text", "Text", SearchIcon],
  ["history", "History", ClockIcon],
];
const STALE = "The report changed elsewhere, so it has been reloaded. Make the change again.";

// Whether the tools are folded away, remembered in this browser.
const FOLDED_KEY = "cofounder-studio-tools";

function storedFolded(): boolean {
  try {
    return window.localStorage.getItem(FOLDED_KEY) === "folded";
  } catch {
    return false;
  }
}

// An instruction that asks for a conversion, which code does exactly.
const CONVERSION = /\b(currenc|euros?\b|eur\b|pounds?\b|gbp|rupees?|inr\b|yen\b|dollars?\b|usd\b|metric|imperial|kilomet|miles?\b|kilograms?)|[€£₹¥$]/i;
const ASKS_TO_CONVERT = /\b(convert|change|switch|turn|express|show|into|to)\b/i;

function pdfKey(shown: Shown, report: Report): string {
  if (shown.kind === "draft") return `draft-${shown.draft.base_version}-${shown.draft.summary}-${shown.draft.changes.length}`;
  if (shown.kind === "version") return `version-${shown.report.version}`;
  return `saved-${report.version}`;
}

// A day as "21 Oct 2026".
function readableDay(day: string): string {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

function ago(when: string): string {
  const minutes = Math.round((Date.now() - new Date(when).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(when).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function PdfPanel({
  report,
  reasoning,
  focusPrompt = false,
  initialTool = "revise",
  initialDraft = null,
  initialFlags = [],
  onChanged,
}: {
  report: Report;
  reasoning: Reasoning | null;
  focusPrompt?: boolean;
  initialTool?: Tool;
  // A change made on the page (a passage revised or removed), to review here.
  initialDraft?: Draft | null;
  // Text in the request that tried to instruct the agents.
  initialFlags?: GuardrailFlag[];
  // Called with the saved report, or with nothing when it changed elsewhere.
  onChanged: (report: Report | null) => void;
}) {
  const [tool, setTool] = useState<Tool>(report.proposal ? initialTool : initialTool === "revise" ? "settings" : initialTool);
  const [shown, setShown] = useState<Shown>(
    initialDraft ? { kind: "draft", draft: initialDraft, flags: initialFlags } : { kind: "saved" },
  );
  const [pdf, setPdf] = useState<Pdf | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [foldTools, setFoldTools] = useState(storedFolded);
  const key = pdfKey(shown, report);
  // A draft to accept, or a version to restore, always shows the tools.
  const folded = foldTools && shown.kind === "saved";

  function fold(next: boolean) {
    setFoldTools(next);
    try {
      if (next) window.localStorage.setItem(FOLDED_KEY, "folded");
      else window.localStorage.removeItem(FOLDED_KEY);
    } catch {
      // A browser that keeps nothing still folds them, for this page.
    }
  }

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    const content = shown.kind === "draft" ? contentOf(shown.draft.report) : shown.kind === "version" ? contentOf(shown.report) : undefined;
    reportPdf(report.session_id, content)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setPdf({ key, url });
      })
      .catch((error: Error) => {
        if (!cancelled) setPdf({ key, error: error.message });
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
    // The key says what is shown; `shown` itself is new on each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report.session_id, key]);

  function failed(error: unknown) {
    if (error instanceof ApiError && error.status === 409) {
      setMessage({ tone: "warn", text: STALE });
      onChanged(null);
    } else {
      setMessage({ tone: "bad", text: (error as Error).message });
    }
  }

  // A change made by code, as a draft to review.
  async function draft(change: DraftChange, doing: string) {
    setMessage(null);
    setBusy(doing);
    try {
      setShown({ kind: "draft", draft: await makeDraft(report.session_id, report.version, change) });
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) setMessage({ tone: "warn", text: error.message.replace(/^The backend returned 422: /, "") });
      else failed(error);
    } finally {
      setBusy(null);
    }
  }

  const current = pdf?.key === key ? pdf : null;
  const kind = report.proposal ? "investment-proposal" : "launch-report";
  const fileName = `${kind}-${report.session_id.slice(0, 8)}.pdf`;
  const iconButton = "flex rounded-md p-2 text-ink-3 transition-colors hover:bg-sunken hover:text-ink";

  return (
    <div
      className={`grid h-full min-h-0 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] lg:grid-rows-1 ${
        folded ? "lg:grid-cols-[3.5rem_minmax(0,1fr)]" : "lg:grid-cols-[25rem_minmax(0,1fr)]"
      }`}
    >
      {folded ? (
        // The tools folded: a strip of their icons, each opening the tools on it.
        <section
          aria-label="The tools, folded"
          className="flex items-center gap-1 border-b border-rule px-3 py-1.5 lg:flex-col lg:border-r lg:border-b-0 lg:px-0 lg:py-3"
        >
          <button type="button" onClick={() => fold(false)} title="Show the tools" className={iconButton}>
            <SidebarIcon />
            <span className="sr-only">Show the tools</span>
          </button>
          <span aria-hidden className="mx-1 h-5 w-px bg-rule lg:mx-0 lg:my-1 lg:h-px lg:w-5" />
          {TOOLS.map(([name, label, Icon]) => (
            <button
              key={name}
              type="button"
              title={label}
              onClick={() => {
                setTool(name);
                setMessage(null);
                fold(false);
              }}
              className={iconButton}
            >
              <Icon />
              <span className="sr-only">Open the {label} tool</span>
            </button>
          ))}
          {current && "url" in current && (
            <a href={current.url} download={fileName} title="Download PDF" className={`${iconButton} ml-auto lg:mt-auto lg:ml-0`}>
              <DownloadIcon />
              <span className="sr-only">Download PDF</span>
            </a>
          )}
        </section>
      ) : (
        <div className="flex min-h-0 flex-col gap-5 overflow-y-auto border-b border-rule p-5 lg:border-r lg:border-b-0">
          {shown.kind === "draft" ? (
            <DraftReview
              sessionId={report.session_id}
              draft={shown.draft}
              before={report}
              notes={
                <>
                  {shown.failed && shown.failed.length > 0 && (
                    <Notice tone="warn">Could not revise {shown.failed.join(", ")}; they keep their text.</Notice>
                  )}
                  <GuardrailNotice flags={shown.flags ?? []} />
                </>
              }
              onAccepted={(saved) => {
                setShown({ kind: "saved" });
                setMessage({ tone: "good", text: `Saved as version ${saved.version}.` });
                onChanged(saved);
              }}
              onDiscard={() => {
                setShown({ kind: "saved" });
                setMessage({ tone: "info", text: "Discarded; nothing was changed." });
              }}
              onStale={() => {
                setShown({ kind: "saved" });
                setMessage({ tone: "warn", text: STALE });
                onChanged(null);
              }}
            />
          ) : shown.kind === "version" ? (
            <section aria-label="An earlier version" className="space-y-4">
              <Notice tone="info">
                Showing version {shown.report.version} as it was{shown.report.change ? `: ${shown.report.change}.` : "."}
              </Notice>
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  className="flex-1"
                  disabled={Boolean(busy)}
                  onClick={async () => {
                    setBusy("restore");
                    try {
                      const saved = await restoreVersion(report.session_id, report.version, shown.report.version);
                      setShown({ kind: "saved" });
                      setMessage({ tone: "good", text: `Restored version ${shown.report.version} as version ${saved.version}; the one it replaced is kept.` });
                      onChanged(saved);
                    } catch (error) {
                      setShown({ kind: "saved" });
                      failed(error);
                    } finally {
                      setBusy(null);
                    }
                  }}
                >
                  Restore this version
                </Button>
                <Button onClick={() => setShown({ kind: "saved" })}>Back</Button>
              </div>
            </section>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <div role="tablist" aria-label="Tools" className="grid flex-1 grid-cols-4 gap-0.5 rounded-md border border-rule-strong bg-sunken p-0.5">
                  {TOOLS.map(([name, label]) => (
                    <button
                      key={name}
                      type="button"
                      role="tab"
                      aria-selected={tool === name}
                      onClick={() => {
                        setTool(name);
                        setMessage(null);
                      }}
                      className={`rounded-[5px] px-1.5 py-1.5 text-[12.5px] transition-colors ${
                        tool === name ? "bg-surface font-medium text-ink shadow-[0_1px_2px_rgb(0_0_0/0.08)]" : "text-ink-2 hover:text-ink"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <button type="button" onClick={() => fold(true)} title="Hide the tools" className={`${iconButton} -mr-1.5 shrink-0`}>
                  <SidebarIcon />
                  <span className="sr-only">Hide the tools</span>
                </button>
              </div>
              {tool === "revise" && (
                <ReviseTool
                  report={report}
                  reasoning={reasoning}
                  focus={focusPrompt}
                  busy={busy}
                  setBusy={setBusy}
                  onDraft={(result) => setShown({ kind: "draft", ...result })}
                  onFailed={failed}
                  onSettings={() => setTool("settings")}
                  setMessage={setMessage}
                />
              )}
              {tool === "settings" && <SettingsTool report={report} busy={busy} onDraft={draft} />}
              {tool === "text" && <TextTool busy={busy} onDraft={draft} />}
              {tool === "history" && (
                <HistoryTool
                  report={report}
                  onLook={async (version) => {
                    try {
                      setShown({ kind: "version", report: await getVersion(report.session_id, version) });
                    } catch (error) {
                      failed(error);
                    }
                  }}
                />
              )}
            </>
          )}
          {busy && busy !== "revise" && busy !== "restore" && <p className="text-sm text-ink-3">{busy}…</p>}
          {message && <Notice tone={message.tone}>{message.text}</Notice>}
          {shown.kind === "saved" && current && "url" in current && (
            <a href={current.url} download={fileName} className={buttonClass("secondary", "md", "mt-auto")}>
              <DownloadIcon />
              Download PDF
            </a>
          )}
        </div>
      )}
      <div className="flex min-h-[60dvh] flex-col bg-sunken lg:min-h-0">
        {shown.kind !== "saved" && (
          <p className={`px-4 py-2 text-xs font-medium ${shown.kind === "draft" ? "bg-warn-soft text-warn" : "bg-primary-soft text-ink"}`}>
            {shown.kind === "draft" ? "Preview of the change: not saved" : `Version ${shown.report.version}, as it was`}
          </p>
        )}
        {!current && <p className="m-auto text-sm text-ink-3">Drawing the PDF…</p>}
        {current && "error" in current && (
          <Notice tone="bad" className="m-auto max-w-md">
            The PDF could not be made. {current.error}
          </Notice>
        )}
        {current && "url" in current && (
          <iframe src={current.url} title="The report as a PDF" className="min-h-[60dvh] w-full flex-1 border-0 lg:min-h-0" />
        )}
      </div>
    </div>
  );
}

function ReviseTool({
  report,
  reasoning,
  focus,
  busy,
  setBusy,
  onDraft,
  onFailed,
  onSettings,
  setMessage,
}: {
  report: Report;
  reasoning: Reasoning | null;
  focus: boolean;
  busy: string | null;
  setBusy: (busy: string | null) => void;
  onDraft: (result: { draft: Draft; failed: string[]; flags: GuardrailFlag[] }) => void;
  onFailed: (error: unknown) => void;
  onSettings: () => void;
  setMessage: (message: Message | null) => void;
}) {
  const [part, setPart] = useState<PartKey | "whole">("whole");
  const [instruction, setInstruction] = useState("");
  const prompt = useRef<HTMLTextAreaElement>(null);
  const converting = CONVERSION.test(instruction) && ASKS_TO_CONVERT.test(instruction);

  useEffect(() => {
    if (focus) prompt.current?.focus();
  }, [focus]);

  if (!report.proposal) {
    return (
      <p className="text-sm leading-relaxed text-ink-2">
        This is the team&apos;s report. Write the investment proposal to ask the team for changes here; the settings,
        the text tools and the history work on the report already.
      </p>
    );
  }

  async function revise(event: React.FormEvent) {
    event.preventDefault();
    if (!instruction.trim()) {
      setMessage({ tone: "warn", text: "Say what to change." });
      return;
    }
    setMessage(null);
    setBusy("revise");
    try {
      const result = await reviseProposal(report.session_id, report.version, instruction.trim(), part === "whole" ? null : part, reasoning);
      setInstruction("");
      onDraft({ draft: result.draft, failed: result.failed, flags: result.guardrails ?? [] });
    } catch (error) {
      onFailed(error);
    } finally {
      setBusy(null);
    }
  }

  return (
    <form onSubmit={revise} aria-label="Ask the team to revise the proposal" className="space-y-5">
      <fieldset>
        <legend className="kicker">Ask the team to revise</legend>
        <div className="mt-3 space-y-0.5">
          {(["whole", ...PARTS] as const).map((key) => (
            <label
              key={key}
              className={`flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-1.5 text-sm ${part === key ? "bg-sunken" : "hover:bg-sunken/60"}`}
            >
              <input
                type="radio"
                name="revise-part"
                value={key}
                checked={part === key}
                onChange={() => setPart(key)}
                className="mt-1 accent-[var(--primary)]"
              />
              {key === "whole" ? <AgentStack agents={TEAM} /> : <AgentAvatar agent={PART_AGENT[key]} size="sm" />}
              <span>
                <span className="block text-ink">{key === "whole" ? "The whole proposal" : PART_TITLES[key]}</span>
                <span className="block text-xs text-ink-3">{key === "whole" ? "Every agent revises its part" : PART_AGENTS[key]}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <div>
        <Label htmlFor="revise-instruction">What to change</Label>
        <textarea
          ref={prompt}
          id="revise-instruction"
          rows={4}
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          placeholder="Make the year-one figures more conservative, and add a referral channel."
          className={`${inputClass} leading-relaxed`}
        />
      </div>
      {converting && (
        <Notice tone="info">
          A conversion of the currency or the units is exact in{" "}
          <button type="button" onClick={onSettings} className="font-medium underline underline-offset-2">
            Settings
          </button>
          : code converts every figure and every amount in the text, which the team cannot promise.
        </Notice>
      )}
      <Button type="submit" variant="primary" disabled={Boolean(busy)} className="w-full">
        Revise
      </Button>
      <p className="text-xs leading-relaxed text-ink-3">
        You see the change before it is saved. To change one paragraph only, use its Revise button on the page.
      </p>
      {busy === "revise" && (
        <Progress
          title={part === "whole" ? "Every agent is revising its part." : `The ${PART_AGENTS[part]} is revising its part.`}
          wait={proposalWait(reasoning)}
          stages={[
            part === "whole" ? "Each agent applies your instruction to its part" : `The ${PART_TITLES[part]} part is rewritten`,
            "The parts built on it are brought into line",
            "The change is shown for you to accept",
          ]}
        />
      )}
    </form>
  );
}

function SettingsTool({
  report,
  busy,
  onDraft,
}: {
  report: Report;
  busy: string | null;
  onDraft: (change: DraftChange, doing: string) => void;
}) {
  const { settings } = report;
  const others = Object.keys(CURRENCIES).filter((code) => code !== settings.currency);
  const [to, setTo] = useState(others[0] ?? "EUR");
  const [relabel, setRelabel] = useState(false);
  const [preparedBy, setPreparedBy] = useState(settings.prepared_by);
  const [hidden, setHidden] = useState<string[]>(settings.hidden);
  // Today's rates from the report's currency fill the rate in; a rate the
  // founder types for a currency stays until they change it.
  const [today, setToday] = useState<Rates | null>(null);
  const [noRates, setNoRates] = useState<string | null>(null);
  const [typed, setTyped] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    getRates(settings.currency)
      .then((answer) => {
        if (cancelled) return;
        setToday(answer);
        setNoRates(null);
      })
      .catch((error: Error) => {
        if (!cancelled) setNoRates(error.message);
      });
    return () => {
      cancelled = true;
    };
  }, [settings.currency]);

  const fetched = today?.base === settings.currency ? today.rates[to] : undefined;
  const rate = typed[to] ?? (fetched === undefined ? "" : String(fetched));
  const value = Number(rate);
  const pegged = today && [to, settings.currency].some((code) => today.pegged.includes(code));

  return (
    <div className="space-y-7">
      <section aria-labelledby="currency-heading" className="space-y-3">
        <h3 id="currency-heading" className="kicker">
          Currency
        </h3>
        <p className="text-sm text-ink-2">
          Every amount is in <span className="font-medium text-ink">{CURRENCIES[settings.currency]?.name ?? settings.currency}</span> ({settings.currency}).
          Converting changes every figure and every amount in the text, in code.
        </p>
        <div>
          <Label htmlFor="currency-to">Change it to</Label>
          <Select id="currency-to" value={to} onChange={(event) => setTo(event.target.value)}>
            {others.map((code) => (
              <option key={code} value={code}>
                {CURRENCIES[code].name} ({code})
              </option>
            ))}
          </Select>
        </div>
        <label className="flex cursor-pointer items-start gap-2.5 text-sm">
          <input type="checkbox" checked={relabel} onChange={(event) => setRelabel(event.target.checked)} className="mt-1 accent-[var(--primary)]" />
          <span>
            The amounts are already in {to}
            <span className="block text-xs text-ink-3">Only show them in {to}, without converting.</span>
          </span>
        </label>
        {!relabel && (
          <div>
            <Label htmlFor="currency-rate" hint="your bank's, if it differs">
              1 {settings.currency} =
            </Label>
            <div className="flex items-center gap-2">
              <input
                id="currency-rate"
                inputMode="decimal"
                value={rate}
                onChange={(event) => setTyped((current) => ({ ...current, [to]: event.target.value.replace(",", ".") }))}
                aria-describedby="currency-rate-source"
                className={`${inputClass} tabular`}
              />
              <span className="text-sm text-ink-2">{to}</span>
            </div>
            <p id="currency-rate-source" className="mt-1.5 text-xs leading-relaxed text-ink-3">
              {fetched !== undefined && typed[to] === undefined && (
                <>
                  Today&apos;s rate, from the {today!.source} of {readableDay(today!.date)}
                  {pegged && ", with the dirham and the riyal at their pegs to the US dollar"}.
                </>
              )}
              {fetched !== undefined && typed[to] !== undefined && (
                <>
                  Your own rate; the ECB&apos;s for {readableDay(today!.date)} is {fetched}.{" "}
                  <button
                    type="button"
                    onClick={() =>
                      setTyped((current) => {
                        const kept = { ...current };
                        delete kept[to];
                        return kept;
                      })
                    }
                    className="font-medium text-ink-2 underline underline-offset-2 hover:text-ink"
                  >
                    Use it
                  </button>
                </>
              )}
              {fetched === undefined && noRates && <>Today&apos;s rate could not be fetched ({noRates}). Enter it from your bank or the ECB.</>}
              {fetched === undefined && !noRates && (today ? "No rate for this currency today; enter it from your bank." : "Fetching today's rate…")}
            </p>
          </div>
        )}
        <Button
          disabled={Boolean(busy) || (!relabel && !(value > 0))}
          onClick={() => onDraft({ kind: "currency", to, rate: relabel ? 1 : value, relabel }, "Converting")}
        >
          {relabel ? `Show the amounts in ${to}` : `Convert to ${to}`}
        </Button>
      </section>

      <section aria-labelledby="units-heading" className="space-y-3">
        <h3 id="units-heading" className="kicker">
          Units
        </h3>
        <p className="text-sm text-ink-2">
          {settings.units ? `Measurements were last converted to ${settings.units}.` : "Measurements are as the team wrote them."} Areas,
          distances, weights, volumes and temperatures convert in code.
        </p>
        <div className="flex gap-2">
          {(["metric", "imperial"] as const).map((system) => (
            <Button key={system} disabled={Boolean(busy)} onClick={() => onDraft({ kind: "units", to: system }, "Converting")}>
              To {system}
            </Button>
          ))}
        </div>
      </section>

      <section aria-labelledby="document-heading" className="space-y-3">
        <h3 id="document-heading" className="kicker">
          The document
        </h3>
        <div>
          <Label htmlFor="prepared-by">Prepared by</Label>
          <input id="prepared-by" value={preparedBy} onChange={(event) => setPreparedBy(event.target.value)} className={inputClass} />
        </div>
        <fieldset>
          <legend className="mb-1.5 text-[13px] font-medium text-ink">The team&apos;s report in the document</legend>
          <div className="space-y-1">
            {report.sections.map((section) => (
              <label key={section.key} className="flex cursor-pointer items-center gap-2.5 text-sm">
                <input
                  type="checkbox"
                  checked={!hidden.includes(section.key)}
                  onChange={(event) =>
                    setHidden((current) => (event.target.checked ? current.filter((key) => key !== section.key) : [...current, section.key]))
                  }
                  className="accent-[var(--primary)]"
                />
                {section.title}
              </label>
            ))}
          </div>
        </fieldset>
        <Button
          disabled={Boolean(busy) || !preparedBy.trim()}
          onClick={() => onDraft({ kind: "settings", prepared_by: preparedBy.trim(), hidden }, "Preparing")}
        >
          Preview these settings
        </Button>
      </section>
    </div>
  );
}

function TextTool({ busy, onDraft }: { busy: string | null; onDraft: (change: DraftChange, doing: string) => void }) {
  const [find, setFind] = useState("");
  const [by, setBy] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [wholeWords, setWholeWords] = useState(true);
  const [terms, setTerms] = useState("");
  const list = terms.split("\n").map((term) => term.trim()).filter(Boolean);

  return (
    <div className="space-y-7">
      <section aria-labelledby="replace-heading" className="space-y-3">
        <h3 id="replace-heading" className="kicker">
          Find and replace
        </h3>
        <p className="text-sm text-ink-2">Everywhere: the title, the team&apos;s report and the proposal. A new product name, say.</p>
        <div>
          <Label htmlFor="replace-find">Find</Label>
          <input id="replace-find" value={find} onChange={(event) => setFind(event.target.value)} className={inputClass} />
        </div>
        <div>
          <Label htmlFor="replace-by">Replace with</Label>
          <input id="replace-by" value={by} onChange={(event) => setBy(event.target.value)} className={inputClass} />
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
          <label className="flex cursor-pointer items-center gap-2">
            <input type="checkbox" checked={matchCase} onChange={(event) => setMatchCase(event.target.checked)} className="accent-[var(--primary)]" />
            Match case
          </label>
          <label className="flex cursor-pointer items-center gap-2">
            <input type="checkbox" checked={wholeWords} onChange={(event) => setWholeWords(event.target.checked)} className="accent-[var(--primary)]" />
            Whole words
          </label>
        </div>
        <Button
          disabled={Boolean(busy) || !find.trim()}
          onClick={() => onDraft({ kind: "replace", find: find.trim(), by, match_case: matchCase, whole_words: wholeWords }, "Finding")}
        >
          Preview the replacement
        </Button>
      </section>

      <section aria-labelledby="redact-heading" className="space-y-3">
        <h3 id="redact-heading" className="kicker">
          Redact
        </h3>
        <p className="text-sm text-ink-2">Black out names, figures or anything else wherever they appear, the PDF included.</p>
        <div>
          <Label htmlFor="redact-terms" hint="one a line">
            What to black out
          </Label>
          <textarea
            id="redact-terms"
            rows={3}
            value={terms}
            onChange={(event) => setTerms(event.target.value)}
            placeholder={"Dana Reyes\nAcme Health"}
            className={`${inputClass} leading-relaxed`}
          />
        </div>
        <Button disabled={Boolean(busy) || !list.length} onClick={() => onDraft({ kind: "redact", terms: list }, "Redacting")}>
          Preview the redaction
        </Button>
      </section>
    </div>
  );
}

function HistoryTool({ report, onLook }: { report: Report; onLook: (version: number) => void }) {
  const [versions, setVersions] = useState<VersionSummary[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listVersions(report.session_id)
      .then((found) => !cancelled && setVersions(found))
      .catch((error: Error) => !cancelled && setProblem(error.message));
    return () => {
      cancelled = true;
    };
  }, [report.session_id, report.version]);

  if (problem) return <Notice tone="bad">{problem}</Notice>;
  if (!versions) return <p className="text-sm text-ink-3">Loading the history…</p>;
  return (
    <section aria-labelledby="history-heading">
      <h3 id="history-heading" className="kicker">
        Versions, newest first
      </h3>
      <ol className="mt-3 divide-y divide-rule border-y border-rule">
        {versions.map((version) => (
          <li key={version.version} className="flex items-start gap-3 py-2.5 text-sm">
            <span className="mt-0.5 w-9 shrink-0 font-mono text-xs text-ink-3">v{version.version}</span>
            <span className="min-w-0 flex-1">
              <span className="block text-ink">{version.change ?? "Saved"}</span>
              <span className="block text-xs text-ink-3">{ago(version.updated_at)}</span>
            </span>
            {version.current ? (
              <span className="shrink-0 rounded bg-sunken px-1.5 py-0.5 text-xs text-ink-2">Current</span>
            ) : (
              <Button size="sm" onClick={() => onLook(version.version)}>
                Look
              </Button>
            )}
          </li>
        ))}
      </ol>
      <p className="mt-2 text-xs text-ink-3">The last 30 versions are kept. Restoring one keeps the current version too.</p>
    </section>
  );
}

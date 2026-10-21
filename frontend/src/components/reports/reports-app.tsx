"use client";

// The Reports page: each session's report, read like the document it is and
// edited in place. Until the agents write the investment proposal it is the
// team's report; after, a chapter per section of the proposal, numbered as the
// PDF is, each with its charts, the agent that wrote it and an Edit button.
// Each paragraph can be revised or removed on its own. "Open PDF" shows the
// document in the studio, beside its tools: the team's revisions, the
// settings (currency, units), find and replace, redaction and the history.
// Every change is shown as a draft before it is saved.

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { EditForm } from "@/components/reports/edit-form";
import { type PassageAction, PassageContext } from "@/components/reports/passages";
import { PdfPanel, type Tool } from "@/components/reports/pdf-panel";
import {
  ExecutiveSection,
  FinancialSection,
  KpiSection,
  MarketSection,
  RiskSection,
  TechnicalSection,
  type View,
} from "@/components/reports/proposal-view";
import { TeamReport } from "@/components/reports/team-report";
import { AgentName } from "@/components/ui/agent";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Label, Select } from "@/components/ui/field";
import { ArrowRightIcon, DocumentIcon, PencilIcon, RefreshIcon, UndoIcon } from "@/components/ui/icons";
import { Menu } from "@/components/ui/menu";
import { Notice, type Tone } from "@/components/ui/notice";
import { PageHeader, titleSize } from "@/components/ui/page-header";
import { Progress } from "@/components/ui/progress";
import { Tabs } from "@/components/ui/tabs";
import {
  ApiError,
  type Draft,
  getReport,
  type GuardrailFlag,
  listReports,
  makeDraft,
  type PartKey,
  type Proposal,
  type Report,
  type ReportSection,
  type ReportSummary,
  resetReport,
  reviseText,
  saveProposal,
  saveReport,
  writeProposal,
} from "@/lib/api";
import { useBackend } from "@/lib/backend";
import { agentClass, PART_AGENT } from "@/lib/agents";
import { CURRENCIES, CurrencyContext, PART_AGENTS, PART_TITLES } from "@/lib/proposal";
import { proposalWait } from "@/lib/team";

type Message = { tone: Tone; text: string };
// The studio pop-up: the tool it opens on, a draft to review, and whether the
// revise prompt takes the focus.
type Studio = { tool: Tool; draft: Draft | null; flags: GuardrailFlag[]; focus: boolean; opened: number };

const DESCRIPTION =
  "Each session's report. Read it, edit it, have the agents write it up as an investment proposal, and share the PDF.";
const CHANGED_ELSEWHERE = "The report changed elsewhere, so it has been reloaded. Make the change again.";

// The proposal's chapters: the part each edits, and the fields of it the form shows.
const CHAPTERS: {
  number: string;
  name: string;
  title: string;
  part: PartKey;
  only?: string[];
  View: (view: View) => React.ReactNode;
}[] = [
  {
    number: "1",
    name: "Executive summary",
    title: "Executive Summary",
    part: "executive",
    only: ["project_name", "verdict", "recommendation", "overview", "opportunity", "strategic_alignment", "financial_case"],
    View: ExecutiveSection,
  },
  { number: "2", name: "Market & marketing", title: "Market & Marketing Strategy", part: "market", View: MarketSection },
  {
    number: "3",
    name: "Technical & operations",
    title: "Technical & Operational Architecture",
    part: "technical",
    View: TechnicalSection,
  },
  { number: "4", name: "Financial plan", title: "Financial Plan & Projections", part: "financial", View: FinancialSection },
  { number: "5", name: "Risk & compliance", title: "Security, Compliance & Risk", part: "risk", View: RiskSection },
  { number: "6", name: "Success metrics", title: "Success Metrics (KPIs)", part: "executive", only: ["kpis"], View: KpiSection },
];

function when(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
}

function label(summary: ReportSummary): string {
  const title = summary.title.length > 70 ? `${summary.title.slice(0, 67)}...` : summary.title;
  return `${title} (${summary.has_proposal ? "investment proposal" : "team report"}, ${when(summary.updated_at)} UTC)`;
}

// The session to open first: the one in the address, else the one the
// Evaluate page is on, else the newest.
function preferred(ids: string[]): string | undefined {
  const fromAddress = new URLSearchParams(window.location.search).get("session");
  if (fromAddress && ids.includes(fromAddress)) return fromAddress;
  try {
    const saved = JSON.parse(window.sessionStorage.getItem("cofounder-session") ?? "{}");
    const current = saved.runs?.at(-1)?.result?.session_id;
    if (current && ids.includes(current)) return current;
  } catch {
    // An unreadable saved session is not a reason to fail.
  }
  return ids[0];
}

const neverChanges = () => () => {};

export function ReportsApp() {
  const inBrowser = useSyncExternalStore(neverChanges, () => true, () => false);
  return inBrowser ? <Reports /> : <PageHeader title="Reports" description={DESCRIPTION} />;
}

function Cover({ report }: { report: Report }) {
  const proposal = report.proposal;
  return (
    <header>
      <p className="kicker flex flex-wrap items-center gap-2">
        {proposal ? "Investment proposal" : "Team report"}
        {report.edited && <Badge tone="warn">Edited</Badge>}
      </p>
      {proposal ? (
        <>
          <h2 className="mt-2 max-w-4xl font-serif text-[2.6rem] leading-[1.08] font-medium tracking-[-0.02em]">
            {proposal.executive.project_name}
          </h2>
          <p className="mt-4 max-w-3xl font-serif text-[1.2rem] leading-snug text-ink-2">{report.objective}</p>
        </>
      ) : (
        <h2 className={`mt-2 max-w-3xl font-serif ${titleSize(report.objective)} leading-snug font-medium tracking-[-0.01em]`}>
          {report.objective}
        </h2>
      )}
      <dl className="mt-8 grid max-w-4xl grid-cols-2 gap-x-8 gap-y-4 border-t border-rule pt-4 text-sm sm:grid-cols-5">
        <div>
          <dt className="kicker">Prepared by</dt>
          <dd className="mt-1">{report.settings.prepared_by}</dd>
        </div>
        <div>
          <dt className="kicker">Currency</dt>
          <dd className="mt-1" title={CURRENCIES[report.settings.currency]?.name}>
            {report.settings.currency}
            {report.settings.units && <span className="text-ink-3"> · {report.settings.units}</span>}
          </dd>
        </div>
        <div>
          <dt className="kicker">Version</dt>
          <dd className="mt-1 tabular">Version {report.version}</dd>
        </div>
        <div>
          <dt className="kicker">Updated</dt>
          <dd className="mt-1">{when(report.updated_at)} UTC</dd>
        </div>
        <div>
          <dt className="kicker">Session</dt>
          <dd className="mt-1 font-mono text-[13px] text-ink-2" title={report.session_id}>
            {report.session_id.slice(0, 8)}
          </dd>
        </div>
      </dl>
    </header>
  );
}

// One chapter of the proposal: its title and source, and its view or the form that edits it.
function Chapter({
  number,
  title,
  part,
  only,
  value,
  onSave,
  children,
}: {
  number: string;
  title: string;
  part: PartKey;
  only?: string[];
  value: Record<string, unknown>;
  onSave: (edited: Record<string, unknown>) => Promise<string | null>;
  children: React.ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  return (
    <div>
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-rule pb-6">
        <div>
          <p className={`${agentClass(PART_AGENT[part])} kicker flex items-center gap-2`}>
            <span className="h-[3px] w-5 rounded-full bg-agent" />
            Chapter {number}
          </p>
          <h2 className="mt-1.5 font-serif text-[1.9rem] leading-tight font-medium tracking-[-0.01em]">{title}</h2>
          <p className="mt-3 text-sm text-ink-3">
            <AgentName agent={PART_AGENT[part]} size="sm">
              Written by the {PART_AGENTS[part]}
            </AgentName>
          </p>
        </div>
        {!editing && (
          <Button size="sm" onClick={() => setEditing(true)}>
            <PencilIcon className="size-3.5" />
            Edit
          </Button>
        )}
      </header>
      <div className="mt-10">
        {editing ? (
          <EditForm
            part={part}
            value={value}
            only={only}
            onCancel={() => setEditing(false)}
            onSave={async (edited) => {
              const failure = await onSave(edited);
              if (!failure) setEditing(false);
              return failure;
            }}
          />
        ) : (
          children
        )}
      </div>
    </div>
  );
}

function Reports() {
  const { reasoning } = useBackend();
  const [summaries, setSummaries] = useState<ReportSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [writing, setWriting] = useState(false);
  const [confirm, setConfirm] = useState<"rewrite" | "reset" | null>(null);
  const [studio, setStudio] = useState<Studio | null>(null);
  // A passage being revised by its writer, while the team works on it.
  const [revisingPassage, setRevisingPassage] = useState(false);
  const [currency, setCurrency] = useState<string | null>(null);

  function open(tool: Tool, draft: Draft | null = null, flags: GuardrailFlag[] = [], focus = false) {
    setStudio({ tool, draft, flags, focus, opened: Date.now() });
  }

  useEffect(() => {
    listReports()
      .then((list) => {
        setSummaries(list);
        setSelected(preferred(list.map((summary) => summary.session_id)) ?? null);
      })
      .catch((error: Error) => setProblem(error.message));
  }, []);

  const load = useCallback((sessionId: string) => {
    getReport(sessionId)
      .then((loaded) => {
        setReport(loaded);
        setProblem(null);
      })
      .catch((error: Error) => setProblem(error.message));
  }, []);

  useEffect(() => {
    if (selected) load(selected);
  }, [selected, load]);

  // A change the API refused because the report moved on: reload it and say so.
  function failed(error: unknown): string {
    if (error instanceof ApiError && error.status === 409 && report) {
      load(report.session_id);
      setMessage({ tone: "warn", text: CHANGED_ELSEWHERE });
      return CHANGED_ELSEWHERE;
    }
    return (error as Error).message;
  }

  async function write() {
    if (!report) return;
    setConfirm(null);
    setMessage(null);
    setWriting(true);
    try {
      const result = await writeProposal(report.session_id, report.version, reasoning, currency ?? report.settings.currency);
      setReport(result.report);
      setMessage({
        tone: "good",
        text: "The investment proposal is written. Open the PDF to see it as a document, and to ask the team for changes.",
      });
    } catch (error) {
      const text = failed(error);
      if (text !== CHANGED_ELSEWHERE) setMessage({ tone: "bad", text });
    } finally {
      setWriting(false);
    }
  }

  async function reset() {
    if (!report) return;
    setConfirm(null);
    try {
      setReport(await resetReport(report.session_id));
      setMessage({ tone: "good", text: "The report was rebuilt from the session's latest results." });
    } catch (error) {
      setMessage({ tone: "bad", text: (error as Error).message });
    }
  }

  // A paragraph revised by its writer, or removed: a draft, shown in the studio.
  async function passage(action: PassageAction): Promise<boolean> {
    if (!report) return false;
    setMessage(null);
    if (action.kind === "revise") setRevisingPassage(true);
    try {
      if (action.kind === "remove") {
        const draft = await makeDraft(report.session_id, report.version, { kind: "remove", path: action.path, passage: action.passage });
        open("revise", draft);
      } else {
        const result = await reviseText(report.session_id, report.version, action.path, action.instruction, action.passage, reasoning);
        open("revise", result.draft, result.guardrails ?? []);
      }
      return true;
    } catch (error) {
      const text = failed(error);
      if (text !== CHANGED_ELSEWHERE) setMessage({ tone: "bad", text });
      return false;
    } finally {
      setRevisingPassage(false);
    }
  }

  async function savePart(part: PartKey, edited: Record<string, unknown>): Promise<string | null> {
    if (!report?.proposal) return null;
    try {
      const proposal = { ...report.proposal, [part]: { ...report.proposal[part], ...edited } } as Proposal;
      setReport(await saveProposal(report.session_id, report.version, proposal));
      setMessage({ tone: "good", text: `Saved your changes to the ${PART_TITLES[part]} part.` });
      return null;
    } catch (error) {
      return failed(error);
    }
  }

  async function saveSections(sections: ReportSection[]): Promise<string | null> {
    if (!report) return null;
    try {
      setReport(await saveReport(report.session_id, report.version, sections));
      setMessage({ tone: "good", text: "Saved your changes to the team's report." });
      return null;
    } catch (error) {
      return failed(error);
    }
  }

  const picker = summaries && summaries.length > 0 && report && (
    <div className="w-full sm:w-[22rem]">
      <Label htmlFor="report">Report</Label>
      <Select
        id="report"
        value={selected ?? ""}
        onChange={(event) => {
          setSelected(event.target.value);
          setMessage(null);
          setStudio(null);
        }}
      >
        {summaries.map((summary) => (
          <option key={summary.session_id} value={summary.session_id}>
            {/* The open report's label follows its changes since the list was loaded. */}
            {label(
              summary.session_id === report.session_id
                ? { ...summary, has_proposal: Boolean(report.proposal), updated_at: report.updated_at }
                : summary,
            )}
          </option>
        ))}
      </Select>
    </div>
  );

  let body: React.ReactNode;
  if (problem && !report) {
    body = (
      <Notice tone="bad" className="mt-8">
        {problem}
      </Notice>
    );
  } else if (summaries && !summaries.length) {
    body = (
      <div className="mt-16 max-w-md">
        <h2 className="font-serif text-2xl font-medium">No reports yet</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">
          Each evaluation leaves a report here. Run one on the Evaluate page, and its report appears.
        </p>
        <ButtonLink href="/" variant="primary" className="mt-5">
          Evaluate an idea
          <ArrowRightIcon className="size-3.5" />
        </ButtonLink>
      </div>
    );
  } else if (!summaries || !report) {
    body = <p className="mt-10 text-sm text-ink-3">Loading the reports…</p>;
  } else {
    const view: View | null =
      report.proposal && report.investment
        ? { proposal: report.proposal, metrics: report.investment, checks: report.checks }
        : null;
    body = (
      <div className="mt-10">
        <Cover report={report} />

        <div className="mt-8 flex flex-wrap items-center gap-2">
          <Button variant={view ? "primary" : "secondary"} onClick={() => open(view ? "revise" : "settings")} disabled={writing}>
            <DocumentIcon />
            Open PDF
          </Button>
          {view && (
            <Button onClick={() => open("revise", null, [], true)} disabled={writing}>
              Revise with the team
            </Button>
          )}
          <Button onClick={() => open("settings")} disabled={writing}>
            Currency, units and text
          </Button>
          <Button variant="quiet" onClick={() => open("history")} disabled={writing}>
            History
          </Button>
          <Menu
            label="More actions"
            items={[
              ...(view
                ? [
                    {
                      label: "Rewrite the proposal",
                      description: "Write it again from the team's report. Replaces your edits to it.",
                      icon: <RefreshIcon />,
                      onSelect: () => setConfirm("rewrite"),
                    },
                  ]
                : []),
              {
                label: "Reset to the latest results",
                description: "Rebuild the report from the session's latest results, without your edits or the proposal.",
                icon: <UndoIcon />,
                onSelect: () => setConfirm("reset"),
              },
            ]}
          />
        </div>

        <div className="mt-6 space-y-3">
          {report.outdated && (
            <Notice tone="warn">
              A later evaluation in this session produced newer results, which this report does not include. Reset it to
              use them; that drops your edits and the proposal.
            </Notice>
          )}
          {message && <Notice tone={message.tone}>{message.text}</Notice>}
          {revisingPassage && (
            <Progress
              title="The passage's writer is revising it."
              wait="This takes ten to thirty seconds."
              stages={["Its writer rewrites just that passage", "You see the change before it is saved"]}
            />
          )}
          {writing && (
            <Progress
              title="The agents are writing the investment proposal."
              wait={proposalWait(reasoning)}
              stages={[
                "Marketing, Technical and Risk & Compliance write their parts at the same time",
                "Finance writes the financial plan from them, and corrects figures that fail a check",
                "The Chief of Staff writes the executive summary and the success metrics",
              ]}
            />
          )}
        </div>

        <CurrencyContext.Provider value={report.settings.currency}>
        <PassageContext.Provider value={passage}>
        <div className="mt-14">
          {view ? (
            <Tabs
              // Remount the chapters, closing any open form, when another report is shown.
              key={report.session_id}
              label="Chapters"
              orientation="vertical"
              tabs={[
                ...CHAPTERS.map(({ number, name, title, part, only, View }) => ({
                  label: name,
                  marker: number,
                  agent: PART_AGENT[part],
                  content: (
                    <Chapter
                      key={`${name}-${report.version}`}
                      number={number}
                      title={title}
                      part={part}
                      only={only}
                      value={view.proposal[part] as unknown as Record<string, unknown>}
                      onSave={(edited) => savePart(part, edited)}
                    >
                      <View {...view} />
                    </Chapter>
                  ),
                })),
                {
                  label: "The team's report",
                  marker: "A",
                  content: (
                    <div>
                      <div className="border-b border-rule pb-6">
                        <p className="kicker">Appendix</p>
                        <h2 className="mt-1 font-serif text-[1.9rem] leading-tight font-medium">
                          The founding team&apos;s report
                        </h2>
                        <p className="mt-2 text-sm text-ink-3">
                          The reviewed reports and decisions the proposal was written from
                        </p>
                      </div>
                      <div className="mt-8">
                        <TeamReport
                          key={report.version}
                          sections={report.sections}
                          hidden={report.settings.hidden}
                          onSave={saveSections}
                        />
                      </div>
                    </div>
                  ),
                },
              ]}
            />
          ) : (
            <>
              <section className="grid grid-cols-1 gap-6 rounded-lg border border-rule bg-surface p-6 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <div>
                  <h3 className="font-serif text-xl font-medium">Turn this into an investment proposal</h3>
                  <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-2">
                    The agents write it up from this report: market sizing, a competitor matrix, the roadmap, three-year
                    projections with NPV, IRR and payback, a risk matrix and success metrics, with charts.{" "}
                    {proposalWait(reasoning)}
                  </p>
                </div>
                <div className="flex flex-wrap items-end gap-2">
                  <div className="w-36">
                    <Label htmlFor="proposal-currency">In</Label>
                    <Select
                      id="proposal-currency"
                      value={currency ?? report.settings.currency}
                      onChange={(event) => setCurrency(event.target.value)}
                    >
                      {Object.entries(CURRENCIES).map(([code, { name }]) => (
                        <option key={code} value={code} title={name}>
                          {code}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <Button variant="primary" onClick={write} disabled={writing}>
                    Write the investment proposal
                  </Button>
                </div>
              </section>
              <div className="mt-14">
                <TeamReport
                  key={`${report.session_id}-${report.version}`}
                  sections={report.sections}
                  hidden={report.settings.hidden}
                  onSave={saveSections}
                />
              </div>
            </>
          )}
        </div>
        </PassageContext.Provider>
        </CurrencyContext.Provider>

        <Dialog
          open={studio !== null}
          title="The document"
          description={view ? view.proposal.executive.project_name : report.objective}
          onClose={() => setStudio(null)}
        >
          {studio && (
            <PdfPanel
              key={studio.opened}
              report={report}
              reasoning={reasoning}
              focusPrompt={studio.focus}
              initialTool={studio.tool}
              initialDraft={studio.draft}
              initialFlags={studio.flags}
              onChanged={(revised) => (revised ? setReport(revised) : load(report.session_id))}
            />
          )}
        </Dialog>

        <Dialog
          open={confirm !== null}
          size="small"
          title={confirm === "rewrite" ? "Rewrite the proposal?" : "Reset the report?"}
          onClose={() => setConfirm(null)}
        >
          <p className="text-sm leading-relaxed text-ink-2">
            {confirm === "rewrite"
              ? "The agents write the proposal again from the team's report as it stands. This replaces it, with your edits and revisions to it."
              : "This rebuilds the report from the session's latest results and drops your edits and the proposal."}
          </p>
          <div className="mt-6 flex justify-end gap-2">
            <Button onClick={() => setConfirm(null)}>Keep it</Button>
            <Button variant="primary" onClick={confirm === "rewrite" ? write : reset}>
              {confirm === "rewrite" ? "Rewrite it" : "Reset the report"}
            </Button>
          </div>
        </Dialog>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Reports" description={DESCRIPTION} aside={picker} />
      {body}
    </div>
  );
}

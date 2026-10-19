"use client";

// The Reports page: each session's report, read on the page and edited in
// place. Until the agents write the investment proposal it is the team's
// report; after, a tab per section of the proposal, each with charts, the agent
// that wrote it and an Edit button. "Open PDF" shows the document in a pop-up,
// where the founder can ask the team to revise a part.

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { Progress } from "@/components/evaluate/working";
import { EditForm } from "@/components/reports/edit-form";
import { PdfPanel } from "@/components/reports/pdf-panel";
import {
  ExecutiveSection,
  FinancialSection,
  KpiSection,
  MarketSection,
  RiskSection,
  TechnicalSection,
} from "@/components/reports/proposal-view";
import { TeamReport } from "@/components/reports/team-report";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Tabs } from "@/components/ui/tabs";
import {
  ApiError,
  getReport,
  listReports,
  type PartKey,
  type Proposal,
  type Report,
  type ReportSection,
  type ReportSummary,
  resetReport,
  saveProposal,
  saveReport,
  writeProposal,
} from "@/lib/api";
import { useBackend } from "@/lib/backend";
import { PART_TITLES } from "@/lib/proposal";
import { proposalWait } from "@/lib/team";

type Notice = { tone: "success" | "warning" | "error"; text: string };

const NOTICE_STYLE = {
  success: "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  warning: "bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  error: "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200",
};

const CHANGED_ELSEWHERE = "The report changed elsewhere, so it has been reloaded. Make the change again.";

// The proposal's tabs: the part each edits, and the fields of it the form shows.
const SECTIONS: {
  name: string;
  part: PartKey;
  only?: string[];
  View: typeof ExecutiveSection;
}[] = [
  {
    name: "Executive summary",
    part: "executive",
    only: ["project_name", "verdict", "recommendation", "overview", "opportunity", "strategic_alignment", "financial_case"],
    View: ExecutiveSection,
  },
  { name: "Market", part: "market", View: MarketSection },
  { name: "Technical", part: "technical", View: TechnicalSection },
  { name: "Financial", part: "financial", View: FinancialSection },
  { name: "Risk & compliance", part: "risk", View: RiskSection },
  { name: "KPIs", part: "executive", only: ["kpis"], View: KpiSection },
];

function when(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
}

function label(summary: ReportSummary): string {
  const title = summary.title.length > 80 ? `${summary.title.slice(0, 77)}...` : summary.title;
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
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          Each session&apos;s report: read it, edit it, have the agents write it up as an investment proposal, and get the PDF.
        </p>
      </header>
      {inBrowser && <Reports />}
    </div>
  );
}

function Reports() {
  const { reasoning } = useBackend();
  const [summaries, setSummaries] = useState<ReportSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [writing, setWriting] = useState(false);
  const [confirm, setConfirm] = useState<"rewrite" | "reset" | null>(null);
  const [pdfOpen, setPdfOpen] = useState(false);

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
      setNotice({ tone: "warning", text: CHANGED_ELSEWHERE });
      return CHANGED_ELSEWHERE;
    }
    return (error as Error).message;
  }

  async function write() {
    if (!report) return;
    setConfirm(null);
    setNotice(null);
    setWriting(true);
    try {
      const result = await writeProposal(report.session_id, report.version, reasoning);
      setReport(result.report);
      setNotice({ tone: "success", text: "The investment proposal is written. Open the PDF to see it as a document, and to ask the team for changes." });
    } catch (error) {
      const message = failed(error);
      if (message !== CHANGED_ELSEWHERE) setNotice({ tone: "error", text: message });
    } finally {
      setWriting(false);
    }
  }

  async function reset() {
    if (!report) return;
    setConfirm(null);
    try {
      setReport(await resetReport(report.session_id));
      setNotice({ tone: "success", text: "The report was rebuilt from the session's latest results." });
    } catch (error) {
      setNotice({ tone: "error", text: (error as Error).message });
    }
  }

  async function savePart(part: PartKey, edited: Record<string, unknown>): Promise<string | null> {
    if (!report?.proposal) return null;
    try {
      const proposal = { ...report.proposal, [part]: { ...report.proposal[part], ...edited } } as Proposal;
      setReport(await saveProposal(report.session_id, report.version, proposal));
      setNotice({ tone: "success", text: `Saved your changes to the ${PART_TITLES[part]} part.` });
      return null;
    } catch (error) {
      return failed(error);
    }
  }

  async function saveSections(sections: ReportSection[]): Promise<string | null> {
    if (!report) return null;
    try {
      setReport(await saveReport(report.session_id, report.version, sections));
      setNotice({ tone: "success", text: "Saved your changes to the team's report." });
      return null;
    } catch (error) {
      return failed(error);
    }
  }

  if (problem && !report) {
    return (
      <p role="alert" className={`rounded-md px-4 py-3 text-sm ${NOTICE_STYLE.error}`}>
        {problem}
      </p>
    );
  }
  if (summaries && !summaries.length) {
    return (
      <p className="rounded-md bg-accent-soft/40 px-4 py-3 text-sm dark:bg-accent/10">
        No reports yet. Run an evaluation on the Evaluate page, and its report appears here.
      </p>
    );
  }
  if (!summaries || !report) return <p className="text-sm text-zinc-500">Loading the reports…</p>;

  const button =
    "rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800";

  return (
    <div className="space-y-6">
      <div>
        <label htmlFor="report" className="mb-1 block text-sm font-medium">
          Report
        </label>
        <select
          id="report"
          value={selected ?? ""}
          onChange={(event) => {
            setSelected(event.target.value);
            setNotice(null);
            setPdfOpen(false);
          }}
          className="w-full rounded-md border border-zinc-300 bg-surface px-3 py-2 text-sm dark:border-zinc-700"
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
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        {report.proposal ? <Badge tone="green">Investment proposal</Badge> : <Badge tone="gray">Team report</Badge>}
        {report.edited && <Badge tone="amber">Edited</Badge>}
        <span className="text-zinc-500">
          Version {report.version} · objective: {report.objective}
        </span>
      </div>

      {report.outdated && (
        <p role="note" className={`rounded-md px-4 py-3 text-sm ${NOTICE_STYLE.warning}`}>
          A later evaluation in this session produced newer results, which this report does not include. Reset it to use them; that drops your edits and the proposal.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {!report.proposal && (
          <button type="button" onClick={write} disabled={writing} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50">
            Write the investment proposal
          </button>
        )}
        {report.proposal && (
          <button type="button" onClick={() => setConfirm("rewrite")} disabled={writing} className={button}>
            Rewrite the proposal
          </button>
        )}
        <button type="button" onClick={() => setPdfOpen(true)} disabled={writing} className={button}>
          Open PDF
        </button>
        <button type="button" onClick={() => setConfirm("reset")} disabled={writing} className={button}>
          Reset to the latest results
        </button>
      </div>

      {confirm && (
        <div role="alertdialog" aria-label="Confirm" className={`flex flex-wrap items-center gap-3 rounded-md px-4 py-3 text-sm ${NOTICE_STYLE.warning}`}>
          <span>
            {confirm === "rewrite"
              ? "The agents write the proposal again from the team's report as it stands. This replaces it, with your edits and revisions to it."
              : "This rebuilds the report from the session's latest results and drops your edits and the proposal."}
          </span>
          <button type="button" onClick={confirm === "rewrite" ? write : reset} className="rounded-md bg-amber-600 px-3 py-1.5 font-semibold text-white hover:bg-amber-700">
            {confirm === "rewrite" ? "Rewrite it" : "Reset the report"}
          </button>
          <button type="button" onClick={() => setConfirm(null)} className="rounded-md px-3 py-1.5 hover:bg-amber-100 dark:hover:bg-amber-900">
            Keep it
          </button>
        </div>
      )}

      {writing && (
        <Progress
          title="The agents are writing the investment proposal."
          wait={proposalWait(reasoning)}
          stages={[
            "Marketing, Technical and Risk & Compliance write their parts at the same time",
            "Finance writes the financial plan from them, and corrects figures that fail a check",
            "The Chief of Staff writes the executive summary and the KPIs",
          ]}
        />
      )}

      {notice && (
        <p role={notice.tone === "success" ? "status" : "alert"} className={`rounded-md px-4 py-3 text-sm ${NOTICE_STYLE[notice.tone]}`}>
          {notice.text}
        </p>
      )}

      <Dialog open={pdfOpen} title="Report PDF" onClose={() => setPdfOpen(false)}>
        <PdfPanel
          report={report}
          reasoning={reasoning}
          onChanged={(revised) => (revised ? setReport(revised) : load(report.session_id))}
        />
      </Dialog>

      {report.proposal && report.investment ? (
        <Tabs
          // Remount the tabs, and close any open form, when another report is shown.
          key={report.session_id}
          label="The proposal's sections"
          tabs={[
            ...SECTIONS.map(({ name, part, only, View }) => ({
              label: name,
              content: (
                <Section
                  key={`${name}-${report.version}`}
                  part={part}
                  only={only}
                  value={report.proposal![part] as unknown as Record<string, unknown>}
                  onSave={(edited) => savePart(part, edited)}
                >
                  <View proposal={report.proposal!} metrics={report.investment!} checks={report.checks} />
                </Section>
              ),
            })),
            {
              label: "Team report",
              content: <TeamReport key={report.version} sections={report.sections} onSave={saveSections} />,
            },
          ]}
        />
      ) : (
        <>
          <p className="rounded-md bg-accent-soft/40 px-4 py-3 text-sm dark:bg-accent/10">
            This is the team&apos;s report. <strong>Write the investment proposal</strong> to have the agents turn it into a full proposal: market sizing, a competitor matrix, the roadmap, three-year projections with NPV, IRR and payback, a risk matrix and KPIs, with charts.
          </p>
          <TeamReport key={`${report.session_id}-${report.version}`} sections={report.sections} onSave={saveSections} />
        </>
      )}
    </div>
  );
}

// One tab of the proposal: its view, or the form that edits it.
function Section({
  part,
  only,
  value,
  onSave,
  children,
}: {
  part: PartKey;
  only?: string[];
  value: Record<string, unknown>;
  onSave: (edited: Record<string, unknown>) => Promise<string | null>;
  children: React.ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
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
    );
  }
  return (
    <div>
      <div className="mb-3 flex justify-end">
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          Edit
        </button>
      </div>
      {children}
    </div>
  );
}

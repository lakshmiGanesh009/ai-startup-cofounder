"use client";

// What the PDF pop-up shows: the inline prompt that asks the team to revise
// the proposal, the download, and the document itself in the browser's own PDF
// viewer. The PDF is fetched again whenever the report's version changes.

import { useEffect, useState } from "react";

import { Progress } from "@/components/evaluate/working";
import { ApiError, type PartKey, type Reasoning, type Report, reportPdf, reviseProposal } from "@/lib/api";
import { PART_AGENTS, PART_TITLES } from "@/lib/proposal";
import { proposalWait } from "@/lib/team";

type Pdf = { version: number; url: string } | { version: number; error: string };
type Notice = { tone: "success" | "warning" | "error"; text: string };

const NOTICE_STYLE = {
  success: "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  warning: "bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  error: "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200",
};

export function PdfPanel({
  report,
  reasoning,
  onChanged,
}: {
  report: Report;
  reasoning: Reasoning | null;
  // Called with the revised report, or with nothing when it changed elsewhere.
  onChanged: (report: Report | null) => void;
}) {
  const [pdf, setPdf] = useState<Pdf | null>(null);
  const [part, setPart] = useState<PartKey | "whole">("whole");
  const [instruction, setInstruction] = useState("");
  const [revising, setRevising] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    reportPdf(report.session_id)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setPdf({ version: report.version, url });
      })
      .catch((error: Error) => {
        if (!cancelled) setPdf({ version: report.version, error: error.message });
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [report.session_id, report.version]);

  async function revise(event: React.FormEvent) {
    event.preventDefault();
    if (!instruction.trim()) {
      setNotice({ tone: "warning", text: "Say what to change." });
      return;
    }
    setNotice(null);
    setRevising(true);
    try {
      const result = await reviseProposal(report.session_id, report.version, instruction.trim(), part === "whole" ? null : part, reasoning);
      setInstruction("");
      setNotice(
        result.failed.length
          ? { tone: "warning", text: `Could not revise: ${result.failed.join(", ")}. They keep their text.` }
          : { tone: "success", text: "The proposal was revised." },
      );
      onChanged(result.report);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setNotice({ tone: "warning", text: "The report changed elsewhere, so it has been reloaded. Make the request again." });
        onChanged(null);
      } else {
        setNotice({ tone: "error", text: (error as Error).message });
      }
    } finally {
      setRevising(false);
    }
  }

  const current = pdf?.version === report.version ? pdf : null;
  const kind = report.proposal ? "investment-proposal" : "launch-report";

  return (
    <div className="space-y-4">
      {report.proposal ? (
        <form onSubmit={revise} aria-label="Ask the team to revise the proposal" className="space-y-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
          <p className="font-semibold">Ask the team to revise the proposal</p>
          <div className="grid gap-3 sm:grid-cols-[16rem_1fr]">
            <div>
              <label htmlFor="revise-part" className="mb-1 block text-sm">
                Part
              </label>
              <select
                id="revise-part"
                value={part}
                onChange={(event) => setPart(event.target.value as PartKey | "whole")}
                className="w-full rounded-md border border-zinc-300 bg-surface px-2.5 py-2 text-sm dark:border-zinc-700"
              >
                <option value="whole">The whole proposal</option>
                {(Object.keys(PART_TITLES) as PartKey[]).map((key) => (
                  <option key={key} value={key}>
                    {PART_TITLES[key]} ({PART_AGENTS[key]})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="revise-instruction" className="mb-1 block text-sm">
                What to change
              </label>
              <textarea
                id="revise-instruction"
                rows={2}
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
                placeholder="Make the year-one figures more conservative and add a referral channel."
                className="w-full rounded-md border border-zinc-300 bg-surface px-3 py-2 text-sm dark:border-zinc-700"
              />
            </div>
          </div>
          <button type="submit" disabled={revising} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50">
            Revise
          </button>
        </form>
      ) : (
        <p className="rounded-md bg-accent-soft/40 px-4 py-3 text-sm dark:bg-accent/10">
          This is the team&apos;s report. Write the investment proposal to get the full document with charts, and to ask the team for changes here.
        </p>
      )}
      {revising && (
        <Progress
          title={part === "whole" ? "Every agent is revising its part." : `The ${PART_AGENTS[part]} is revising its part.`}
          wait={proposalWait(reasoning)}
          stages={[
            part === "whole" ? "Each agent applies your instruction to its part" : `The ${PART_TITLES[part]} part is rewritten`,
            "The parts built on it are brought into line",
            "The PDF is drawn again",
          ]}
        />
      )}
      {notice && (
        <p role={notice.tone === "success" ? "status" : "alert"} className={`rounded-md px-4 py-3 text-sm ${NOTICE_STYLE[notice.tone]}`}>
          {notice.text}
        </p>
      )}
      {!current && <p className="text-sm text-zinc-500">Drawing the PDF…</p>}
      {current && "error" in current && (
        <p role="alert" className={`rounded-md px-4 py-3 text-sm ${NOTICE_STYLE.error}`}>
          The PDF could not be made. {current.error}
        </p>
      )}
      {current && "url" in current && (
        <>
          <a
            href={current.url}
            download={`${kind}-${report.session_id.slice(0, 8)}.pdf`}
            className="inline-flex rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            Download PDF
          </a>
          <iframe src={current.url} title="The report as a PDF" className="h-[70dvh] w-full rounded-md border border-zinc-200 dark:border-zinc-800" />
        </>
      )}
    </div>
  );
}

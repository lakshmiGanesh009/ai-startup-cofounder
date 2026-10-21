"use client";

// Questions about a report: the Chief of Staff answers from the passages of
// the documents chosen (this report, the files its run worked from, and any
// others added) and nothing else, citing each one it uses. The sources it
// cites are listed under the answer, so each claim can be checked.

import { useEffect, useId, useRef, useState } from "react";

import {
  DocumentNamesProvider,
  DocumentPicker,
  type DocumentRef,
  Mark,
  type ReportRef,
  useDocuments,
} from "@/components/documents";
import { GuardrailNotice } from "@/components/guardrail-notice";
import { Markdown } from "@/components/markdown";
import { AgentAvatar } from "@/components/ui/agent";
import { Button, Kbd } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Progress } from "@/components/ui/progress";
import {
  ask,
  type AskResult,
  getUpload,
  type Reasoning,
  type Report,
  type ReportSummary,
  type UploadSummary,
} from "@/lib/api";

const BRIEF_CLASS =
  "block w-full resize-y rounded-lg border border-rule-strong bg-surface px-4 py-3 font-serif text-[1.05rem] leading-relaxed text-ink placeholder:text-ink-3 focus:border-focus focus:ring-3 focus:ring-focus/20 focus:outline-none";

type Exchange = { question: string; documents: DocumentRef[]; result: AskResult };

// The report's own documents, loaded before the panel starts with them: the
// report, the files its run worked from that are still kept, and its earlier reports.
export function AskPanel({
  report,
  summaries,
  reasoning,
}: {
  report: Report;
  summaries: ReportSummary[];
  reasoning: Reasoning | null;
}) {
  const [files, setFiles] = useState<UploadSummary[] | null>(null);
  const uploads = report.worked_from?.uploads ?? [];

  useEffect(() => {
    Promise.all(uploads.map((id) => getUpload(id).catch(() => null))).then((found) =>
      setFiles(found.filter((upload): upload is UploadSummary => upload !== null)),
    );
    // The report's files are read once, when the panel opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!files) return <p className="p-5 text-sm text-ink-3">Loading the report&apos;s documents…</p>;
  const titled = (id: string): ReportRef => ({
    session_id: id,
    title: summaries.find((summary) => summary.session_id === id)?.title ?? "An earlier report",
  });
  const reports = [
    { session_id: report.session_id, title: report.title },
    ...(report.worked_from?.reports ?? []).filter((id) => id !== report.session_id).map(titled),
  ];
  return <Questions files={files} reports={reports} reasoning={reasoning} />;
}

function Questions({
  files,
  reports,
  reasoning,
}: {
  files: UploadSummary[];
  reports: ReportRef[];
  reasoning: Reasoning | null;
}) {
  const id = useId();
  const documents = useDocuments({ files, reports });
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const latest = useRef<HTMLDivElement>(null);
  const none = !documents.uploads.length && !documents.reportIds.length;

  useEffect(() => {
    latest.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [exchanges.length]);

  async function submit(event?: React.FormEvent) {
    event?.preventDefault();
    const asked = question.trim();
    if (!asked || asking) return;
    if (none) {
      setProblem("Choose a report or a file to ask about.");
      return;
    }
    if (documents.reading) {
      setProblem("Wait until the files have been read.");
      return;
    }
    setProblem(null);
    setAsking(true);
    const named = documents.refs;
    try {
      const result = await ask(asked, documents.uploads, documents.reportIds, reasoning);
      setExchanges((current) => [...current, { question: asked, documents: named, result }]);
      setQuestion("");
    } catch (reason) {
      setProblem((reason as Error).message);
    } finally {
      setAsking(false);
    }
  }

  // On a wide screen the conversation and the documents scroll side by side;
  // on a narrow one the panel scrolls as one page: answers, question, documents.
  return (
    <div className="h-full overflow-y-auto p-4 sm:p-5 lg:overflow-hidden">
      <div className="grid grid-cols-1 gap-6 lg:h-full lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-8">
        <div className="flex flex-col lg:min-h-0">
          <div className="space-y-8 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-1">
            {exchanges.length === 0 && !asking && (
              <div className="max-w-xl rounded-lg border border-dashed border-rule-strong px-5 py-6">
                <p className="flex items-center gap-2.5 text-sm font-medium text-ink">
                  <AgentAvatar agent="chief" size="sm" />
                  Ask the Chief of Staff
                </p>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">
                  It answers from the documents on the right and nothing else, and cites the passage behind each claim. Add
                  files or other reports to compare them.
                </p>
                <ul className="mt-3 space-y-1 text-sm text-ink-3">
                  <li>“What did the team assume about churn, and does my plan agree?”</li>
                  <li>“Which risks are rated high, and what do they cost to mitigate?”</li>
                </ul>
              </div>
            )}
            {exchanges.map((exchange, index) => (
              <div key={index} ref={index === exchanges.length - 1 ? latest : undefined}>
                <Answered exchange={exchange} />
              </div>
            ))}
            {asking && (
              <Progress
                title="The Chief of Staff is reading the passages."
                wait="This takes ten to twenty seconds."
                stages={["Finds the passages that bear on your question", "Answers from them, citing each"]}
              />
            )}
          </div>

          <form aria-label="Ask a question" onSubmit={submit} className="mt-5 border-t border-rule pt-5">
            <label htmlFor={`${id}-question`} className="sr-only">
              Your question
            </label>
            <textarea
              id={`${id}-question`}
              rows={2}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") void submit();
              }}
              placeholder="Ask about this report, or compare it with your files…"
              className={BRIEF_CLASS}
            />
            {problem && (
              <Notice tone="bad" className="mt-3">
                {problem}
              </Notice>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
              <Button type="submit" variant="primary" disabled={asking || !question.trim()}>
                Ask
                <Kbd>⌘↵</Kbd>
              </Button>
              <p className="text-xs text-ink-3">
                {documents.refs.length
                  ? `From ${documents.refs.map((document) => document.ref).join(", ")}`
                  : "Choose a document to ask about"}
              </p>
            </div>
          </form>
        </div>

        <aside
          aria-label="Documents to ask about"
          className="rounded-xl border border-rule bg-sunken/40 p-4 lg:min-h-0 lg:overflow-y-auto"
        >
          <p className="kicker">Asking about</p>
          <div className="mt-3">
            <DocumentPicker documents={documents} id={id} />
          </div>
        </aside>
      </div>
    </div>
  );
}

function Answered({ exchange }: { exchange: Exchange }) {
  const { question, documents, result } = exchange;
  return (
    <article aria-label={question} className="space-y-4">
      <p className="ml-auto max-w-[85%] rounded-xl rounded-br-sm bg-primary-soft px-4 py-2.5 text-[15px] text-ink">
        {question}
      </p>
      <GuardrailNotice flags={result.guardrails} />
      <div className="agent-chief rounded-xl border border-rule bg-surface px-5 py-4 shadow-[0_1px_2px_rgb(0_0_0/0.04)]">
        <p className="mb-3 flex items-center gap-2 text-xs text-ink-3">
          <AgentAvatar agent="chief" size="xs" />
          <span className="font-medium text-ink">Chief of Staff</span>
        </p>
        <DocumentNamesProvider value={documents}>
          <Markdown compact>{result.answer}</Markdown>
        </DocumentNamesProvider>
        {result.sources.length > 0 && (
          <details className="mt-4 border-t border-rule pt-3">
            <summary className="cursor-pointer text-xs font-medium text-ink-2">
              {result.sources.length} {result.sources.length === 1 ? "passage" : "passages"} cited
            </summary>
            <ol className="mt-3 space-y-3">
              {result.sources.map((source) => (
                <li key={source.mark} className="text-sm">
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <Mark>{source.mark.slice(1).split(" · ")[0]}</Mark>
                    <span className="max-w-full truncate font-medium text-ink">{source.name}</span>
                    <span className="text-xs text-ink-3">{source.where}</span>
                  </p>
                  <blockquote className="mt-1.5 border-l-2 border-rule-strong pl-3 text-[13px] leading-relaxed whitespace-pre-line text-ink-2">
                    {source.text}
                    {source.text.length >= 400 ? "…" : ""}
                  </blockquote>
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
    </article>
  );
}

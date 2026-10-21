"use client";

// The founder's documents for a run or a question: files uploaded here (the
// API keeps only their text) and earlier reports from this app. Each wears the
// mark the agents cite it by, D1 for the first file and R1 for the first
// report, so a citation like [D1 · page 3] leads back to its file.

import { createContext, useContext, useEffect, useRef, useState } from "react";

import { Select } from "@/components/ui/field";
import { AlertIcon, CloseIcon, DocumentIcon, PaperclipIcon } from "@/components/ui/icons";
import {
  ApiError,
  type GuardrailFlag,
  listReports,
  MAX_UPLOAD_BYTES,
  type ReportSummary,
  UPLOAD_TYPES,
  type UploadSummary,
  uploadFile,
} from "@/lib/api";

// Of each kind, as the API takes them.
export const MAX_DOCUMENTS = 5;

export type Attached = {
  key: string;
  name: string;
  status: "reading" | "ready" | "failed";
  upload?: UploadSummary;
  problem?: string;
  flags?: GuardrailFlag[];
};

export type ReportRef = { session_id: string; title: string };

// A document as a run or an answer names it: its mark, its name, what it is.
export type DocumentRef = { ref: string; name: string; detail: string };

// The marks' documents, for the views that show citations of them.
const DocumentNames = createContext<DocumentRef[]>([]);
export const DocumentNamesProvider = DocumentNames.Provider;
export const useDocumentNames = () => useContext(DocumentNames);

export function describeUpload(upload: UploadSummary): string {
  return `${upload.kind} · ${upload.parts}`;
}

export function useDocuments(initial: { files?: UploadSummary[]; reports?: ReportRef[] } = {}) {
  const [files, setFiles] = useState<Attached[]>(() =>
    (initial.files ?? []).map((upload) => ({ key: upload.id, name: upload.name, status: "ready", upload })),
  );
  const [reports, setReports] = useState<ReportRef[]>(initial.reports ?? []);
  const counter = useRef(0);

  const update = (key: string, change: Partial<Attached>) =>
    setFiles((current) => current.map((file) => (file.key === key ? { ...file, ...change } : file)));

  function add(chosen: File[]) {
    let room = MAX_DOCUMENTS - files.filter((file) => file.status !== "failed").length;
    const added: Attached[] = [];
    for (const file of chosen) {
      const key = `file-${++counter.current}`;
      if (room <= 0) {
        added.push({ key, name: file.name, status: "failed", problem: `At most ${MAX_DOCUMENTS} files: remove one first.` });
        continue;
      }
      if (file.size > MAX_UPLOAD_BYTES) {
        added.push({ key, name: file.name, status: "failed", problem: "The file is larger than 10 MB." });
        continue;
      }
      room -= 1;
      added.push({ key, name: file.name, status: "reading" });
      uploadFile(file).then(
        ({ upload, guardrails }) => update(key, { status: "ready", upload, name: upload.name, flags: guardrails }),
        (reason: unknown) =>
          update(key, { status: "failed", problem: reason instanceof ApiError ? reason.detail : String(reason) }),
      );
    }
    setFiles((current) => [...current, ...added]);
  }

  const ready = files.filter((file): file is Attached & { upload: UploadSummary } => Boolean(file.upload));
  const refs: DocumentRef[] = [
    ...ready.map((file, index) => ({ ref: `D${index + 1}`, name: file.upload.name, detail: describeUpload(file.upload) })),
    ...reports.map((report, index) => ({ ref: `R${index + 1}`, name: report.title, detail: "An earlier report" })),
  ];
  return {
    files,
    reports,
    refs,
    add,
    remove: (key: string) => setFiles((current) => current.filter((file) => file.key !== key)),
    addReport: (report: ReportRef) =>
      setReports((current) => (current.some((each) => each.session_id === report.session_id) ? current : [...current, report])),
    removeReport: (id: string) => setReports((current) => current.filter((report) => report.session_id !== id)),
    uploads: ready.map((file) => file.upload.id),
    reportIds: reports.map((report) => report.session_id),
    reading: files.some((file) => file.status === "reading"),
  };
}

export type Documents = ReturnType<typeof useDocuments>;

// A document's mark: D1, R2.
export function Mark({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex h-5 min-w-7 shrink-0 items-center justify-center rounded border border-rule-strong bg-sunken px-1 font-mono text-[11px] font-medium text-ink-2">
      {children}
    </span>
  );
}

function Chip({
  mark,
  name,
  detail,
  tone = "plain",
  onRemove,
  children,
}: {
  mark: React.ReactNode;
  name: string;
  detail: React.ReactNode;
  tone?: "plain" | "bad";
  onRemove: () => void;
  children?: React.ReactNode;
}) {
  return (
    <li
      className={`flex min-w-0 items-start gap-3 rounded-lg border px-3 py-2.5 ${
        tone === "bad" ? "border-bad/40 bg-bad-soft" : "border-rule bg-surface"
      }`}
    >
      <span className="mt-0.5">{mark}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-ink">{name}</span>
        <span className={`mt-0.5 block text-xs ${tone === "bad" ? "text-bad" : "text-ink-3"}`}>{detail}</span>
        {children}
      </span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${name}`}
        className="-mr-1 rounded p-1 text-ink-3 transition-colors hover:bg-sunken hover:text-ink"
      >
        <CloseIcon className="size-3.5" />
      </button>
    </li>
  );
}

// Add files (chosen or dropped) and earlier reports, and see what was read of each.
export function DocumentPicker({ documents, id }: { documents: Documents; id: string }) {
  const [available, setAvailable] = useState<ReportSummary[] | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    listReports()
      .then(setAvailable)
      .catch(() => setAvailable([]));
  }, []);

  const marks = new Map(documents.files.filter((file) => file.upload).map((file, index) => [file.key, `D${index + 1}`]));
  const choosable = (available ?? []).filter(
    (report) => !documents.reports.some((chosen) => chosen.session_id === report.session_id),
  );
  const full = documents.files.filter((file) => file.status !== "failed").length >= MAX_DOCUMENTS;

  return (
    // Its lists take two columns where there is room: on the brief, not beside the questions.
    <div className="@container space-y-3">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          documents.add(Array.from(event.dataTransfer.files));
        }}
        className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-dashed px-4 py-3.5 transition-colors ${
          dragging ? "border-focus bg-primary-soft" : "border-rule-strong bg-sunken/40"
        }`}
      >
        <label
          className={`inline-flex h-8 cursor-pointer items-center gap-2 rounded-md border border-rule-strong bg-surface px-2.5 text-[13px] font-medium text-ink transition-colors hover:border-ink-3 has-focus-visible:ring-3 has-focus-visible:ring-focus/30 ${
            full ? "pointer-events-none opacity-45" : ""
          }`}
        >
          <PaperclipIcon />
          Add files
          <input
            id={`${id}-files`}
            type="file"
            multiple
            accept={UPLOAD_TYPES}
            disabled={full}
            className="sr-only"
            onChange={(event) => {
              documents.add(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
        </label>
        <span className="text-xs leading-snug text-ink-3">
          or drop them here · PDF, Word, PowerPoint, Excel, CSV, text · up to 10 MB each
        </span>
      </div>

      {documents.files.length > 0 && (
        <ul aria-label="Files" className="grid grid-cols-1 gap-2 @lg:grid-cols-2">
          {documents.files.map((file) => {
            if (file.status === "failed") {
              return (
                <Chip
                  key={file.key}
                  mark={<AlertIcon className="size-4 text-bad" />}
                  name={file.name}
                  detail={file.problem ?? "The file could not be read."}
                  tone="bad"
                  onRemove={() => documents.remove(file.key)}
                />
              );
            }
            const mark = marks.get(file.key);
            const notes = [
              ...(file.upload?.warnings ?? []),
              ...(file.flags?.length ? ["Text in it that tried to instruct the agents was cut out."] : []),
            ];
            return (
              <Chip
                key={file.key}
                mark={
                  mark ? (
                    <Mark>{mark}</Mark>
                  ) : (
                    <span className="block size-4 animate-spin rounded-full border-2 border-rule-strong border-t-ink-2" />
                  )
                }
                name={file.name}
                detail={file.upload ? describeUpload(file.upload) : "Reading…"}
                onRemove={() => documents.remove(file.key)}
              >
                {notes.map((note) => (
                  <span key={note} className="mt-1 block text-xs text-warn">
                    {note}
                  </span>
                ))}
              </Chip>
            );
          })}
        </ul>
      )}

      {(choosable.length > 0 || documents.reports.length > 0) && (
        <div className="space-y-2">
          {choosable.length > 0 && documents.reports.length < MAX_DOCUMENTS && (
            <Select
              aria-label="Add an earlier report"
              value=""
              onChange={(event) => {
                const report = choosable.find((each) => each.session_id === event.target.value);
                if (report) documents.addReport({ session_id: report.session_id, title: report.title });
              }}
            >
              <option value="">Add an earlier report…</option>
              {choosable.map((report) => (
                <option key={report.session_id} value={report.session_id}>
                  {report.title.length > 90 ? `${report.title.slice(0, 88)}…` : report.title}
                </option>
              ))}
            </Select>
          )}
          {documents.reports.length > 0 && (
            <ul aria-label="Earlier reports" className="grid grid-cols-1 gap-2 @lg:grid-cols-2">
              {documents.reports.map((report, index) => (
                <Chip
                  key={report.session_id}
                  mark={<Mark>{`R${index + 1}`}</Mark>}
                  name={report.title}
                  detail={
                    <span className="inline-flex items-center gap-1">
                      <DocumentIcon className="size-3" />
                      An earlier report from this app
                    </span>
                  }
                  onRemove={() => documents.removeReport(report.session_id)}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// The documents a run or an answer worked from, by their marks.
export function DocumentList({ documents, className = "" }: { documents: DocumentRef[]; className?: string }) {
  if (!documents.length) return null;
  return (
    // It may shrink in a row beside a label, so a long name is cut short, not the page widened.
    <ul className={`flex max-w-full min-w-0 flex-wrap gap-x-4 gap-y-1.5 ${className}`}>
      {documents.map((document) => (
        <li key={document.ref} className="flex max-w-full min-w-0 items-center gap-2 text-sm">
          <Mark>{document.ref}</Mark>
          <span className="min-w-0 truncate text-ink-2">{document.name}</span>
          <span className="shrink-0 text-xs text-ink-3">{document.detail}</span>
        </li>
      ))}
    </ul>
  );
}

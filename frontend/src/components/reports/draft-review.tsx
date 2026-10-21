"use client";

// A change before it is saved: what it does, every field it touches with the
// words it takes out struck through and the words it puts in highlighted (an
// amount before and after, each in its currency), and the choice to accept it
// or discard it. Nothing is saved until it is accepted.

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { acceptDraft, ApiError, type Draft, type FieldChange, type Report } from "@/lib/api";
import { diffWords } from "@/lib/diff";
import { full } from "@/lib/proposal";

const SHOWN = 30;
// Unchanged text longer than this is cut down to its ends.
const CONTEXT = 140;

function Shortened({ text }: { text: string }) {
  if (text.length <= CONTEXT * 2) return <>{text}</>;
  return (
    <>
      {text.slice(0, CONTEXT)}
      <span className="text-ink-3"> … </span>
      {text.slice(-CONTEXT)}
    </>
  );
}

function Value({ value, money, currency }: { value: string | number | null; money: boolean; currency: string }) {
  if (value === null) return <span className="text-ink-3">none</span>;
  if (typeof value === "number") return <>{money ? full(value, currency) : value.toLocaleString("en-US")}</>;
  return <>{value}</>;
}

function Change({ change, from, to }: { change: FieldChange; from: string; to: string }) {
  const { before, after } = change;
  const text = typeof before === "string" && typeof after === "string";
  return (
    <li className="py-3">
      <p className="text-xs font-medium text-ink-3">{change.label}</p>
      {text ? (
        <p className="mt-1 text-[13px] leading-relaxed whitespace-pre-wrap text-ink-2">
          {diffWords(before, after).map((piece, index) =>
            piece.kind === "same" ? (
              <Shortened key={index} text={piece.text} />
            ) : piece.kind === "removed" ? (
              <del key={index} className="rounded-sm bg-bad-soft px-0.5 text-bad decoration-bad/60">
                {piece.text}
              </del>
            ) : (
              <ins key={index} className="rounded-sm bg-good-soft px-0.5 text-good no-underline">
                {piece.text}
              </ins>
            ),
          )}
        </p>
      ) : (
        <p className="mt-1 flex flex-wrap items-baseline gap-2 text-[13px] tabular">
          <del className="text-ink-3">
            <Value value={before} money={change.money} currency={from} />
          </del>
          <span aria-hidden className="text-ink-3">
            →
          </span>
          <ins className="font-medium text-ink no-underline">
            <Value value={after} money={change.money} currency={to} />
          </ins>
        </p>
      )}
    </li>
  );
}

export function DraftReview({
  sessionId,
  draft,
  before,
  notes,
  onAccepted,
  onDiscard,
  onStale,
}: {
  sessionId: string;
  draft: Draft;
  // The report as it is saved, for the currency the old amounts are in.
  before: Report;
  notes?: React.ReactNode;
  onAccepted: (report: Report) => void;
  onDiscard: () => void;
  // The report changed since the draft was made.
  onStale: () => void;
}) {
  const [all, setAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const { changes } = draft;
  const shown = all ? changes : changes.slice(0, SHOWN);

  async function accept() {
    setSaving(true);
    setProblem(null);
    try {
      onAccepted(await acceptDraft(sessionId, draft));
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) onStale();
      else setProblem((error as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-label="The change, before it is saved" className="flex min-h-0 flex-col gap-4">
      <div className="rounded-lg border border-warn/40 bg-warn-soft px-3.5 py-3">
        <p className="kicker text-warn">Not saved yet</p>
        <p className="mt-1 text-sm font-medium text-ink">{draft.summary}</p>
        <p className="mt-1 text-xs text-ink-2">
          {changes.length ? `${changes.length} ${changes.length === 1 ? "change" : "changes"}, shown below and in the PDF.` : "Nothing would change."}
        </p>
      </div>
      {notes}
      {problem && <Notice tone="bad">{problem}</Notice>}
      <div className="flex gap-2">
        <Button variant="primary" onClick={accept} disabled={saving || !changes.length} className="flex-1">
          {saving ? "Saving…" : "Accept and save"}
        </Button>
        <Button onClick={onDiscard} disabled={saving}>
          Discard
        </Button>
      </div>
      {changes.length > 0 && (
        <ol aria-label="What changes" className="divide-y divide-rule border-y border-rule">
          {shown.map((change) => (
            <Change key={change.path} change={change} from={before.settings.currency} to={draft.report.settings.currency} />
          ))}
        </ol>
      )}
      {changes.length > SHOWN && !all && (
        <Button size="sm" onClick={() => setAll(true)}>
          Show all {changes.length} changes
        </Button>
      )}
    </section>
  );
}

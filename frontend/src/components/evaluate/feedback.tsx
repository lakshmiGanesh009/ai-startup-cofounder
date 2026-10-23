"use client";

// The founder's verdict on a strategy: useful or not, with a comment if they
// like, sent to Langfuse as a score on the run's trace (POST /feedback). Shown
// only for a run that was traced, that is when Langfuse is set up.

import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { inputClass } from "@/components/ui/field";
import { ThumbDownIcon, ThumbUpIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/notice";
import { Voice } from "@/components/voice";
import { type EvaluateResponse, sendFeedback } from "@/lib/api";

export function Feedback({ result }: { result: EvaluateResponse }) {
  const [useful, setUseful] = useState<boolean | null>(null);
  const [comment, setComment] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<boolean | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const heading = useId();
  const field = useId();

  if (!result.trace_id) return null;

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (useful === null) return;
    setSending(true);
    setProblem(null);
    try {
      const answer = await sendFeedback({ session_id: result.session_id, trace_id: result.trace_id, useful, comment: comment.trim() });
      setSent(answer.recorded);
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setSending(false);
    }
  }

  if (sent !== null) {
    return (
      <p role="status" className="mt-8 border-t border-rule pt-5 text-sm text-ink-2">
        {sent
          ? "Thank you. Your verdict is a score on this run in Langfuse, beside the team's own."
          : "Langfuse is not set up on the server any more, so your verdict was not kept."}
      </p>
    );
  }

  const choice = (value: boolean) =>
    `flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors ${
      useful === value ? "border-ink-3 bg-sunken font-medium text-ink" : "border-rule text-ink-2 hover:border-rule-strong hover:text-ink"
    }`;

  return (
    <form aria-labelledby={heading} onSubmit={send} className="mt-8 border-t border-rule pt-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p id={heading} className="text-sm text-ink-2">
          Was this strategy useful?
        </p>
        <div className="flex gap-2">
          <button type="button" aria-pressed={useful === true} onClick={() => setUseful(true)} className={choice(true)}>
            <ThumbUpIcon />
            Useful
          </button>
          <button type="button" aria-pressed={useful === false} onClick={() => setUseful(false)} className={choice(false)}>
            <ThumbDownIcon />
            Not useful
          </button>
        </div>
      </div>
      {useful !== null && (
        <div className="mt-4 max-w-xl">
          <label htmlFor={field} className="text-sm text-ink-2">
            {useful ? "What made it useful?" : "What would have made it useful?"} <span className="text-ink-3">(optional)</span>
          </label>
          <Voice label="your comment" multiline className="mt-1.5">
            <textarea
              id={field}
              rows={2}
              value={comment}
              maxLength={4000}
              onChange={(event) => setComment(event.target.value)}
              className={inputClass}
            />
          </Voice>
          <div className="mt-2 flex items-center gap-3">
            <Button type="submit" size="sm" variant="primary" disabled={sending}>
              {sending ? "Sending…" : "Send"}
            </Button>
            <span className="text-xs text-ink-3">Sent to Langfuse as a score on this run, with the comment.</span>
          </div>
          {problem && (
            <Notice tone="bad" className="mt-3">
              {problem}
            </Notice>
          )}
        </div>
      )}
    </form>
  );
}

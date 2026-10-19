"use client";

// What the page shows while the team works: the request, a running clock, how
// long it should take, and what the team does meanwhile.

import { useEffect, useRef, useState } from "react";

import type { Reasoning } from "@/lib/api";
import { evaluationWait, formatSeconds } from "@/lib/team";

const STAGES = [
  "The Chief of Staff plans and delegates",
  "The specialists write their reports at the same time",
  "The Chief of Staff reviews them and sends weak ones back",
  "The specialists critique each other; conflicts are settled",
  "The Chief of Staff writes the launch strategy",
];

// A panel with a running clock for a request that takes minutes.
export function Progress({
  title,
  wait,
  detail,
  stages,
}: {
  title: string;
  wait: string;
  detail?: React.ReactNode;
  stages: string[];
}) {
  const [elapsed, setElapsed] = useState(0);
  // Kept across the effect's restarts, as when the page is hidden and shown
  // again on navigation, so the clock does not start over.
  const started = useRef<number | null>(null);

  useEffect(() => {
    started.current ??= Date.now();
    const timer = window.setInterval(() => setElapsed((Date.now() - (started.current ?? 0)) / 1000), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section
      aria-live="polite"
      aria-busy="true"
      className="rounded-lg border border-accent-soft bg-accent-soft/30 p-5 dark:border-accent/40 dark:bg-accent/10"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="size-5 animate-spin rounded-full border-2 border-accent border-t-transparent"
        />
        <p className="font-medium">{title}</p>
        <span className="ml-auto font-mono text-sm tabular-nums" aria-label="Elapsed time">
          {formatSeconds(elapsed)}
        </span>
      </div>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
        {wait} {detail}
      </p>
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-zinc-600 dark:text-zinc-400">
        {stages.map((stage) => (
          <li key={stage}>{stage}</li>
        ))}
      </ol>
    </section>
  );
}

export function Working({ prompt, reasoning }: { prompt: string; reasoning: Reasoning | null }) {
  return (
    <Progress
      title="The founding team is working."
      wait={evaluationWait(reasoning)}
      detail={
        <>
          Request: <q>{prompt}</q>
        </>
      }
      stages={STAGES}
    />
  );
}

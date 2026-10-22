"use client";

// A running clock, for work that takes a minute or more.

import { useEffect, useRef, useState } from "react";

import { formatSeconds } from "@/lib/team";

// The seconds since the work began: `since` (a time from Date.now()), or else
// since the clock first showed.
export function useElapsed(since?: number): number {
  const [elapsed, setElapsed] = useState(() => (since ? (Date.now() - since) / 1000 : 0));
  // Kept across the effect's restarts, as when the page is hidden and shown
  // again on navigation, so the clock does not start over.
  const started = useRef<number | null>(since ?? null);

  useEffect(() => {
    started.current ??= Date.now();
    const timer = window.setInterval(() => setElapsed((Date.now() - (started.current ?? 0)) / 1000), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return elapsed;
}

export function Clock({ className = "", since }: { className?: string; since?: number }) {
  const elapsed = useElapsed(since);
  return (
    <span className={`font-mono text-sm tabular text-ink-2 ${className}`} aria-label="Elapsed time">
      {formatSeconds(elapsed)}
    </span>
  );
}

// A panel for work whose steps the page cannot see: what happens, and the clock.
export function Progress({
  title,
  wait,
  stages,
}: {
  title: string;
  wait: string;
  stages: string[];
}) {
  return (
    <section aria-live="polite" aria-busy="true" className="rounded-lg border border-rule bg-surface px-5 py-4">
      <div className="flex items-center gap-3">
        <span aria-hidden className="working-dot size-2 rounded-full bg-primary" />
        <p className="text-sm font-medium">{title}</p>
        <Clock className="ml-auto" />
      </div>
      <p className="mt-1.5 text-sm text-ink-3">{wait}</p>
      <ol className="mt-3 space-y-1 border-t border-rule pt-3 text-sm text-ink-2">
        {stages.map((stage, index) => (
          <li key={stage} className="flex gap-3">
            <span className="w-3 text-xs text-ink-3 tabular">{index + 1}</span>
            <span>{stage}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

"use client";

// Whether the browser can reach the backend, which proves that
// NEXT_PUBLIC_API_URL and the backend's CORS_ORIGINS are set up.

import { API_URL } from "@/lib/api";
import { useBackend } from "@/lib/backend";

const HOST = API_URL.replace(/^https?:\/\//, "");

export function BackendStatus() {
  const { status, error } = useBackend();

  return (
    <section aria-live="polite" className="text-xs leading-relaxed">
      {status === "checking" && (
        <p className="flex items-center gap-2 text-ink-3">
          <span aria-hidden className="working-dot size-1.5 rounded-full bg-ink-3" />
          Connecting to {HOST}…
        </p>
      )}
      {status === "up" && (
        <p className="flex items-center gap-2 text-ink-2">
          <span aria-hidden className="size-1.5 rounded-full bg-good" />
          <span>
            API connected <span className="font-mono text-ink-3">{HOST}</span>
          </span>
        </p>
      )}
      {status === "down" && (
        <div className="text-bad">
          <p className="flex items-center gap-2 font-medium">
            <span aria-hidden className="size-1.5 rounded-full bg-bad" />
            Can&apos;t reach {HOST}
          </p>
          <p className="mt-1 text-ink-3">
            {error} Start it with <code className="font-mono">uv run python main.py</code>, and check its CORS_ORIGINS
            includes this page&apos;s origin.
          </p>
        </div>
      )}
    </section>
  );
}

"use client";

// Whether the browser can reach the API through this app's server, which
// proves that BACKEND_URL and API_KEY are set up on that server.

import { useBackend } from "@/lib/backend";

export function BackendStatus() {
  const { status, error } = useBackend();

  return (
    <section aria-live="polite" className="text-xs leading-relaxed">
      {status === "checking" && (
        <p className="flex items-center gap-2 text-ink-3">
          <span aria-hidden className="working-dot size-1.5 rounded-full bg-ink-3" />
          Connecting to the API…
        </p>
      )}
      {status === "up" && (
        <p className="flex items-center gap-2 text-ink-2">
          <span aria-hidden className="size-1.5 rounded-full bg-good" />
          <span>API connected</span>
        </p>
      )}
      {status === "down" && (
        <div className="text-bad">
          <p className="flex items-center gap-2 font-medium">
            <span aria-hidden className="size-1.5 rounded-full bg-bad" />
            Can&apos;t reach the API
          </p>
          <p className="mt-1 text-ink-3">
            {error} Start it with <code className="font-mono">uv run python main.py</code>, and check BACKEND_URL and
            API_KEY in this app&apos;s .env.local.
          </p>
        </div>
      )}
    </section>
  );
}

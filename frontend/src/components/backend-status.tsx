"use client";

// Whether the browser can reach the backend, which proves that
// NEXT_PUBLIC_API_URL and the backend's CORS_ORIGINS are set up.

import { API_URL } from "@/lib/api";
import { useBackend } from "@/lib/backend";

export function BackendStatus() {
  const { status, error } = useBackend();

  return (
    <section aria-live="polite" className="text-sm">
      <h2 className="mb-1 font-semibold">Backend</h2>
      {status === "checking" && <p className="text-zinc-500">Checking {API_URL}…</p>}
      {status === "up" && (
        <p className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
          <span aria-hidden className="size-2 rounded-full bg-emerald-500" />
          Connected to {API_URL}
        </p>
      )}
      {status === "down" && (
        <p className="text-red-700 dark:text-red-400">
          Can&apos;t reach {API_URL} ({error}). Start it with <code>uv run python main.py</code>, and
          check that its CORS_ORIGINS includes this page&apos;s origin.
        </p>
      )}
    </section>
  );
}

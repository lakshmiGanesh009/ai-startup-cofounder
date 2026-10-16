"use client";

import { useEffect, useState } from "react";

import { API_URL, getHealth } from "@/lib/api";

type Status =
  | { state: "checking" }
  | { state: "up"; service: string }
  | { state: "down"; error: string };

// Shows whether the browser can reach the backend, which proves that
// NEXT_PUBLIC_API_URL and the backend's CORS_ORIGINS are set up.
export function BackendStatus() {
  const [status, setStatus] = useState<Status>({ state: "checking" });

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((health) => {
        if (!cancelled) setStatus({ state: "up", service: health.service });
      })
      .catch((error: Error) => {
        if (!cancelled) setStatus({ state: "down", error: error.message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section
      aria-live="polite"
      className="rounded-lg border border-zinc-200 p-4 text-sm dark:border-zinc-800"
    >
      <h2 className="mb-1 font-medium">Backend</h2>
      {status.state === "checking" && <p>Checking {API_URL} …</p>}
      {status.state === "up" && (
        <p className="text-emerald-700 dark:text-emerald-400">
          Connected to {status.service} at {API_URL}.
        </p>
      )}
      {status.state === "down" && (
        <p className="text-red-700 dark:text-red-400">
          Can&apos;t reach {API_URL} ({status.error}). Start it with{" "}
          <code>uv run python main.py</code>, and check that its CORS_ORIGINS includes this
          page&apos;s origin.
        </p>
      )}
    </section>
  );
}

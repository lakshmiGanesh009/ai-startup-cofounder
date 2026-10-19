"use client";

// The first request in a session: an idea, optional context, or a scenario to
// start from.

import { useState } from "react";

import type { RequestContext, Scenario } from "@/lib/api";

const FIELDS = [
  ["target_market", "Target market"],
  ["constraints", "Constraints (budget, timeline)"],
  ["competitive_landscape", "Competitive landscape"],
] as const;

type Field = (typeof FIELDS)[number][0];

export function scenarioTitle(name: string): string {
  const words = name.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function RequestForm({
  scenarios,
  busy,
  onSubmit,
  onScenario,
}: {
  scenarios: Scenario[];
  busy: boolean;
  onSubmit: (prompt: string, context: RequestContext) => void;
  onScenario: (scenario: Scenario | null) => void;
}) {
  const [scenario, setScenario] = useState("");
  const [prompt, setPrompt] = useState("");
  const [context, setContext] = useState<Record<Field, string>>({
    target_market: "",
    constraints: "",
    competitive_landscape: "",
  });
  const [warning, setWarning] = useState<string | null>(null);

  function choose(name: string) {
    setScenario(name);
    const chosen = scenarios.find((item) => item.name === name) ?? null;
    onScenario(chosen);
    if (!chosen) return;
    setPrompt(chosen.prompt);
    setContext({
      target_market: chosen.context?.target_market ?? "",
      constraints: chosen.context?.constraints ?? "",
      competitive_landscape: chosen.context?.competitive_landscape ?? "",
    });
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!prompt.trim()) {
      setWarning("Describe the idea or what you want the team to do.");
      return;
    }
    setWarning(null);
    const filled = Object.fromEntries(
      Object.entries(context)
        .map(([key, value]) => [key, value.trim()])
        .filter(([, value]) => value),
    );
    onSubmit(prompt.trim(), filled);
  }

  const input =
    "w-full rounded-md border border-zinc-300 bg-surface px-3 py-2 text-sm shadow-xs focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none dark:border-zinc-700";

  return (
    <form onSubmit={submit} className="space-y-5" aria-label="New request">
      <div>
        <label htmlFor="scenario" className="mb-1 block text-sm font-medium">
          Start from a scenario
        </label>
        <select id="scenario" value={scenario} onChange={(event) => choose(event.target.value)} className={input}>
          <option value="">(none)</option>
          {scenarios.map((item) => (
            <option key={item.name} value={item.name}>
              {scenarioTitle(item.name)}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="prompt" className="mb-1 block text-sm font-medium">
          Startup idea or request
        </label>
        <textarea
          id="prompt"
          rows={4}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Evaluate this startup idea: an assistant that drafts and schedules patient follow-ups…"
          className={input}
        />
      </div>
      <details className="rounded-md border border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <summary className="cursor-pointer text-sm font-medium">Context (optional)</summary>
        <div className="mt-3 space-y-3">
          {FIELDS.map(([field, label]) => (
            <div key={field}>
              <label htmlFor={field} className="mb-1 block text-sm">
                {label}
              </label>
              <input
                id={field}
                value={context[field]}
                onChange={(event) => setContext((current) => ({ ...current, [field]: event.target.value }))}
                className={input}
              />
            </div>
          ))}
        </div>
      </details>
      {warning && (
        <p role="alert" className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {warning}
        </p>
      )}
      <button
        type="submit"
        disabled={busy}
        className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"
      >
        Evaluate
      </button>
    </form>
  );
}

"use client";

// The first request of a session: the brief, optional context, or an example
// to start from.

import { useState } from "react";

import { Button, Kbd } from "@/components/ui/button";
import { inputClass, Label } from "@/components/ui/field";
import { CheckIcon } from "@/components/ui/icons";
import type { RequestContext, Scenario } from "@/lib/api";

const FIELDS = [
  ["target_market", "Target market", "Who buys, and where"],
  ["constraints", "Constraints", "Budget, team, timeline"],
  ["competitive_landscape", "Competition", "What they use today"],
] as const;

type Field = (typeof FIELDS)[number][0];
const EMPTY: Record<Field, string> = { target_market: "", constraints: "", competitive_landscape: "" };

export function Composer({
  scenarios,
  wait,
  busy,
  onSubmit,
  onScenario,
}: {
  scenarios: Scenario[];
  wait: string;
  busy: boolean;
  onSubmit: (prompt: string, context: RequestContext) => void;
  onScenario: (scenario: Scenario) => void;
}) {
  const [chosen, setChosen] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [context, setContext] = useState(EMPTY);
  const [problem, setProblem] = useState<string | null>(null);

  function start(scenario: Scenario) {
    setChosen(scenario.name);
    setPrompt(scenario.prompt);
    setContext({
      target_market: scenario.context?.target_market ?? "",
      constraints: scenario.context?.constraints ?? "",
      competitive_landscape: scenario.context?.competitive_landscape ?? "",
    });
    setProblem(null);
    onScenario(scenario);
  }

  function submit(event?: React.FormEvent) {
    event?.preventDefault();
    if (busy) return;
    if (!prompt.trim()) {
      setProblem("Describe the idea, or the decision you want the team to make.");
      return;
    }
    setProblem(null);
    const filled = Object.fromEntries(
      Object.entries(context)
        .map(([key, value]) => [key, value.trim()])
        .filter(([, value]) => value),
    );
    onSubmit(prompt.trim(), filled);
  }

  return (
    <form aria-label="New request" onSubmit={submit}>
      <Label htmlFor="brief">The brief</Label>
      <textarea
        id="brief"
        rows={5}
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") submit();
        }}
        placeholder="An assistant that drafts and schedules patient follow-ups from clinical notes, for small clinics. Is it worth building, and how should we launch it?"
        aria-invalid={Boolean(problem)}
        aria-describedby={problem ? "brief-problem" : undefined}
        className="block w-full resize-y rounded-lg border border-rule-strong bg-surface px-4 py-3.5 font-serif text-[1.125rem] leading-relaxed text-ink placeholder:text-ink-3 focus:border-focus focus:ring-3 focus:ring-focus/20 focus:outline-none"
      />
      {problem && (
        <p id="brief-problem" role="alert" className="mt-2 text-sm text-bad">
          {problem}
        </p>
      )}

      <fieldset className="mt-7">
        <legend className="kicker">
          Context <span className="tracking-normal normal-case">· optional</span>
        </legend>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {FIELDS.map(([field, label, hint]) => (
            <div key={field}>
              <Label htmlFor={field}>{label}</Label>
              <input
                id={field}
                value={context[field]}
                placeholder={hint}
                onChange={(event) => setContext((current) => ({ ...current, [field]: event.target.value }))}
                className={inputClass}
              />
            </div>
          ))}
        </div>
      </fieldset>

      <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Button type="submit" variant="primary" disabled={busy}>
          Evaluate
          <Kbd>⌘↵</Kbd>
        </Button>
        <p className="text-sm text-ink-3">{wait}</p>
      </div>

      {scenarios.length > 0 && (
        <section aria-labelledby="examples-heading" className="mt-14">
          <h2 id="examples-heading" className="kicker">
            Or start from an example
          </h2>
          <ul className="mt-3 divide-y divide-rule border-y border-rule">
            {scenarios.map((scenario, index) => {
              const picked = chosen === scenario.name;
              return (
                <li key={scenario.name}>
                  <button
                    type="button"
                    aria-pressed={picked}
                    onClick={() => start(scenario)}
                    className="group flex w-full items-start gap-4 py-3.5 text-left"
                  >
                    <span className="mt-0.5 w-5 text-xs text-ink-3 tabular">
                      {picked ? <CheckIcon className="size-4 text-primary" /> : String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-ink underline-offset-4 group-hover:underline">
                        {scenario.title}
                      </span>
                      <span className="mt-0.5 block truncate text-sm text-ink-3">{scenario.prompt}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </form>
  );
}

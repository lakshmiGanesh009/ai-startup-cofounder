"use client";

// The first request of a session: a brief written freely or filled into a
// decision template, optional context, or a worked example to start from; and
// whether the Chief of Staff researches it and checks it before the team runs.

import { useRef, useState } from "react";

import { Button, Kbd } from "@/components/ui/button";
import { inputClass, Label } from "@/components/ui/field";
import { CheckIcon } from "@/components/ui/icons";
import { PROVIDER_NAMES, type RequestContext, type ResearchProvider, type Scenario, type Template } from "@/lib/api";
import { fillTemplate, missingField, type TemplateValues } from "@/lib/brief";
import { DEEP_RESEARCH_COST } from "@/lib/team";

const FIELDS = [
  ["target_market", "Target market", "Who buys, and where"],
  ["constraints", "Constraints", "Budget, team, timeline"],
  ["competitive_landscape", "Competition", "What they use today"],
] as const;

type Field = (typeof FIELDS)[number][0];
const EMPTY: Record<Field, string> = { target_market: "", constraints: "", competitive_landscape: "" };

const BRIEF_CLASS =
  "block w-full resize-y rounded-lg border border-rule-strong bg-surface px-4 py-3.5 font-serif text-[1.125rem] leading-relaxed text-ink placeholder:text-ink-3 focus:border-focus focus:ring-3 focus:ring-focus/20 focus:outline-none";

export type Submission = {
  prompt: string;
  context: RequestContext;
  template: string | null;
  // Check the brief with the Chief of Staff first; research each specialist's area on the web.
  prepare: boolean;
  deep: boolean;
};

function Choice({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
        pressed ? "border-primary bg-primary-soft font-medium text-ink" : "border-rule-strong text-ink-2 hover:border-ink-3 hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

export function Composer({
  scenarios,
  templates,
  research,
  waits,
  busy,
  onSubmit,
  onScenario,
}: {
  scenarios: Scenario[];
  templates: Template[];
  // Where web research runs (the sidebar's choice): null when no provider is
  // set up, undefined until the backend has answered.
  research: ResearchProvider | null | undefined;
  // How long the next step takes: checking the brief, or running the team.
  waits: { prepare: string; evaluate: string };
  busy: boolean;
  onSubmit: (submission: Submission) => void;
  onScenario: (scenario: Scenario) => void;
}) {
  const [chosen, setChosen] = useState<string | null>(null);
  const [templateName, setTemplateName] = useState<string | null>(null);
  const [values, setValues] = useState<TemplateValues>({});
  const [prompt, setPrompt] = useState("");
  const [context, setContext] = useState(EMPTY);
  const [prepare, setPrepare] = useState(true);
  const [deep, setDeep] = useState(false);
  const [problem, setProblem] = useState<{ field: string; text: string } | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const template = templates.find((each) => each.name === templateName) ?? null;

  function start(scenario: Scenario) {
    setChosen(scenario.name);
    setTemplateName(null);
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
    let brief = prompt.trim();
    if (template) {
      const missing = missingField(template, values);
      if (missing) {
        setProblem({ field: `field-${missing.key}`, text: `Fill in ${missing.label.toLowerCase()} first.` });
        form.current?.querySelector<HTMLElement>(`#field-${missing.key}`)?.focus();
        return;
      }
      brief = fillTemplate(template, values);
    } else if (!brief) {
      setProblem({ field: "brief", text: "Describe the idea, or the decision you want the team to make." });
      return;
    }
    setProblem(null);
    const filled = Object.fromEntries(
      Object.entries(context)
        .map(([key, value]) => [key, value.trim()])
        .filter(([, value]) => value),
    );
    onSubmit({ prompt: brief, context: filled, template: template?.name ?? null, prepare, deep: deep && research !== null });
  }

  const sendOnShortcut = (event: React.KeyboardEvent) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") submit();
  };
  const invalid = (field: string) => problem?.field === field;
  const message = (field: string) =>
    invalid(field) && (
      <p id={`${field}-problem`} role="alert" className="mt-2 text-sm text-bad">
        {problem?.text}
      </p>
    );

  return (
    <form ref={form} aria-label="New request" onSubmit={submit}>
      {templates.length > 0 && (
        <div className="mb-7">
          <p id="kind-heading" className="kicker">
            What do you need decided?
          </p>
          <div role="group" aria-labelledby="kind-heading" className="mt-3 flex flex-wrap gap-2">
            <Choice pressed={!template} onClick={() => setTemplateName(null)}>
              Your own brief
            </Choice>
            {templates.map((each) => (
              <Choice
                key={each.name}
                pressed={templateName === each.name}
                onClick={() => {
                  setTemplateName(each.name);
                  setChosen(null);
                  setProblem(null);
                }}
              >
                {each.title}
              </Choice>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-xl border border-rule bg-surface p-5 shadow-[0_1px_2px_rgb(0_0_0/0.04),0_10px_30px_-18px_rgb(0_0_0/0.18)] sm:p-7">
      {template ? (
        <section aria-label={template.title} className="space-y-5">
          <p className="text-[15px] text-ink-2">{template.summary}</p>
          {template.fields.map((field) => {
            const id = `field-${field.key}`;
            const shared = {
              id,
              value: values[field.key] ?? "",
              placeholder: field.placeholder,
              onKeyDown: sendOnShortcut,
              "aria-invalid": invalid(id),
              "aria-describedby": invalid(id) ? `${id}-problem` : undefined,
              onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
                setValues((current) => ({ ...current, [field.key]: event.target.value })),
            };
            return (
              <div key={field.key}>
                <Label htmlFor={id}>{field.label}</Label>
                {field.long ? <textarea rows={3} className={BRIEF_CLASS} {...shared} /> : <input className={inputClass} {...shared} />}
                {message(id)}
              </div>
            );
          })}
          <p className="text-sm text-ink-3">
            <span className="text-ink-2">The brief reads:</span>{" "}
            <span className="font-serif text-[15px]">{fillTemplate(template, values)}</span>
          </p>
        </section>
      ) : (
        <div>
          <Label htmlFor="brief">The brief</Label>
          <textarea
            id="brief"
            rows={5}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={sendOnShortcut}
            placeholder="An assistant that drafts and schedules patient follow-ups from clinical notes, for small clinics. Is it worth building, and how should we launch it?"
            aria-invalid={invalid("brief")}
            aria-describedby={invalid("brief") ? "brief-problem" : undefined}
            className={BRIEF_CLASS}
          />
          {message("brief")}
        </div>
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

      <label className="mt-7 flex cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          checked={prepare}
          onChange={(event) => setPrepare(event.target.checked)}
          className="mt-1 size-4 accent-[var(--primary)]"
        />
        <span>
          <span className="block text-sm font-medium text-ink">Research it and check the brief first</span>
          <span className="mt-0.5 block text-sm text-ink-3">
            {research === null
              ? "Web research is off: the server has neither Azure OpenAI nor a TAVILY_API_KEY set up. The Chief of Staff still checks the brief for anything missing."
              : `The Chief of Staff looks up the market on the web with ${PROVIDER_NAMES[research ?? "azure"]}, and asks anything it needs to know. You review both before the team starts.`}
          </span>
        </span>
      </label>

      <label
        className={`mt-4 flex items-start gap-3 ${research === null ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
      >
        <input
          type="checkbox"
          checked={deep && research !== null}
          disabled={research === null}
          onChange={(event) => setDeep(event.target.checked)}
          className="mt-1 size-4 accent-[var(--primary)]"
        />
        <span>
          <span className="block text-sm font-medium text-ink">Deep research for each specialist</span>
          <span className="mt-0.5 block text-sm text-ink-3">
            {research === null
              ? "Needs Azure OpenAI or a TAVILY_API_KEY on the server."
              : `${PROVIDER_NAMES[research ?? "azure"]} researches each specialist's area and profiles up to three competitors before the team starts. ${DEEP_RESEARCH_COST[research ?? "azure"]} Choose where research runs in the sidebar.`}
          </span>
        </span>
      </label>

      <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Button type="submit" variant="primary" disabled={busy}>
          {prepare ? "Check the brief" : "Evaluate"}
          <Kbd>⌘↵</Kbd>
        </Button>
        <p className="text-sm text-ink-3">{prepare ? waits.prepare : waits.evaluate}</p>
      </div>
      </div>

      {scenarios.length > 0 && (
        <section aria-labelledby="examples-heading" className="mt-14">
          <h2 id="examples-heading" className="kicker">
            Or start from an example
          </h2>
          <ul className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {scenarios.map((scenario, index) => {
              const picked = chosen === scenario.name;
              return (
                <li key={scenario.name} className="flex">
                  <button
                    type="button"
                    aria-pressed={picked}
                    onClick={() => start(scenario)}
                    className={`group flex w-full items-start gap-3 rounded-lg border px-4 py-3.5 text-left transition-[border-color,box-shadow,background-color] ${
                      picked
                        ? "border-primary bg-primary-soft"
                        : "border-rule bg-surface hover:border-rule-strong hover:shadow-[0_6px_18px_-12px_rgb(0_0_0/0.25)]"
                    }`}
                  >
                    <span
                      className={`mt-px flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] tabular ${
                        picked ? "bg-primary text-primary-ink" : "bg-sunken text-ink-3"
                      }`}
                    >
                      {picked ? <CheckIcon className="size-3.5" /> : String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-ink">{scenario.title}</span>
                      <span className="mt-1 line-clamp-2 block text-[13px] leading-snug text-ink-3">{scenario.prompt}</span>
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

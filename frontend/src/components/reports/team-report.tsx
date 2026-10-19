"use client";

// The team's report: the strategy, each specialist's report and the decisions
// on conflicts, read as text, or edited as markdown and saved together.

import { useState } from "react";

import { Markdown } from "@/components/markdown";
import { Badge } from "@/components/ui/badge";
import type { ReportSection } from "@/lib/api";
import { SECTION_AGENTS } from "@/lib/proposal";

export function TeamReport({
  sections,
  onSave,
}: {
  sections: ReportSection[];
  onSave: (sections: ReportSection[]) => Promise<string | null>;
}) {
  const [draft, setDraft] = useState<ReportSection[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  if (!draft) {
    return (
      <div className="space-y-8">
        <button
          type="button"
          onClick={() => setDraft(sections.map((section) => ({ ...section })))}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          Edit the team&apos;s report
        </button>
        {sections.map((section) => (
          <section key={section.key} aria-label={section.title}>
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <h3 className="text-lg font-semibold">{section.title}</h3>
              <Badge>{SECTION_AGENTS[section.key] ?? "Edited by the founder"}</Badge>
            </div>
            <Markdown>{section.body}</Markdown>
          </section>
        ))}
      </div>
    );
  }

  return (
    <form
      aria-label="Edit the team's report"
      className="space-y-5"
      onSubmit={async (event) => {
        event.preventDefault();
        setSaving(true);
        const failure = await onSave(draft);
        setSaving(false);
        setProblem(failure);
        if (!failure) setDraft(null);
      }}
    >
      <p className="text-sm text-zinc-500">Sections are markdown.</p>
      {draft.map((section, index) => (
        <div key={section.key}>
          <label htmlFor={`section-${section.key}`} className="mb-1 block text-sm font-medium">
            {section.title}
          </label>
          <textarea
            id={`section-${section.key}`}
            rows={Math.min(24, Math.max(6, section.body.split("\n").length + 2))}
            value={section.body}
            onChange={(event) =>
              setDraft(draft.map((item, i) => (i === index ? { ...item, body: event.target.value } : item)))
            }
            className="w-full rounded-md border border-zinc-300 bg-surface px-3 py-2 font-mono text-sm focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none dark:border-zinc-700"
          />
        </div>
      ))}
      {problem && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {problem}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50">
          {saving ? "Saving…" : "Save changes"}
        </button>
        <button
          type="button"
          onClick={() => {
            setDraft(null);
            setProblem(null);
          }}
          className="rounded-md border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

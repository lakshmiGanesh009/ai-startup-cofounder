"use client";

// The team's report: the strategy, each specialist's report and the decisions
// on conflicts, read as a document, or edited as markdown and saved together.

import { useState } from "react";

import { Markdown } from "@/components/markdown";
import { AgentAvatar } from "@/components/ui/agent";
import { Button } from "@/components/ui/button";
import { inputClass } from "@/components/ui/field";
import { PencilIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/notice";
import type { ReportSection } from "@/lib/api";
import { SECTION_AGENT } from "@/lib/agents";
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
      <div>
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setDraft(sections.map((section) => ({ ...section })))}>
            <PencilIcon className="size-3.5" />
            Edit the team&apos;s report
          </Button>
        </div>
        <div className="mt-4 space-y-14">
          {sections.map((section) => (
            <section key={section.key} aria-label={section.title}>
              <div className="mb-5 flex items-center gap-3 border-b border-rule pb-3">
                {SECTION_AGENT[section.key] && <AgentAvatar agent={SECTION_AGENT[section.key]} size="md" />}
                <div>
                  <h3 className="font-serif text-[1.5rem] leading-snug font-medium">{section.title}</h3>
                  <p className="mt-0.5 text-xs text-ink-3">{SECTION_AGENTS[section.key] ?? "Edited by you"}</p>
                </div>
              </div>
              <Markdown labels={4}>{section.body}</Markdown>
            </section>
          ))}
        </div>
      </div>
    );
  }

  return (
    <form
      aria-label="Edit the team's report"
      className="space-y-7"
      onSubmit={async (event) => {
        event.preventDefault();
        setSaving(true);
        const failure = await onSave(draft);
        setSaving(false);
        setProblem(failure);
        if (!failure) setDraft(null);
      }}
    >
      <p className="text-sm text-ink-3">Each section is markdown: # for headings, - for lists, **bold**.</p>
      {draft.map((section, index) => (
        <div key={section.key}>
          <label htmlFor={`section-${section.key}`} className="mb-1.5 block text-[13px] font-medium text-ink">
            {section.title}
          </label>
          <textarea
            id={`section-${section.key}`}
            rows={Math.min(24, Math.max(6, section.body.split("\n").length + 2))}
            value={section.body}
            onChange={(event) =>
              setDraft(draft.map((item, i) => (i === index ? { ...item, body: event.target.value } : item)))
            }
            className={`${inputClass} font-mono text-[13px] leading-relaxed`}
          />
        </div>
      ))}
      {problem && <Notice tone="bad">{problem}</Notice>}
      <div className="sticky bottom-0 flex gap-2 border-t border-rule bg-paper/95 py-3 backdrop-blur">
        <Button type="submit" variant="primary" disabled={saving}>
          {saving ? "Saving…" : "Save changes"}
        </Button>
        <Button
          onClick={() => {
            setDraft(null);
            setProblem(null);
          }}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}

"use client";

// The founder's hand on one paragraph or list item of the report: ask its
// writer to revise just that, or take it out. The page that shows the report
// says what to do with the request (PassageContext); the change then comes
// back as a draft to accept or discard, like any other.

import { createContext, useContext, useState } from "react";

import { PencilIcon, TrashIcon } from "@/components/ui/icons";

export type PassageAction = { path: string; passage: string } & (
  | { kind: "remove" }
  | { kind: "revise"; instruction: string }
);

// Resolves once the request is handled (true) or refused (false).
export const PassageContext = createContext<((action: PassageAction) => Promise<boolean>) | null>(null);

export function usePassages() {
  return useContext(PassageContext);
}

// A block of the report with its tools; `Tag` is the element it renders as.
export function Passage({
  Tag,
  path,
  passage,
  children,
  ...props
}: {
  Tag: "p" | "li";
  path: string;
  passage: string;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  const act = usePassages();
  const [asking, setAsking] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(action: PassageAction) {
    if (!act) return;
    setBusy(true);
    const done = await act(action);
    setBusy(false);
    if (done) {
      setAsking(false);
      setInstruction("");
    }
  }

  return (
    <Tag {...props} className="group/passage relative">
      {children}
      <span className="ml-1.5 inline-flex translate-y-[-1px] gap-0.5 align-middle font-sans opacity-0 transition-opacity group-hover/passage:opacity-100 group-focus-within/passage:opacity-100 max-lg:opacity-70">
        <button
          type="button"
          title="Revise this passage"
          aria-label="Revise this passage"
          onClick={() => setAsking((open) => !open)}
          className="rounded p-1 text-ink-3 hover:bg-sunken hover:text-ink"
        >
          <PencilIcon className="size-3.5" />
        </button>
        <button
          type="button"
          title="Remove this passage"
          aria-label="Remove this passage"
          disabled={busy}
          onClick={() => run({ kind: "remove", path, passage })}
          className="rounded p-1 text-ink-3 hover:bg-bad-soft hover:text-bad"
        >
          <TrashIcon className="size-3.5" />
        </button>
      </span>
      {asking && (
        <span className="mt-2 flex flex-col gap-2 rounded-lg border border-rule bg-surface p-2.5 font-sans text-sm sm:flex-row">
          <input
            autoFocus
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && instruction.trim()) run({ kind: "revise", path, passage, instruction: instruction.trim() });
              if (event.key === "Escape") setAsking(false);
            }}
            placeholder="What to change in this passage"
            aria-label="What to change in this passage"
            className="min-w-0 flex-1 rounded-md border border-rule-strong bg-paper px-2.5 py-1.5 text-sm text-ink placeholder:text-ink-3 focus:border-focus focus:outline-none"
          />
          <button
            type="button"
            disabled={busy || !instruction.trim()}
            onClick={() => run({ kind: "revise", path, passage, instruction: instruction.trim() })}
            className="rounded-md bg-primary px-3 py-1.5 text-[13px] font-medium text-primary-ink disabled:opacity-45"
          >
            {busy ? "Revising…" : "Revise"}
          </button>
        </span>
      )}
    </Tag>
  );
}

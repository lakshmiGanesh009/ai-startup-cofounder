// The web research a brief was prepared with: facts that cite their sources by
// number, and the sources themselves as links. Before the team runs, each fact
// can be left out.

import { CloseIcon, UndoIcon } from "@/components/ui/icons";
import type { Research, Source } from "@/lib/api";
import { domain } from "@/lib/brief";

function Citations({ numbers, prefix }: { numbers: number[]; prefix: string }) {
  return (
    <span className="ml-1 whitespace-nowrap">
      {numbers.map((n) => (
        <a
          key={n}
          href={`#${prefix}-source-${n}`}
          aria-label={`Source ${n}`}
          className="ml-0.5 align-super font-sans text-[10px] font-medium text-link no-underline hover:underline"
        >
          [{n}]
        </a>
      ))}
    </span>
  );
}

export function ResearchFindings({
  research,
  prefix,
  leftOut,
  onToggle,
}: {
  research: Research;
  prefix: string;
  // Before the team runs: which facts the founder left out, and how to change that.
  leftOut?: ReadonlySet<number>;
  onToggle?: (index: number) => void;
}) {
  return (
    <ul className="divide-y divide-rule border-y border-rule">
      {research.findings.map((finding, index) => {
        const out = leftOut?.has(index) ?? false;
        return (
          <li key={index} className="flex items-start gap-4 py-3">
            <p className={`min-w-0 flex-1 font-serif text-[16px] leading-relaxed ${out ? "text-ink-3 line-through" : "text-ink"}`}>
              {finding.point}
              <Citations numbers={finding.sources} prefix={prefix} />
            </p>
            {onToggle && (
              <button
                type="button"
                onClick={() => onToggle(index)}
                aria-label={`${out ? "Put back" : "Leave out"}: ${finding.point}`}
                title={out ? "Put back" : "Leave out"}
                className="mt-0.5 shrink-0 rounded-md p-1 text-ink-3 hover:bg-sunken hover:text-ink"
              >
                {out ? <UndoIcon className="size-3.5" /> : <CloseIcon className="size-3.5" />}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function ResearchSources({ sources, prefix }: { sources: Source[]; prefix: string }) {
  return (
    <ol className="space-y-1.5 text-sm">
      {sources.map((source, index) => (
        <li key={source.url} id={`${prefix}-source-${index + 1}`} className="flex gap-2.5 scroll-mt-24">
          <span className="w-5 shrink-0 text-right text-xs text-ink-3 tabular">{index + 1}</span>
          <span className="min-w-0">
            <a href={source.url} target="_blank" rel="noreferrer" className="text-link underline-offset-2 hover:underline">
              {source.title}
            </a>{" "}
            <span className="text-xs text-ink-3">{domain(source.url)}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

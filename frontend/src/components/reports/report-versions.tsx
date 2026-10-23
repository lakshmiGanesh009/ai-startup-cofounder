"use client";

// A report's versions, for the report picker's preview, newest first: each
// with what made it, when, and how many fields it changed in which parts of
// the report; opened, what changed field by field from the version before it,
// each word taken out struck through and each put in highlighted, and each
// amount before and after, as a draft shows it before it is saved.

import { useEffect, useId, useState } from "react";

import { Change } from "@/components/reports/draft-review";
import { Badge } from "@/components/ui/badge";
import { ChevronDownIcon } from "@/components/ui/icons";
import { listVersions, versionChanges, type VersionChanges, type VersionSummary } from "@/lib/api";
import { stamp } from "@/lib/dates";

// Shown before "Show all": versions, the changes of one, and the parts of the report named beside it.
const VERSIONS = 4;
const CHANGES = 8;
const AREAS = 3;

// How much a version changed, or why there is nothing to compare it with.
function extent(version: VersionSummary): string | null {
  if (version.changed === undefined) return null;
  if (version.changed === null) return version.version === 1 ? "The first version" : "The version before it is no longer kept";
  if (version.changed === 0) return "Nothing changed";
  return `${version.changed.toLocaleString("en-US")} change${version.changed === 1 ? "" : "s"}`;
}

function ChangeList({ sessionId, version }: { sessionId: string; version: number }) {
  const [found, setFound] = useState<VersionChanges | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [all, setAll] = useState(false);

  useEffect(() => {
    let cancelled = false;
    versionChanges(sessionId, version)
      .then((changes) => !cancelled && setFound(changes))
      .catch((error: Error) => !cancelled && setProblem(error.message));
    return () => {
      cancelled = true;
    };
  }, [sessionId, version]);

  if (problem) return <p className="py-3 text-[13px] text-bad">{problem}</p>;
  if (!found) return <p className="py-3 text-[13px] text-ink-3">Loading what changed…</p>;
  const shown = all ? found.changes : found.changes.slice(0, CHANGES);
  return (
    <>
      <ol aria-label={`What changed in version ${version}`} className="divide-y divide-rule">
        {shown.map((change) => (
          <Change key={change.path} change={change} from={found.currency_before} to={found.currency} />
        ))}
      </ol>
      {found.changes.length > shown.length && (
        <button
          type="button"
          onClick={() => setAll(true)}
          className="mb-3 text-xs font-medium text-link underline-offset-2 hover:underline"
        >
          Show all {found.changes.length} changes
        </button>
      )}
    </>
  );
}

export function Versions({ sessionId, version }: { sessionId: string; version: number }) {
  const [versions, setVersions] = useState<VersionSummary[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [opened, setOpened] = useState<number[]>([]);
  const [all, setAll] = useState(false);
  const id = useId();

  // Loaded afresh when the report has a new version.
  useEffect(() => {
    let cancelled = false;
    listVersions(sessionId)
      .then((found) => !cancelled && setVersions(found))
      .catch((error: Error) => !cancelled && setProblem(error.message));
    return () => {
      cancelled = true;
    };
  }, [sessionId, version]);

  function toggle(number: number) {
    setOpened((now) => (now.includes(number) ? now.filter((open) => open !== number) : [...now, number]));
  }

  const shown = versions && (all ? versions : versions.slice(0, VERSIONS));
  return (
    <section aria-label="Versions">
      <p className="mb-3 flex flex-wrap items-baseline gap-x-2">
        <span className="kicker">Versions</span>
        <span className="text-xs text-ink-3">what each one changed, from the one before</span>
      </p>
      {problem ? (
        <p className="text-[13px] text-ink-3">The versions could not be loaded: {problem}</p>
      ) : !shown ? (
        <p className="text-[13px] text-ink-3">Loading the versions…</p>
      ) : (
        <>
          <ol>
            {shown.map((entry, index) => {
              const open = opened.includes(entry.version);
              const areas = entry.areas ?? [];
              const said = extent(entry);
              return (
                <li key={entry.version} className="relative pb-4 pl-7 last:pb-0">
                  {/* The line from this version down to the one before it. */}
                  {index < shown.length - 1 && <span aria-hidden className="absolute top-4 bottom-0 left-[5px] w-px bg-rule-strong" />}
                  <span
                    aria-hidden
                    className={`absolute top-[5px] left-0 size-[11px] rounded-full border-2 ${
                      entry.current ? "border-primary bg-primary" : "border-rule-strong bg-surface"
                    }`}
                  />
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                        <span className="font-mono text-xs text-ink-3">v{entry.version}</span>
                        <span className="font-medium text-ink">{entry.change ?? "Saved"}</span>
                        {entry.current && <Badge tone="primary">Current</Badge>}
                      </p>
                      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
                        <span className="tabular">{stamp(entry.updated_at)}</span>
                        {said && (
                          <>
                            <span aria-hidden>·</span>
                            <span>{said}</span>
                          </>
                        )}
                        {areas.slice(0, AREAS).map((area) => (
                          <span key={area} className="rounded bg-sunken px-1.5 py-px text-[11px] font-medium text-ink-2">
                            {area}
                          </span>
                        ))}
                        {areas.length > AREAS && <span>and {areas.length - AREAS} more</span>}
                      </p>
                    </div>
                    {(entry.changed ?? 0) > 0 && (
                      <button
                        type="button"
                        aria-expanded={open}
                        aria-controls={open ? `${id}-${entry.version}` : undefined}
                        aria-label={`What changed in version ${entry.version}`}
                        onClick={() => toggle(entry.version)}
                        className="inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-rule px-2 text-xs font-medium text-ink-2 transition-colors hover:border-rule-strong hover:text-ink"
                      >
                        What changed
                        <ChevronDownIcon className={`size-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
                      </button>
                    )}
                  </div>
                  {open && (
                    <div id={`${id}-${entry.version}`} className="mt-2.5 rounded-lg border border-rule bg-surface px-3.5">
                      <ChangeList sessionId={sessionId} version={entry.version} />
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
          {versions && versions.length > shown.length && (
            <button
              type="button"
              onClick={() => setAll(true)}
              className="mt-3 text-xs font-medium text-link underline-offset-2 hover:underline"
            >
              Show all {versions.length} versions
            </button>
          )}
        </>
      )}
    </section>
  );
}

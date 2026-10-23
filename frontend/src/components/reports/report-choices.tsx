"use client";

// What the founder chose and told the team while a report was built, for the
// report picker's preview: their brief and its details, their answers to the
// Chief of Staff's questions, the research facts they kept (with where each
// came from), their documents, and how the team was run. Every amount, share
// and span of time in their words is picked out.

import { useEffect, useState } from "react";

import { Figured } from "@/components/markdown";
import { AGENTS } from "@/lib/agents";
import { type Choices, PROVIDER_NAMES, reportChoices } from "@/lib/api";

// The brief shown before "Show the whole brief", and the facts before "Show all".
const BRIEF_CHARS = 420;
const FACTS = 4;

const DETAILS: [keyof Choices, string][] = [
  ["target_market", "Target market"],
  ["constraints", "Constraints"],
  ["competitive_landscape", "Competition"],
];

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function Part({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-3.5">
      <p className="mb-2 flex flex-wrap items-baseline gap-x-2">
        <span className="kicker">{title}</span>
        {note && <span className="text-xs text-ink-3">{note}</span>}
      </p>
      {children}
    </div>
  );
}

function Brief({ text }: { text: string }) {
  const [whole, setWhole] = useState(false);
  const long = text.length > BRIEF_CHARS;
  const shown = long && !whole ? `${text.slice(0, BRIEF_CHARS).replace(/\s+\S*$/, "")}…` : text;
  return (
    <>
      <p className="font-serif text-[15px] leading-relaxed whitespace-pre-wrap text-ink">
        <Figured text={shown} />
      </p>
      {long && (
        <button
          type="button"
          onClick={() => setWhole(!whole)}
          className="mt-1.5 text-xs font-medium text-link underline-offset-2 hover:underline"
        >
          {whole ? "Show less" : "Show the whole brief"}
        </button>
      )}
    </>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="rounded bg-sunken px-1.5 py-0.5 text-xs font-medium text-ink-2">{children}</span>;
}

export function YourChoices({ sessionId, version }: { sessionId: string; version: number }) {
  const [choices, setChoices] = useState<Choices | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [allFacts, setAllFacts] = useState(false);

  // Loaded afresh when the report has a new version: a follow-up changes them.
  useEffect(() => {
    let cancelled = false;
    reportChoices(sessionId)
      .then((found) => !cancelled && setChoices(found))
      .catch((error: Error) => !cancelled && setProblem(error.message));
    return () => {
      cancelled = true;
    };
  }, [sessionId, version]);

  const heading = (
    <p className="mb-3 flex flex-wrap items-baseline gap-x-2">
      <span className="kicker">Your choices</span>
      <span className="text-xs text-ink-3">what you chose and told the team while it was built</span>
    </p>
  );
  if (problem) {
    return (
      <section aria-label="Your choices">
        {heading}
        <p className="text-[13px] text-ink-3">Your choices could not be loaded: {problem}</p>
      </section>
    );
  }
  if (!choices) {
    return (
      <section aria-label="Your choices">
        {heading}
        <p className="text-[13px] text-ink-3">Loading your choices…</p>
      </section>
    );
  }

  const details = DETAILS.filter(([key]) => choices[key]);
  const findings = choices.research?.findings ?? [];
  const facts = allFacts ? findings : findings.slice(0, FACTS);
  const efforts = Object.entries(choices.efforts) as ["specialist" | "chief", string][];
  return (
    <section aria-label="Your choices">
      {heading}
      <div className="divide-y divide-rule rounded-lg border border-rule bg-surface">
        <Part title="Your brief">
          <Brief text={choices.brief} />
          {choices.follow_up && (
            <p className="mt-2.5 text-[13px] leading-relaxed text-ink-2">
              <span className="font-medium text-ink-3">Your follow-up: </span>
              <Figured text={choices.follow_up} />
            </p>
          )}
        </Part>

        {details.length > 0 && (
          <Part title="Its details">
            <dl className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
              {details.map(([key, label]) => (
                <div key={key} className="contents">
                  <dt className="text-ink-3">{label}</dt>
                  <dd className="text-ink">
                    <Figured text={String(choices[key])} />
                  </dd>
                </div>
              ))}
            </dl>
          </Part>
        )}

        {choices.answers.length > 0 && (
          <Part title="Your answers" note="to the Chief of Staff's questions">
            <ol className="space-y-2.5">
              {choices.answers.map((answer, index) => (
                <li key={index} className="text-sm">
                  <p className="text-[13px] text-ink-3">{answer.question}</p>
                  <p className="mt-0.5 text-ink">
                    <Figured text={answer.answer} />
                  </p>
                </li>
              ))}
            </ol>
          </Part>
        )}

        {findings.length > 0 && (
          <Part title="Facts you kept" note="from the web research before the team started">
            <ul className="space-y-2">
              {facts.map((finding, index) => (
                <li key={index} className="flex gap-2.5 text-sm leading-relaxed text-ink">
                  <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-rule-strong" />
                  <span className="min-w-0">
                    <Figured text={finding.point} />
                    {finding.sources.map((number) => {
                      const source = choices.research?.sources[number - 1];
                      return source ? (
                        <a
                          key={number}
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                          title={source.title}
                          className="ml-1.5 text-xs text-link underline-offset-2 hover:underline"
                        >
                          {host(source.url)}
                        </a>
                      ) : null;
                    })}
                  </span>
                </li>
              ))}
            </ul>
            {findings.length > facts.length && (
              <button
                type="button"
                onClick={() => setAllFacts(true)}
                className="mt-2 text-xs font-medium text-link underline-offset-2 hover:underline"
              >
                Show all {findings.length} facts
              </button>
            )}
          </Part>
        )}

        {choices.documents.length > 0 && (
          <Part title="Your documents">
            <ul className="space-y-1 text-sm text-ink">
              {choices.documents.map((document) => (
                <li key={document}>{document}</li>
              ))}
            </ul>
          </Part>
        )}

        {(choices.deep_research !== null || efforts.length > 0) && (
          <Part title="How the team ran">
            <p className="flex flex-wrap gap-1.5">
              {choices.deep_research !== null && (
                <Chip>
                  {choices.deep_research
                    ? `Deep research for each specialist${choices.research_provider ? ` · ${PROVIDER_NAMES[choices.research_provider]}` : ""}`
                    : "No deep research"}
                </Chip>
              )}
              {efforts.map(([role, effort]) => (
                <Chip key={role}>
                  {role === "chief" ? AGENTS.chief.name : "Specialists"} reasoned at {effort}
                </Chip>
              ))}
            </p>
          </Part>
        )}
      </div>
      {!choices.complete && (
        <p className="mt-2 text-xs text-ink-3">
          This report was built before your choices were kept with it: only your brief, the facts you kept and your
          documents are known.
        </p>
      )}
    </section>
  );
}

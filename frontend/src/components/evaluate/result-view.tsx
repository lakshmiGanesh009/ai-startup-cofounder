// One request's result: the launch strategy as a memo, a summary of the team's
// reviews beside it, and the team's work underneath: the specialists' reports,
// the plan, the reviews, the conflicts and what the request cost.

import { Markdown } from "@/components/markdown";
import { Badge, Score } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { ArrowRightIcon } from "@/components/ui/icons";
import { titleSize } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import type { EvaluateResponse, ReviewResult } from "@/lib/api";
import { formatSeconds, specialistTitle } from "@/lib/team";

export type Run = { prompt: string; result: EvaluateResponse; seconds?: number };

const UNAVAILABLE = "[unavailable]";

type Verdict = { review: ReviewResult; label: string; tone: "good" | "warn" | "bad" };

// The reviews made in one round. Each round carries the earlier reviews
// forward, and after the first, only the reports sent back are reviewed again.
function reviewedIn(result: EvaluateResponse, index: number): [string, ReviewResult][] {
  const before = result.review_history[index - 1];
  return Object.entries(result.review_history[index]).filter(
    (entry): entry is [string, ReviewResult] =>
      entry[1] !== undefined && (!before || before[entry[0] as keyof typeof before]?.approved === false),
  );
}

// Each specialist's last review in the request, and how it got there.
function verdicts(result: EvaluateResponse): Record<string, Verdict> {
  const found: Record<string, Verdict> = {};
  result.review_history.forEach((_, index) => {
    const revised = index > 0;
    for (const [name, review] of reviewedIn(result, index)) {
      if (result.analyses[name as keyof typeof result.analyses]?.startsWith(UNAVAILABLE)) {
        found[name] = { review, label: "Unavailable", tone: "bad" };
      } else if (review.approved) {
        found[name] = { review, label: revised ? "Approved after revision" : "Approved", tone: "good" };
      } else {
        found[name] = { review, label: revised ? "Not approved after revision" : "Not approved", tone: "warn" };
      }
    }
  });
  return found;
}

function words(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}

const VERDICT_TEXT = { good: "text-ink-3", warn: "text-warn", bad: "text-bad" };

function Summary({ run }: { run: Run }) {
  const { result } = run;
  const reviewed = verdicts(result);
  const metrics = Object.values(result.metrics);
  const calls = metrics.reduce((sum, metric) => sum + metric.calls, 0);
  const tokens = metrics.reduce((sum, metric) => sum + metric.tokens, 0);
  const conflicts = result.resolutions.length;

  return (
    <aside aria-label="The team's reviews" className="space-y-8 xl:sticky xl:top-8 xl:self-start">
      <section>
        <h3 className="kicker">Reviews</h3>
        <ul className="mt-3 space-y-3">
          {Object.keys(result.analyses).map((name) => {
            const verdict = reviewed[name];
            return (
              <li key={name} className="text-sm">
                <p className="font-medium text-ink">{specialistTitle(name)}</p>
                <p className="mt-1 flex items-center justify-between gap-3">
                  {verdict ? (
                    <Score score={verdict.review.score} />
                  ) : (
                    <span className="text-xs text-ink-3">Kept from earlier</span>
                  )}
                  {verdict && <span className={`text-xs ${VERDICT_TEXT[verdict.tone]}`}>{verdict.label}</span>}
                </p>
              </li>
            );
          })}
        </ul>
      </section>
      <section>
        <h3 className="kicker">Conflicts</h3>
        <p className="mt-2 text-sm text-ink-2">
          {conflicts ? `${conflicts} settled by the Chief of Staff.` : "None raised."}
        </p>
      </section>
      <section>
        <h3 className="kicker">This request</h3>
        <dl className="mt-2 grid grid-cols-[1fr_auto] gap-y-1 text-sm">
          <dt className="text-ink-3">Model calls</dt>
          <dd className="text-right tabular">{calls}</dd>
          <dt className="text-ink-3">Tokens</dt>
          <dd className="text-right tabular">{tokens.toLocaleString("en-US")}</dd>
          {run.seconds !== undefined && (
            <>
              <dt className="text-ink-3">Time</dt>
              <dd className="text-right tabular">{formatSeconds(run.seconds)}</dd>
            </>
          )}
        </dl>
      </section>
      <ButtonLink href={`/reports?session=${encodeURIComponent(result.session_id)}`} size="sm" className="w-full">
        Open the report
        <ArrowRightIcon className="size-3.5" />
      </ButtonLink>
    </aside>
  );
}

function Reports({ result }: { result: EvaluateResponse }) {
  const reviewed = verdicts(result);
  return (
    <div className="divide-y divide-rule border-y border-rule">
      {Object.entries(result.analyses).map(([name, report], index) => (
        <details key={name} open={index === 0} className="group">
          <summary className="flex cursor-pointer list-none items-center gap-3 py-3.5 [&::-webkit-details-marker]:hidden">
            <span aria-hidden className="w-3 text-ink-3 transition-transform group-open:rotate-90">
              ›
            </span>
            <span className="font-medium">{specialistTitle(name)}</span>
            <span className="text-xs text-ink-3 tabular">{words(report ?? "")} words</span>
            {reviewed[name] && (
              <span className="ml-auto">
                <Score score={reviewed[name].review.score} />
              </span>
            )}
          </summary>
          <div className="pb-7 pl-6">
            <Markdown compact labels>{report ?? ""}</Markdown>
          </div>
        </details>
      ))}
    </div>
  );
}

function Plan({ result }: { result: EvaluateResponse }) {
  return (
    <div className="max-w-3xl">
      <p className="kicker">Objective</p>
      <p className="mt-1.5 font-serif text-lg leading-snug">{result.objective}</p>
      <dl className="mt-6 divide-y divide-rule border-y border-rule">
        {Object.entries(result.assignments).map(([name, task]) => (
          <div key={name} className="grid grid-cols-1 gap-1 py-3 text-sm sm:grid-cols-[12rem_minmax(0,1fr)] sm:gap-6">
            <dt className="font-medium">{specialistTitle(name)}</dt>
            <dd className="text-ink-2">{task}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Reviews({ result }: { result: EvaluateResponse }) {
  if (!result.review_history.length) return <p className="text-sm text-ink-3">No reviews in this request.</p>;
  const last = result.review_history.length - 1;
  return (
    <div className="space-y-8">
      {result.review_history.map((_, number) => (
        <section key={number} aria-label={`Round ${number + 1}`}>
          <h4 className="kicker">
            Round {number + 1}
            {number > 0 && <span className="font-normal tracking-normal normal-case"> · the revised reports</span>}
          </h4>
          <table className="mt-2 w-full text-left text-sm">
            <thead>
              <tr className="border-b border-rule-strong text-xs text-ink-3">
                <th className="py-2 pr-4 font-medium">Specialist</th>
                <th className="py-2 pr-4 font-medium">Verdict</th>
                <th className="py-2 pr-4 font-medium">Score</th>
                <th className="py-2 font-medium">Feedback</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {reviewedIn(result, number).map(([name, review]) => (
                <tr key={name} className="align-top">
                  <td className="py-2.5 pr-4 font-medium whitespace-nowrap">{specialistTitle(name)}</td>
                  <td className="py-2.5 pr-4 whitespace-nowrap">
                    {review.approved ? (
                      <Badge tone="good">Approved</Badge>
                    ) : (
                      <Badge tone="warn">{number < last ? "Sent back" : "Not approved"}</Badge>
                    )}
                  </td>
                  <td className="py-2.5 pr-4">
                    <Score score={review.score} />
                  </td>
                  <td className="py-2.5 text-ink-2">{review.feedback || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}

function Conflicts({ result }: { result: EvaluateResponse }) {
  if (!result.resolutions.length) return <p className="text-sm text-ink-3">No conflicts were raised.</p>;
  return (
    <ol className="max-w-3xl divide-y divide-rule border-y border-rule">
      {result.resolutions.map(({ conflict, decision, revise }, index) => (
        <li key={index} className="py-4 text-sm">
          <p className="font-medium">
            {specialistTitle(conflict.raised_by)} <span className="font-normal text-ink-3">questioned</span>{" "}
            {specialistTitle(conflict.about)}
          </p>
          <p className="mt-1 text-ink-2">{conflict.issue}</p>
          <div className="mt-3 border-l-2 border-primary pl-3">
            <p className="kicker">Decision</p>
            <p className="mt-0.5 text-ink">{decision}</p>
          </div>
          <p className="mt-2 text-xs text-ink-3">
            {revise ? `${specialistTitle(revise)} revised its report to match.` : "No report needed revising."}
          </p>
        </li>
      ))}
    </ol>
  );
}

function RunMetrics({ result }: { result: EvaluateResponse }) {
  const rows = Object.entries(result.metrics);
  const longest = Math.max(1, ...rows.map(([, metric]) => metric.seconds));
  return (
    <table className="w-full max-w-3xl text-left text-sm">
      <thead>
        <tr className="border-b border-rule-strong text-xs text-ink-3">
          <th className="py-2 pr-4 font-medium">Stage</th>
          <th className="py-2 pr-4 text-right font-medium">Calls</th>
          <th className="py-2 pr-4 text-right font-medium">Tokens</th>
          <th className="py-2 font-medium">Seconds</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-rule">
        {rows.map(([node, metric]) => (
          <tr key={node}>
            <td className="py-2 pr-4">{node}</td>
            <td className="py-2 pr-4 text-right tabular">{metric.calls}</td>
            <td className="py-2 pr-4 text-right tabular">{metric.tokens.toLocaleString("en-US")}</td>
            <td className="py-2">
              <div className="flex items-center gap-2.5">
                <div
                  aria-hidden
                  className="h-1.5 rounded-full"
                  style={{ width: `${Math.max(2, (metric.seconds / longest) * 60)}%`, background: "var(--data-1)" }}
                />
                <span className="text-ink-2 tabular">{metric.seconds.toFixed(1)}</span>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ResultView({ run, number }: { run: Run; number: number }) {
  const { result } = run;
  return (
    <article aria-label={`Request ${number}`}>
      <header className="max-w-3xl">
        <p className="kicker">Launch strategy · Request {number}</p>
        <h2 className={`mt-2 font-serif ${titleSize(result.objective)} leading-snug font-medium tracking-[-0.01em]`}>
          {result.objective}
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-ink-3">
          <span className="text-ink-2">Your brief:</span> {run.prompt}
        </p>
      </header>
      <div className="mt-10 grid grid-cols-1 gap-12 xl:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="min-w-0">
          <p className="mb-6 border-b border-rule pb-3 text-xs text-ink-3">
            Written by the Chief of Staff from the specialists&apos; reviewed reports
          </p>
          <Markdown labels>{result.final_strategy}</Markdown>
        </div>
        <Summary run={run} />
      </div>
      <section aria-label="The team's work" className="mt-16">
        <Tabs
          label="The team's work"
          tabs={[
            { label: "Specialist reports", content: <Reports result={result} /> },
            { label: "Plan", content: <Plan result={result} /> },
            { label: "Reviews", content: <Reviews result={result} /> },
            { label: "Conflicts", content: <Conflicts result={result} /> },
            { label: "Run", content: <RunMetrics result={result} /> },
          ]}
        />
      </section>
    </article>
  );
}

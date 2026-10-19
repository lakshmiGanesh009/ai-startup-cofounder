// One request's result: the objective, the launch strategy, and tabs for the
// plan, the specialists' reports, the reviews, the conflicts and the metrics.

import { Markdown } from "@/components/markdown";
import { Badge } from "@/components/ui/badge";
import { Tabs } from "@/components/ui/tabs";
import type { EvaluateResponse, ReviewResult } from "@/lib/api";
import { specialistTitle } from "@/lib/team";

function Plan({ result }: { result: EvaluateResponse }) {
  return (
    <ul className="space-y-3">
      {Object.entries(result.assignments).map(([name, task]) => (
        <li key={name} className="rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-800">
          <p className="mb-1 font-semibold">{specialistTitle(name)}</p>
          <p className="text-zinc-700 dark:text-zinc-300">{task}</p>
        </li>
      ))}
    </ul>
  );
}

function Reports({ result }: { result: EvaluateResponse }) {
  return (
    <div className="space-y-3">
      {Object.entries(result.analyses).map(([name, report], index) => (
        <details key={name} open={index === 0} className="rounded-md border border-zinc-200 dark:border-zinc-800">
          <summary className="cursor-pointer px-4 py-3 font-semibold">{specialistTitle(name)}</summary>
          <div className="border-t border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <Markdown>{report ?? ""}</Markdown>
          </div>
        </details>
      ))}
    </div>
  );
}

function Verdict({ review }: { review: ReviewResult }) {
  return review.approved ? <Badge tone="green">Approved</Badge> : <Badge tone="amber">Sent back</Badge>;
}

function Reviews({ result }: { result: EvaluateResponse }) {
  if (!result.review_history.length) return <p className="text-sm text-zinc-500">No reviews in this request.</p>;
  return (
    <div className="space-y-5">
      {result.review_history.map((round, number) => (
        <div key={number}>
          <h4 className="mb-2 text-sm font-semibold">Round {number + 1}</h4>
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-zinc-500 uppercase">
              <tr>
                <th className="py-1 pr-3 font-medium">Specialist</th>
                <th className="py-1 pr-3 font-medium">Verdict</th>
                <th className="py-1 pr-3 font-medium">Score</th>
                <th className="py-1 font-medium">Feedback</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {Object.entries(round).map(([name, review]) =>
                review ? (
                  <tr key={name} className="align-top">
                    <td className="py-2 pr-3 font-medium whitespace-nowrap">{specialistTitle(name)}</td>
                    <td className="py-2 pr-3">
                      <Verdict review={review} />
                    </td>
                    <td className="py-2 pr-3 tabular-nums">{review.score}/5</td>
                    <td className="py-2 text-zinc-700 dark:text-zinc-300">{review.feedback || "—"}</td>
                  </tr>
                ) : null,
              )}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

function Conflicts({ result }: { result: EvaluateResponse }) {
  if (!result.resolutions.length) return <p className="text-sm text-zinc-500">No conflicts were raised.</p>;
  return (
    <ul className="space-y-3">
      {result.resolutions.map(({ conflict, decision, revise }, index) => (
        <li key={index} className="rounded-md border border-zinc-200 p-4 text-sm dark:border-zinc-800">
          <p className="font-semibold">
            {specialistTitle(conflict.raised_by)} vs {specialistTitle(conflict.about)}
          </p>
          <p className="mt-1 text-zinc-700 dark:text-zinc-300">{conflict.issue}</p>
          <p className="mt-2">
            <span className="font-medium">Decision:</span> {decision}
          </p>
          <p className="mt-2">
            {revise ? <Badge tone="amber">Revised: {specialistTitle(revise)}</Badge> : <Badge tone="gray">No revision needed</Badge>}
          </p>
        </li>
      ))}
    </ul>
  );
}

function Metrics({ result }: { result: EvaluateResponse }) {
  const rows = Object.entries(result.metrics);
  const longest = Math.max(1, ...rows.map(([, metric]) => metric.seconds));
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-xs text-zinc-500 uppercase">
        <tr>
          <th className="py-1 pr-3 font-medium">Stage</th>
          <th className="py-1 pr-3 text-right font-medium">LLM calls</th>
          <th className="py-1 pr-3 text-right font-medium">Tokens</th>
          <th className="py-1 font-medium">Seconds</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
        {rows.map(([node, metric]) => (
          <tr key={node}>
            <td className="py-2 pr-3">{node}</td>
            <td className="py-2 pr-3 text-right tabular-nums">{metric.calls}</td>
            <td className="py-2 pr-3 text-right tabular-nums">{metric.tokens.toLocaleString("en-US")}</td>
            <td className="py-2">
              <div className="flex items-center gap-2">
                <div
                  aria-hidden
                  className="h-2 rounded-r bg-accent"
                  style={{ width: `${Math.max(2, (metric.seconds / longest) * 60)}%` }}
                />
                <span className="tabular-nums">{metric.seconds.toFixed(1)}</span>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ResultView({ result }: { result: EvaluateResponse }) {
  const metrics = Object.values(result.metrics);
  const calls = metrics.reduce((sum, metric) => sum + metric.calls, 0);
  const tokens = metrics.reduce((sum, metric) => sum + metric.tokens, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
        <span>
          <span className="font-medium text-zinc-800 dark:text-zinc-200">Objective:</span> {result.objective}
        </span>
        <Badge tone="gray">{calls} LLM calls</Badge>
        <Badge tone="gray">{tokens.toLocaleString("en-US")} tokens</Badge>
      </div>
      <article className="rounded-lg border border-zinc-200 bg-surface p-5 shadow-xs dark:border-zinc-800">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg font-semibold">Launch strategy</h3>
          <Badge>Written by the Chief of Staff</Badge>
        </div>
        <Markdown>{result.final_strategy}</Markdown>
      </article>
      <Tabs
        label="The team's work"
        tabs={[
          { label: "Plan", content: <Plan result={result} /> },
          { label: "Reports", content: <Reports result={result} /> },
          { label: "Reviews", content: <Reviews result={result} /> },
          { label: "Conflicts", content: <Conflicts result={result} /> },
          { label: "Metrics", content: <Metrics result={result} /> },
        ]}
      />
    </div>
  );
}

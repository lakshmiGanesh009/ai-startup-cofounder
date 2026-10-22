// One request's result: the launch strategy as a memo, a summary of the team's
// reviews beside it, and the team's work underneath: the specialists' reports,
// the plan, the reviews, the conflicts and what the request cost.

import { DocumentList, type DocumentRef } from "@/components/documents";
import { Feedback } from "@/components/evaluate/feedback";
import { ResearchFindings, ResearchSources } from "@/components/evaluate/research";
import { GuardrailNotice } from "@/components/guardrail-notice";
import { Markdown } from "@/components/markdown";
import { AgentAvatar, AgentName, AgentStack, TeamStripe } from "@/components/ui/agent";
import { Badge, Score } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { ArrowRightIcon } from "@/components/ui/icons";
import { titleSize } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { Notice } from "@/components/ui/notice";
import type {
  Answer,
  CompanyProfile,
  DeepResearch,
  EconomicData,
  EvaluateResponse,
  Research,
  ReviewResult,
} from "@/lib/api";
import { citations } from "@/lib/brief";
import { agentClass, agentFill, agentOf, agentsOf, specialistAgent } from "@/lib/agents";
import { formatSeconds, specialistTitle, stepName } from "@/lib/team";

// What the founder added to the brief before the team ran: answers to the
// Chief of Staff's questions, and the web research they kept.
export type Brief = { answers: Answer[]; research: Research | null };

export type Run = { prompt: string; result: EvaluateResponse; seconds?: number; brief?: Brief; documents?: DocumentRef[] };

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
        <ul className="mt-3 space-y-2">
          {Object.keys(result.analyses).map((name) => {
            const verdict = reviewed[name];
            return (
              <li key={name} className={`${agentClass(specialistAgent(name))} rounded-lg bg-agent-soft px-3 py-2.5 text-sm`}>
                <AgentName agent={specialistAgent(name)} size="sm" className="font-medium text-ink">
                  {specialistTitle(name)}
                </AgentName>
                <p className="mt-2 flex items-center justify-between gap-3 pl-8">
                  {verdict ? (
                    <Score score={verdict.review.score} agent={specialistAgent(name)} />
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
      {result.trace_url && (
        <section>
          <h3 className="kicker">Trace</h3>
          <TraceLink url={result.trace_url} className="mt-2" />
        </section>
      )}
      <section>
        <h3 className="kicker">Conflicts</h3>
        <p className="mt-2 flex items-center gap-2 text-sm text-ink-2">
          {conflicts > 0 && <AgentAvatar agent="chief" size="xs" />}
          {conflicts ? `${conflicts} settled by the Chief of Staff.` : "None raised."}
        </p>
      </section>
      {hasResearch(run) && (
        <section>
          <h3 className="kicker">Research</h3>
          <ul className="mt-2 space-y-1 text-sm text-ink-2">
            {run.brief?.research && <li>{count(run.brief.research.findings.length, "fact")} from the web for the brief</li>}
            {run.brief && run.brief.answers.length > 0 && <li>{count(run.brief.answers.length, "answer")} from you</li>}
            {result.economic && result.economic.figures.length > 0 && (
              <li>{count(result.economic.figures.length, "official figure")} from FRED</li>
            )}
            {result.research && (
              <li>
                Deep research on {count(Object.keys(result.research.areas).length, "area")} and{" "}
                {count(result.research.companies.length, "competitor")}
                {result.research.providers.length > 0 && ` with ${result.research.providers.join(" and ")}`}
                {[
                  result.research.credits > 0 && `${result.research.credits} Tavily credits`,
                  result.research.searches > 0 && count(result.research.searches, "web search").replace("searchs", "searches"),
                ]
                  .filter(Boolean)
                  .map((cost) => `, ${cost}`)
                  .join("")}
              </li>
            )}
          </ul>
        </section>
      )}
      <section>
        <h3 className="kicker">This request</h3>
        <dl className="mt-2 grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-rule bg-rule text-center">
          {[
            ["Model calls", String(calls)],
            ["Tokens", tokens >= 10_000 ? `${(tokens / 1000).toFixed(1)}k` : tokens.toLocaleString("en-US")],
            ...(run.seconds !== undefined ? [["Time", formatSeconds(run.seconds)]] : []),
          ].map(([label, value]) => (
            <div key={label} className="flex flex-col-reverse bg-surface px-1 py-2.5">
              <dt className="text-[11px] text-ink-3">{label}</dt>
              <dd className="text-[15px] font-medium tabular">{value}</dd>
            </div>
          ))}
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
        <details key={name} open={index === 0} className={`${agentClass(specialistAgent(name))} group`}>
          <summary className="flex cursor-pointer list-none items-center gap-3 py-3.5 [&::-webkit-details-marker]:hidden">
            <span aria-hidden className="w-3 text-ink-3 transition-transform group-open:rotate-90">
              ›
            </span>
            <AgentAvatar agent={specialistAgent(name)} size="md" />
            <span className="font-medium">{specialistTitle(name)}</span>
            <span className="text-xs text-ink-3 tabular">{words(report ?? "")} words</span>
            {reviewed[name] && (
              <span className="ml-auto">
                <Score score={reviewed[name].review.score} agent={specialistAgent(name)} />
              </span>
            )}
          </summary>
          <div className="mb-7 ml-[1.3rem] border-l-2 border-agent-line pl-[1.85rem]">
            <Markdown compact labels>{report ?? ""}</Markdown>
          </div>
        </details>
      ))}
    </div>
  );
}

function count(number: number, word: string): string {
  return `${number} ${word}${number === 1 ? "" : "s"}`;
}

// Whether the run has research to show: the brief's, the founder's answers, or deep research.
function hasResearch(run: Run): boolean {
  return Boolean(
    run.brief?.answers.length || run.brief?.research || run.result.research || run.result.economic?.figures.length,
  );
}

const PROFILE_FIELDS = [
  ["pricing", "Pricing"],
  ["customers", "Customers"],
  ["funding", "Funding"],
  ["recent_moves", "Recent moves"],
  ["strengths", "Strengths"],
  ["weaknesses", "Weaknesses"],
  ["site", "Its own pricing page"],
] as const;

function Competitor({ company }: { company: CompanyProfile }) {
  return (
    <li className="rounded-lg border border-rule bg-surface p-4">
      <p className="font-medium">
        {company.name}
        {company.sources.length > 0 && (
          <span className="ml-1.5 text-xs font-normal text-ink-3 tabular">{citations(company.sources)}</span>
        )}
      </p>
      {company.summary && <p className="mt-1 text-sm text-ink-2">{company.summary}</p>}
      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-[7rem_minmax(0,1fr)]">
        {PROFILE_FIELDS.filter(([key]) => company[key]).map(([key, label]) => (
          <div key={key} className="contents">
            <dt className="text-ink-3">{label}</dt>
            <dd className="text-ink-2">{company[key]}</dd>
          </div>
        ))}
      </dl>
    </li>
  );
}

// A figure as the page shows it: 4.12, 323.42, 31,250.
function figureValue(value: number): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: Math.abs(value) >= 1000 ? 0 : 2 });
}

// The official figures the team read, from FRED, each linked to its page there.
function Figures({ economic }: { economic: EconomicData }) {
  return (
    <section aria-label="Official figures">
      <h4 className="kicker">Official figures, from FRED</h4>
      <p className="mt-1 text-sm text-ink-3">
        The St. Louis Fed&apos;s data, looked up for this plan; the reports cite each as [FRED · its id].
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-rule text-left text-xs text-ink-3">
              <th className="py-2 pr-4 font-medium">Figure</th>
              <th className="py-2 pr-4 font-medium">Latest</th>
              <th className="py-2 font-medium">Over the year</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {economic.figures.map((figure) => (
              <tr key={figure.id} className="align-top">
                <td className="py-2.5 pr-4">
                  <span className="block text-ink">{figure.title}</span>
                  <a href={figure.link} target="_blank" rel="noreferrer" className="font-mono text-xs text-link hover:underline">
                    {figure.id}
                  </a>
                  {figure.why && <span className="mt-0.5 block text-xs text-ink-3">{figure.why}</span>}
                </td>
                <td className="py-2.5 pr-4 whitespace-nowrap">
                  <span className="tabular text-ink">{figureValue(figure.value)}</span>{" "}
                  <span className="text-xs text-ink-3">{figure.units}</span>
                  <span className="block text-xs text-ink-3 tabular">{figure.date}</span>
                </td>
                <td className="py-2.5 text-ink-2 tabular">{figure.change || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {economic.note && <p className="mt-2 text-xs text-ink-3">{economic.note}</p>}
    </section>
  );
}

function ResearchTab({
  brief,
  deep,
  economic,
}: {
  brief?: Brief;
  deep?: DeepResearch | null;
  economic?: EconomicData | null;
}) {
  const sources = deep?.sources ?? brief?.research?.sources ?? [];
  return (
    <div className="max-w-3xl space-y-12">
      {economic && economic.figures.length > 0 && <Figures economic={economic} />}
      {brief && brief.answers.length > 0 && (
        <section aria-label="Your answers">
          <h4 className="kicker">Your answers to the Chief of Staff</h4>
          <dl className="mt-2 divide-y divide-rule border-y border-rule">
            {brief.answers.map((answer) => (
              <div key={answer.question} className="grid grid-cols-1 gap-1 py-3 text-sm sm:grid-cols-[minmax(0,1fr)_14rem] sm:gap-6">
                <dt className="text-ink-2">{answer.question}</dt>
                <dd className="font-medium">{answer.answer}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      {brief?.research && (
        <section aria-label="Web research">
          <h4 className="kicker">What the web said before the team started</h4>
          <div className="mt-2">
            <ResearchFindings research={brief.research} prefix="run" />
          </div>
        </section>
      )}
      {deep && Object.keys(deep.areas).length > 0 && (
        <section aria-label="Deep research">
          <h4 className="kicker">Deep research by area</h4>
          <div className="mt-2 divide-y divide-rule border-y border-rule">
            {Object.entries(deep.areas).map(([name, report]) => (
              <details key={name} className="group">
                <summary className="flex cursor-pointer list-none items-center gap-3 py-3 [&::-webkit-details-marker]:hidden">
                  <span aria-hidden className="w-3 text-ink-3 transition-transform group-open:rotate-90">
                    ›
                  </span>
                  <AgentName agent={specialistAgent(name)} size="sm" className="font-medium">
                    {specialistTitle(name)}
                  </AgentName>
                </summary>
                <div className="pb-6 pl-6">
                  <Markdown compact labels>
                    {report ?? ""}
                  </Markdown>
                </div>
              </details>
            ))}
          </div>
        </section>
      )}
      {deep && deep.companies.length > 0 && (
        <section aria-label="Competitors">
          <h4 className="kicker">Competitors</h4>
          <ul className="mt-3 space-y-3">
            {deep.companies.map((company) => (
              <Competitor key={company.name} company={company} />
            ))}
          </ul>
        </section>
      )}
      {deep && deep.failed.length > 0 && (
        <Notice tone="warn">
          The research could not cover {deep.failed.map(specialistTitle).join(", ")}; the team worked without it there.
        </Notice>
      )}
      {sources.length > 0 && (
        <section aria-label="Sources">
          <h4 className="kicker">Sources</h4>
          <div className="mt-3">
            <ResearchSources sources={sources} prefix="run" />
          </div>
        </section>
      )}
    </div>
  );
}

function Plan({ result }: { result: EvaluateResponse }) {
  return (
    <div className="max-w-3xl">
      <p className="kicker flex items-center gap-2">
        <AgentAvatar agent="chief" size="xs" /> The Chief of Staff&apos;s objective
      </p>
      <p className="mt-2 border-l-2 border-[var(--agent-chief)] pl-4 font-serif text-lg leading-snug">{result.objective}</p>
      <dl className="mt-6 divide-y divide-rule border-y border-rule">
        {Object.entries(result.assignments).map(([name, task]) => (
          <div key={name} className="grid grid-cols-1 gap-1 py-3 text-sm sm:grid-cols-[12rem_minmax(0,1fr)] sm:gap-6">
            <dt className="font-medium">
              <AgentName agent={specialistAgent(name)} size="sm">
                {specialistTitle(name)}
              </AgentName>
            </dt>
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
                  <td className="py-2.5 pr-4 font-medium whitespace-nowrap">
                    <AgentName agent={specialistAgent(name)}>{specialistTitle(name)}</AgentName>
                  </td>
                  <td className="py-2.5 pr-4 whitespace-nowrap">
                    {review.approved ? (
                      <Badge tone="good">Approved</Badge>
                    ) : (
                      <Badge tone="warn">{number < last ? "Sent back" : "Not approved"}</Badge>
                    )}
                  </td>
                  <td className="py-2.5 pr-4">
                    <Score score={review.score} agent={specialistAgent(name)} />
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
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 font-medium">
            <AgentName agent={specialistAgent(conflict.raised_by)}>{specialistTitle(conflict.raised_by)}</AgentName>
            <span className="font-normal text-ink-3">questioned</span>
            <AgentName agent={specialistAgent(conflict.about)}>{specialistTitle(conflict.about)}</AgentName>
          </p>
          <p className="mt-1.5 text-ink-2">{conflict.issue}</p>
          <div className="agent-chief mt-3 rounded-r-md border-l-2 border-agent bg-agent-soft py-2 pr-3 pl-3">
            <p className="kicker flex items-center gap-1.5">
              <AgentAvatar agent="chief" size="xs" /> The Chief of Staff&apos;s decision
            </p>
            <p className="mt-1 text-ink">{decision}</p>
          </div>
          <p className="mt-2 text-xs text-ink-3">
            {revise ? `${specialistTitle(revise)} revised its report to match.` : "No report needed revising."}
          </p>
        </li>
      ))}
    </ol>
  );
}

// The run's trace in Langfuse: every model call, with its prompt, reply, tokens and cost, and the scores.
function TraceLink({ url, className = "" }: { url: string; className?: string }) {
  return (
    <p className={`text-sm ${className}`}>
      <a href={url} target="_blank" rel="noreferrer" className="font-medium text-ink underline decoration-rule-strong underline-offset-4 hover:decoration-ink">
        Open the run in Langfuse ↗
      </a>
      <span className="mt-1 block text-xs leading-relaxed text-ink-3">
        Every model call, with its prompt, reply, tokens and cost, and the scores on the run.
      </span>
    </p>
  );
}

function RunMetrics({ result }: { result: EvaluateResponse }) {
  const rows = Object.entries(result.metrics);
  const longest = Math.max(1, ...rows.map(([, metric]) => metric.seconds));
  return (
    <div className="max-w-3xl space-y-5">
      <table className="w-full text-left text-sm">
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
              <td className="py-2 pr-4">
                {agentsOf(node).length > 1 ? (
                  <span className="inline-flex items-center gap-2">
                    <AgentStack agents={agentsOf(node)} />
                    {stepName(node)}
                  </span>
                ) : (
                  <AgentName agent={agentOf(node)}>{stepName(node)}</AgentName>
                )}
              </td>
              <td className="py-2 pr-4 text-right tabular">{metric.calls}</td>
              <td className="py-2 pr-4 text-right tabular">{metric.tokens.toLocaleString("en-US")}</td>
              <td className="py-2">
                <div className="flex items-center gap-2.5">
                  <div
                    aria-hidden
                    className="h-1.5 rounded-full"
                    style={{ width: `${Math.max(2, (metric.seconds / longest) * 60)}%`, background: agentFill(agentsOf(node)) }}
                  />
                  <span className="text-ink-2 tabular">{metric.seconds.toFixed(1)}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {result.trace_url && <TraceLink url={result.trace_url} />}
    </div>
  );
}

export function ResultView({ run, number }: { run: Run; number: number }) {
  const { result } = run;
  return (
    <article aria-label={`Request ${number}`}>
      <header className="max-w-3xl">
        <p className="kicker flex items-center gap-3">
          Launch strategy · Request {number}
          <TeamStripe />
        </p>
        <h2 className={`mt-2 font-serif ${titleSize(result.objective)} leading-snug font-medium tracking-[-0.01em]`}>
          {result.objective}
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-ink-3">
          <span className="text-ink-2">Your brief:</span> {run.prompt}
        </p>
        {run.documents && run.documents.length > 0 && (
          <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1.5">
            <span className="text-sm text-ink-2">Worked from:</span>
            <DocumentList documents={run.documents} />
          </div>
        )}
        <GuardrailNotice flags={result.guardrails} className="mt-5" />
      </header>
      <div className="mt-10 grid grid-cols-1 gap-12 xl:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="min-w-0 rounded-xl border border-rule bg-surface px-5 py-6 shadow-[0_1px_2px_rgb(0_0_0/0.04),0_8px_24px_-12px_rgb(0_0_0/0.12)] sm:px-9 sm:py-8">
          <p className="mb-6 flex items-center gap-2.5 border-b border-rule pb-4 text-xs text-ink-3">
            <AgentAvatar agent="chief" size="md" />
            <span>
              <span className="block text-sm font-medium text-ink">Chief of Staff</span>
              Written from the specialists&apos; reviewed reports
            </span>
          </p>
          <Markdown labels>{result.final_strategy}</Markdown>
          <Feedback result={result} />
        </div>
        <Summary run={run} />
      </div>
      <section aria-label="The team's work" className="mt-16">
        <Tabs
          label="The team's work"
          tabs={[
            { label: "Specialist reports", content: <Reports result={result} /> },
            ...(hasResearch(run)
              ? [
                  {
                    label: "Research",
                    content: <ResearchTab brief={run.brief} deep={result.research} economic={result.economic} />,
                  },
                ]
              : []),
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

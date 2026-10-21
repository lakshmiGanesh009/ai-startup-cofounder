"use client";

// Before the team starts: the brief as it will be sent, the Chief of Staff's
// questions with likely answers to pick from, and the facts the web research
// found, each of which can be left out. A question left unanswered is skipped.

import { useId, useState } from "react";

import { ResearchFindings, ResearchSources } from "@/components/evaluate/research";
import { GuardrailNotice } from "@/components/guardrail-notice";
import { AgentAvatar } from "@/components/ui/agent";
import { Button, Kbd } from "@/components/ui/button";
import { inputClass } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import type { Answer, PreparedBrief, Question, Research } from "@/lib/api";
import { keepFindings } from "@/lib/brief";

function Ask({
  question,
  number,
  answer,
  onAnswer,
}: {
  question: Question;
  number: number;
  answer: string;
  onAnswer: (answer: string) => void;
}) {
  const id = useId();
  return (
    <div role="group" aria-labelledby={id} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-3 py-5">
      <span aria-hidden className="pt-0.5 text-xs text-ink-3 tabular">
        {number}
      </span>
      <div>
        <p id={id} className="font-medium text-ink">
          {question.question}
        </p>
        <p className="mt-1 text-sm text-ink-3">{question.why}</p>
        {question.suggestions.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {question.suggestions.map((suggestion) => {
              const picked = answer === suggestion;
              return (
                <button
                  key={suggestion}
                  type="button"
                  aria-pressed={picked}
                  onClick={() => onAnswer(picked ? "" : suggestion)}
                  className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                    picked
                      ? "border-primary bg-primary-soft text-ink"
                      : "border-rule-strong text-ink-2 hover:border-ink-3 hover:text-ink"
                  }`}
                >
                  {suggestion}
                </button>
              );
            })}
          </div>
        )}
        <input
          value={answer}
          onChange={(event) => onAnswer(event.target.value)}
          aria-label={`Your answer: ${question.question}`}
          placeholder="Or answer in your own words"
          className={`${inputClass} mt-3`}
        />
      </div>
    </div>
  );
}

export function BriefReview({
  prompt,
  prepared,
  wait,
  onRun,
  onBack,
}: {
  prompt: string;
  prepared: PreparedBrief;
  wait: string;
  onRun: (answers: Answer[], research: Research | null) => void;
  onBack: () => void;
}) {
  const prefix = useId();
  const [answers, setAnswers] = useState(() => prepared.questions.map(() => ""));
  const [leftOut, setLeftOut] = useState<ReadonlySet<number>>(new Set());
  const { research, questions } = prepared;

  function run() {
    onRun(
      questions
        .map((question, index) => ({ question: question.question, answer: answers[index].trim() }))
        .filter((answer) => answer.answer),
      keepFindings(research, leftOut),
    );
  }

  function toggle(index: number) {
    setLeftOut((current) => {
      const next = new Set(current);
      if (!next.delete(index)) next.add(index);
      return next;
    });
  }

  return (
    <section
      aria-label="Before the team starts"
      onKeyDown={(event) => {
        if ((event.metaKey || event.ctrlKey) && event.key === "Enter") run();
      }}
    >
      <header className="flex flex-wrap items-start justify-between gap-x-8 gap-y-3 border-b border-rule pb-6">
        <div className="max-w-3xl">
          <p className="kicker">Before the team starts</p>
          <p className="mt-2 font-serif text-xl leading-snug">{prompt}</p>
        </div>
        <Button size="sm" onClick={onBack}>
          Edit the brief
        </Button>
      </header>
      <GuardrailNotice flags={prepared.guardrails} className="mt-6" />

      <div className="mt-8 grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="min-w-0 space-y-12">
          <section aria-labelledby={`${prefix}-questions`}>
            <h2 id={`${prefix}-questions`} className="kicker flex items-center gap-2">
              <AgentAvatar agent="chief" size="xs" />
              The Chief of Staff asks
            </h2>
            {questions.length ? (
              <>
                <p className="mt-2 text-sm text-ink-2">
                  The answers go to every agent. Skip any you would rather leave to the team.
                </p>
                <div className="mt-2 divide-y divide-rule border-y border-rule">
                  {questions.map((question, index) => (
                    <Ask
                      key={question.question}
                      question={question}
                      number={index + 1}
                      answer={answers[index]}
                      onAnswer={(answer) =>
                        setAnswers((current) => current.map((each, at) => (at === index ? answer : each)))
                      }
                    />
                  ))}
                </div>
              </>
            ) : (
              <p className="mt-2 text-sm text-ink-2">Nothing: the brief gives the team what it needs.</p>
            )}
          </section>

          <section aria-labelledby={`${prefix}-research`}>
            <h2 id={`${prefix}-research`} className="kicker flex items-center gap-2">
              <AgentAvatar agent="research" size="xs" />
              What the web says
            </h2>
            {research ? (
              <>
                <p className="mt-2 text-sm text-ink-2">
                  {research.findings.length} {research.findings.length === 1 ? "fact" : "facts"} from{" "}
                  {research.sources.length} {research.sources.length === 1 ? "source" : "sources"}
                  {prepared.provider ? `, found with ${prepared.provider},` : ","} for every agent to weigh. Leave out
                  any that do not fit your case.
                </p>
                <div className="mt-3">
                  <ResearchFindings research={research} prefix={prefix} leftOut={leftOut} onToggle={toggle} />
                </div>
              </>
            ) : (
              <Notice className="mt-3">{prepared.research_note ?? "No web research for this brief."}</Notice>
            )}
          </section>
        </div>

        {(research || prepared.queries.length > 0) && (
          <aside aria-label="Sources" className="space-y-8 lg:pt-7">
            {research && (
              <section>
                <h3 className="kicker">Sources</h3>
                <div className="mt-3">
                  <ResearchSources sources={research.sources} prefix={prefix} />
                </div>
              </section>
            )}
            {prepared.queries.length > 0 && (
              <section>
                <h3 className="kicker">Searched for</h3>
                <ul className="mt-2 space-y-1 text-sm text-ink-2">
                  {prepared.queries.map((query) => (
                    <li key={query}>{query}</li>
                  ))}
                </ul>
              </section>
            )}
          </aside>
        )}
      </div>

      <div className="mt-12 flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-rule pt-6">
        <Button variant="primary" onClick={run}>
          Run the team
          <Kbd>⌘↵</Kbd>
        </Button>
        <p className="text-sm text-ink-3">{wait}</p>
      </div>
    </section>
  );
}

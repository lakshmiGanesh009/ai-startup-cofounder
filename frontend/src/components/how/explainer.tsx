// The How it works page's explanation, section by section: the team, how the
// Chief of Staff decides, how information moves through the shared state, how
// the critique works, where the facts come from, where your judgement comes
// in, the stack, and your path through the app. Its numbers come from the
// backend's own settings (/pipeline).

import {
  ChartIcon,
  CheckIcon,
  ChipIcon,
  CompassIcon,
  DocumentIcon,
  FlowIcon,
  GavelIcon,
  GlobeIcon,
  HandIcon,
  MegaphoneIcon,
  PulseIcon,
  ServerIcon,
  ShieldIcon,
  SparkIcon,
  StateIcon,
  SwapIcon,
  TeamIcon,
  WindowIcon,
} from "@/components/ui/icons";
import type { Pipeline, Reasoning, Specialist } from "@/lib/api";
import { JUDGEMENT, type LayerIcon, STACK, STATE, STEPS, USER_FLOW } from "@/lib/how";

type Glyph = (props: { className?: string }) => React.ReactNode;

const SPECIALIST_ICONS: Record<Specialist, Glyph> = {
  marketing: MegaphoneIcon,
  finance: ChartIcon,
  technical: ChipIcon,
  risk: ShieldIcon,
};

const LAYER_ICONS: Record<LayerIcon, Glyph> = {
  window: WindowIcon,
  server: ServerIcon,
  flow: FlowIcon,
  team: TeamIcon,
  spark: SparkIcon,
  globe: GlobeIcon,
  document: DocumentIcon,
  state: StateIcon,
  pulse: PulseIcon,
  check: CheckIcon,
};

function Section({
  id,
  kicker,
  title,
  intro,
  children,
}: {
  id: string;
  kicker: string;
  title: string;
  intro?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-8 border-t border-rule pt-10">
      <p className="kicker">{kicker}</p>
      <h2 id={`${id}-title`} className="mt-1 font-serif text-[1.6rem] leading-tight font-medium tracking-[-0.01em]">
        {title}
      </h2>
      {intro && <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-ink-2">{intro}</p>}
      <div className="mt-7">{children}</div>
    </section>
  );
}

function Chips({ label, items }: { label: string; items: string[] }) {
  return (
    <p className="flex flex-wrap items-baseline gap-1.5 text-xs">
      <span className="w-12 shrink-0 text-ink-3">{label}</span>
      {items.map((item) => (
        <span key={item} className="rounded bg-sunken px-1.5 py-0.5 text-ink-2">
          {item}
        </span>
      ))}
    </p>
  );
}

function Orb({ children, chief = false }: { children: React.ReactNode; chief?: boolean }) {
  return (
    <span
      className={`flex size-10 shrink-0 items-center justify-center rounded-full border border-rule-strong ${
        chief ? "bg-primary-soft text-primary" : "bg-surface text-ink-2"
      }`}
    >
      {children}
    </span>
  );
}

export function TeamSection({ pipeline, reasoning }: { pipeline: Pipeline; reasoning: Reasoning | null }) {
  const { rules } = pipeline;
  return (
    <Section
      id="team"
      kicker="The agents"
      title="One orchestrator, four specialists"
      intro="Every agent is the same model, given a different role, the parts of the shared state it needs, and a structured form to answer in."
    >
      <div className="rounded-lg border border-rule bg-surface p-5">
        <div className="flex items-start gap-4">
          <Orb chief>
            <CompassIcon className="size-5" />
          </Orb>
          <div className="min-w-0">
            <p className="font-medium">
              Chief of Staff <span className="font-normal text-ink-3">· the orchestrator</span>
            </p>
            <ul className="mt-2 grid grid-cols-1 gap-x-8 gap-y-1.5 text-sm text-ink-2 sm:grid-cols-2">
              <li>Prepares the brief: plans the searches, keeps cited facts, asks up to {rules.max_questions} questions.</li>
              <li>Plans: states the decision and assigns the specialists it needs.</li>
              <li>Reviews each report against a rubric: {rules.approval_score} of 5 to pass.</li>
              <li>Names the competitors to profile, when deep research is on.</li>
              <li>Settles each conflict the specialists raise, and says who revises.</li>
              <li>Writes the launch strategy, in at most {rules.strategy_words} words.</li>
            </ul>
            <div className="mt-3 space-y-1">
              <Chips label="Reads" items={["your brief", "every report", "the conflicts"]} />
              <Chips label="Writes" items={["the plan", "the reviews", "the decisions", "the strategy"]} />
              <Chips label="Runs at" items={[`${reasoning?.chief ?? "medium"} reasoning`, "Azure OpenAI gpt-5-mini"]} />
            </div>
          </div>
        </div>
      </div>
      <ul className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {pipeline.specialists.map((specialist) => {
          const Glyph = SPECIALIST_ICONS[specialist.name];
          return (
            <li key={specialist.name} className="rounded-lg border border-rule bg-surface p-4">
              <div className="flex items-center gap-3">
                <Orb>
                  <Glyph className="size-[18px]" />
                </Orb>
                <p className="font-medium leading-snug">{specialist.title}</p>
              </div>
              <p className="mt-3 text-sm text-ink-2">Covers {specialist.focus}.</p>
              <div className="mt-3 space-y-1">
                <Chips
                  label="Reads"
                  items={[
                    "its task",
                    "your brief",
                    "its area's research",
                    ...(specialist.reads_competitors ? ["competitor profiles"] : []),
                  ]}
                />
                <Chips label="Writes" items={[`a report, ≤ ${rules.report_words} words`, "its conflicts"]} />
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-ink-3">
        The specialists run at {reasoning?.specialist ?? "minimal"} reasoning, set with the sidebar&apos;s sliders.
      </p>
    </Section>
  );
}

type Outcome = { when: string; then: string; tone?: "good" | "warn" };

const OUTCOME_TONE = { good: "bg-good-soft text-good", warn: "bg-warn-soft text-warn", none: "bg-sunken text-ink-2" };

export function DecisionsSection({ pipeline }: { pipeline: Pipeline }) {
  const { rules } = pipeline;
  const decisions: { step: string; question: string; answer: string; outcomes: Outcome[] }[] = [
    {
      step: "Before the team starts",
      question: "What must the founder tell us?",
      answer: `Only what you alone know (budget, team, traction, goals) and what would change the answer: at most ${rules.max_questions} questions, none when the brief is enough. It keeps at most ${rules.max_facts} facts from the web, each citing a real result.`,
      outcomes: [
        { when: "missing and decisive", then: "ask, with likely answers", tone: "warn" },
        { when: "in the brief already", then: "never ask", tone: "good" },
      ],
    },
    {
      step: "Plan",
      question: "Who works on this?",
      answer:
        "It states the decision to make, then assigns: all four specialists to judge a whole idea; for a narrower question, the one it asks about and the owner of the plan it touches. A follow-up reassigns only those it affects.",
      outcomes: [
        { when: "a whole idea", then: "all four" },
        { when: "a narrow question", then: "one or two" },
      ],
    },
    {
      step: "Review",
      question: "Is each report good enough?",
      answer: `It scores each report from 1 to 5 against its task and a rubric. The score decides, not the model's verdict: ${rules.approval_score} or more passes; below, the report goes back with feedback, ${rules.max_revisions === 1 ? "once" : `up to ${rules.max_revisions} times`}. One still below after that goes on, marked "not approved after revision".`,
      outcomes: [
        { when: `${rules.approval_score} or more`, then: "approved", tone: "good" },
        { when: `below ${rules.approval_score}`, then: "revise with feedback", tone: "warn" },
      ],
    },
    {
      step: "Cross-check and resolve",
      question: "Do the reports agree?",
      answer: `Each specialist reads the others' reports and raises a conflict where they clash. The Chief of Staff decides each one, and names the specialist who must revise to match: ${rules.max_critique_rounds === 1 ? "one round" : `${rules.max_critique_rounds} rounds`}.`,
      outcomes: [
        { when: "no conflicts", then: "on to the strategy", tone: "good" },
        { when: "a conflict", then: "a decision and a revision", tone: "warn" },
      ],
    },
    {
      step: "Strategy",
      question: "What is the decision?",
      answer: `Go, go with conditions, or not yet, and the main reason, using only what the specialists reported: the same figures everywhere, their citations kept, any missing report named. At most ${rules.strategy_words} words.`,
      outcomes: [
        { when: "the case holds", then: "go" },
        { when: "it holds if…", then: "go with conditions" },
        { when: "it does not yet", then: "not yet" },
      ],
    },
  ];
  return (
    <Section
      id="decisions"
      kicker="The orchestrator"
      title="How the Chief of Staff decides"
      intro="Five decisions shape every run. Each is a structured answer the code checks, and some are made by code rather than the model."
    >
      <ol className="relative space-y-6 before:absolute before:top-3 before:bottom-3 before:left-[13px] before:w-px before:bg-rule">
        {decisions.map((decision, index) => (
          <li key={decision.step} className="relative grid grid-cols-[28px_minmax(0,1fr)] gap-x-4">
            <span aria-hidden className="relative z-10 mt-0.5 flex size-7 items-center justify-center">
              <span className="absolute inset-1 rotate-45 rounded-[3px] border border-primary bg-paper" />
              <span className="relative text-[11px] font-medium text-primary tabular">{index + 1}</span>
            </span>
            <div className="max-w-3xl">
              <p className="kicker">{decision.step}</p>
              <p className="mt-0.5 font-serif text-lg leading-snug">{decision.question}</p>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{decision.answer}</p>
              <p className="mt-2.5 flex flex-wrap gap-2">
                {decision.outcomes.map((outcome) => (
                  <span
                    key={outcome.when}
                    className={`rounded-full px-2.5 py-0.5 text-xs ${OUTCOME_TONE[outcome.tone ?? "none"]}`}
                  >
                    {outcome.when} → <span className="font-medium">{outcome.then}</span>
                  </span>
                ))}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </Section>
  );
}

export function StateSection() {
  return (
    <Section
      id="state"
      kicker="The shared state"
      title="How information moves"
      intro="The agents never call each other. Each step reads what it needs from one shared state and writes its part back; LangGraph merges the parallel reports as they arrive, and keeps the state per session, so a follow-up starts from it."
    >
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[44rem] text-left text-sm">
          <caption className="sr-only">Which step reads and writes each part of the state</caption>
          <thead>
            <tr className="border-b border-rule-strong text-xs text-ink-3">
              <th className="py-2 pr-4 font-medium">
                <span className="flex items-center gap-2">
                  <StateIcon className="size-3.5" /> The state
                </span>
              </th>
              {STEPS.map((step) => (
                <th key={step} className="px-2 py-2 text-center font-medium">
                  {step}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {STATE.map((row) => (
              <tr key={row.field}>
                <th scope="row" className="py-2.5 pr-4 font-normal">
                  <span className="block font-medium">{row.field}</span>
                  <span className="block text-xs text-ink-3">{row.about}</span>
                </th>
                {row.cells.map((cell, index) => (
                  <td key={STEPS[index]} className="px-2 py-2.5 text-center">
                    {cell === "w" && (
                      <span className="inline-block size-3 rounded-full bg-primary" title="writes">
                        <span className="sr-only">writes</span>
                      </span>
                    )}
                    {cell === "r" && (
                      <span className="inline-block size-3 rounded-full border-[1.5px] border-ink-3" title="reads">
                        <span className="sr-only">reads</span>
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 flex gap-5 text-xs text-ink-3">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-full bg-primary" /> writes
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-full border-[1.5px] border-ink-3" /> reads
        </span>
      </p>
    </Section>
  );
}

function Card({
  icon,
  who,
  children,
  tone = "plain",
}: {
  icon: React.ReactNode;
  who: string;
  children: React.ReactNode;
  tone?: "plain" | "conflict" | "decision";
}) {
  const tones = {
    plain: "border-rule bg-surface",
    conflict: "border-warn/40 bg-warn-soft",
    decision: "border-primary/40 bg-primary-soft",
  };
  return (
    <div className={`rounded-lg border p-4 ${tones[tone]}`}>
      <p className="flex items-center gap-2 text-xs font-medium text-ink-2">
        {icon}
        {who}
      </p>
      <p className="mt-1.5 font-serif text-[15px] leading-snug text-ink">{children}</p>
    </div>
  );
}

function Down({ label }: { label: string }) {
  return (
    <p className="flex items-center gap-2 py-2 pl-5 text-xs text-ink-3">
      <span aria-hidden className="h-5 w-px bg-rule-strong" />
      {label}
    </p>
  );
}

export function CritiqueSection({ pipeline }: { pipeline: Pipeline }) {
  return (
    <Section
      id="critique"
      kicker="The critique"
      title="How the specialists check each other"
      intro="Review asks whether each report is good enough on its own. The cross-check asks whether they agree: a strategy built on two prices or two budgets is no decision at all."
    >
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="max-w-2xl">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Card icon={<ChartIcon className="size-3.5" />} who="Financial Planning">
              Charge $149 a month: 25 clinics cover the fixed costs.
            </Card>
            <Card icon={<MegaphoneIcon className="size-3.5" />} who="Marketing Strategy">
              Launch at $99 a month to win the first pilots fast.
            </Card>
          </div>
          <Down label="Each reads the other's report" />
          <Card icon={<SwapIcon className="size-3.5" />} who="Conflict: Financial Planning questions Marketing Strategy" tone="conflict">
            At $99 a month the pilot cannot cover the cost to serve.
          </Card>
          <Down label="The Chief of Staff decides" />
          <Card icon={<GavelIcon className="size-3.5" />} who="Decision: Marketing Strategy revises" tone="decision">
            Charge $149, with the first two months at $99.
          </Card>
          <Down label="The revision, then the strategy" />
          <Card icon={<MegaphoneIcon className="size-3.5" />} who="Marketing Strategy, revised">
            Launch at $149 a month, the first two months at $99.
          </Card>
        </div>
        <aside className="space-y-4 text-sm text-ink-2">
          <p>
            A conflict is a structured object: <span className="font-mono text-xs">raised_by</span>,{" "}
            <span className="font-mono text-xs">about</span> and <span className="font-mono text-xs">issue</span>. The
            same clash raised twice counts once.
          </p>
          <p>
            A decision names the conflict, what is decided and who must <span className="font-mono text-xs">revise</span>.
            A specialist with several decisions gets them all at once.
          </p>
          <p>
            There {pipeline.rules.max_critique_rounds === 1 ? "is one round" : `are ${pipeline.rules.max_critique_rounds} rounds`}
            : a report revised after the decision goes straight to the strategy, so no call is spent on a round that
            could change nothing.
          </p>
          <p className="flex gap-2 rounded-md bg-warn-soft p-3 text-warn">
            <HandIcon className="mt-0.5 size-4" />
            <span>A model settles these. Read the Conflicts tab and check each decision against your priorities.</span>
          </p>
        </aside>
      </div>
    </Section>
  );
}

export function ResearchSection({ pipeline }: { pipeline: Pipeline }) {
  const { rules } = pipeline;
  return (
    <Section
      id="research"
      kicker="The evidence"
      title="Where the facts come from"
      intro="The team can work from the web as well as from what the model knows, in two places, and every fact keeps its source."
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-rule bg-surface p-5">
          <p className="kicker">Before the team starts</p>
          <p className="mt-1 font-serif text-lg">The brief&apos;s research</p>
          <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm text-ink-2">
            <li>The Chief of Staff plans two to four searches.</li>
            <li>They run at once, and their results are pooled.</li>
            <li>It keeps up to {rules.max_facts} facts, each citing a real result, and drops the rest.</li>
            <li>You leave out any that do not fit, and every agent reads the others.</li>
          </ol>
        </div>
        <div className="rounded-lg border border-rule bg-surface p-5">
          <p className="kicker">With deep research on</p>
          <p className="mt-1 font-serif text-lg">Each specialist&apos;s research</p>
          <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm text-ink-2">
            <li>A research task per assigned specialist, from its own task.</li>
            <li>A profile of each of up to {rules.max_competitors} competitors the Chief of Staff names.</li>
            <li>All at once; one that fails leaves only its area without research.</li>
            <li>Each specialist reads its area&apos;s report; Marketing and Finance the profiles too.</li>
          </ol>
        </div>
      </div>
      <p className="mt-6 text-xs text-ink-3">
        Where research runs, chosen in the sidebar. Measured on one deep research run each, of four areas and three
        competitors.
      </p>
      <div className="relative mt-2 overflow-x-auto">
        <table className="w-full min-w-[36rem] text-left text-sm">
          <caption className="sr-only">Azure OpenAI and Tavily compared</caption>
          <thead>
            <tr className="border-b border-rule-strong text-xs text-ink-3">
              <th className="py-2 pr-4 font-medium" />
              <th className="py-2 pr-4 font-medium">Azure OpenAI (the default)</th>
              <th className="py-2 font-medium">Tavily (for demanding tasks)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {[
              ["How it searches", "Bing, through your own Azure deployment", "Its Search and Research APIs"],
              ["Deep research took", "45 s", "94 s"],
              ["What it cost", "42 Bing searches, billed to Azure", "209 of your 1,000 monthly credits"],
              ["Best for", "Everyday research", "The deepest, most demanding questions"],
            ].map(([what, azure, tavily]) => (
              <tr key={what}>
                <th scope="row" className="py-2.5 pr-4 font-normal text-ink-3">
                  {what}
                </th>
                <td className="py-2.5 pr-4">{azure}</td>
                <td className="py-2.5">{tavily}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 max-w-3xl text-sm text-ink-2">
        Every source gets one number for the whole session, the brief&apos;s first, so a{" "}
        <span className="font-mono text-xs">[3]</span> means the same page in a specialist&apos;s report, the strategy,
        the report and the PDF.
      </p>
    </Section>
  );
}

export function JudgementSection() {
  return (
    <Section
      id="judgement"
      kicker="You"
      title="Where your judgement matters"
      intro="The team is fast and thorough, but it does not know your business, it can be confidently wrong, and it decides nothing for you. These are the places to slow down."
    >
      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {JUDGEMENT.map((point) => (
          <li key={point.title} className="flex gap-3 rounded-lg border border-rule bg-surface p-4">
            <span aria-hidden className="flex size-8 shrink-0 items-center justify-center rounded-full bg-warn-soft text-warn">
              <HandIcon className="size-4" />
            </span>
            <div>
              <p className="font-medium">{point.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-ink-2">{point.why}</p>
              <p className="mt-1.5 text-xs text-ink-3">Where: {point.where}</p>
            </div>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export function StackSection() {
  return (
    <Section
      id="stack"
      kicker="The technology"
      title="What it is built with, and what each part does"
    >
      <ol className="relative space-y-2 before:absolute before:top-4 before:bottom-4 before:left-[15px] before:w-px before:bg-rule">
        {STACK.map((layer) => {
          const Glyph = LAYER_ICONS[layer.icon];
          return (
            <li key={layer.layer} className="relative grid grid-cols-[32px_minmax(0,1fr)] gap-x-4">
              <span
                aria-hidden
                className="relative z-10 flex size-8 items-center justify-center rounded-full border border-rule-strong bg-paper text-ink-2"
              >
                <Glyph className="size-4" />
              </span>
              <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 rounded-lg border border-rule bg-surface px-4 py-3 md:grid-cols-[9rem_minmax(0,1fr)]">
                <p className="font-medium">{layer.layer}</p>
                <div>
                  <p className="flex flex-wrap gap-1.5">
                    {layer.tools.map((tool) => (
                      <span key={tool} className="rounded border border-rule-strong px-1.5 py-0.5 text-xs text-ink">
                        {tool}
                      </span>
                    ))}
                  </p>
                  <p className="mt-1.5 text-sm text-ink-2">{layer.does}</p>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}

export function UserFlowSection() {
  return (
    <Section
      id="user-flow"
      kicker="Your path"
      title="From an idea to a document you can share"
    >
      <ol className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {USER_FLOW.map((step, index) => (
          <li key={step.title} className="flex gap-3">
            <span
              className={`relative flex size-8 shrink-0 items-center justify-center rounded-full border text-sm tabular ${
                step.yours ? "border-warn/50 bg-warn-soft text-warn" : "border-rule-strong bg-surface text-ink-2"
              }`}
            >
              {index + 1}
            </span>
            <div>
              <p className="font-medium">
                {step.title}
                {step.yours && <span className="ml-1.5 text-xs font-normal text-warn">your call</span>}
              </p>
              <p className="mt-0.5 text-sm text-ink-2">{step.does}</p>
            </div>
          </li>
        ))}
      </ol>
    </Section>
  );
}

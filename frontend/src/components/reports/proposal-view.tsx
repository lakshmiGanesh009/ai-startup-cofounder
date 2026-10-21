// The investment proposal on screen, a chapter at a time: text, tables and
// charts, numbered as the PDF numbers them. Figures the API calculates say so.

import { BarList, CashPosition, DATA_1, DATA_2, DATA_3, Funnel, Gantt, GroupedColumns, ramp, RiskMatrix, SEVERITY_FILL } from "@/components/reports/charts";
import { Markdown } from "@/components/markdown";
import { Badge, type Tone } from "@/components/ui/badge";
import { Notice } from "@/components/ui/notice";
import type { InvestmentMetrics, Kpi, Proposal } from "@/lib/api";
import {
  describeBreakEven,
  describeIrr,
  describePayback,
  money,
  monthRange,
  percent,
  severity,
  share,
  full,
  useCurrency,
} from "@/lib/proposal";

export type View = { proposal: Proposal; metrics: InvestmentMetrics; checks: string[] };

function Sub({
  number,
  title,
  note,
  children,
}: {
  number: string;
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title} className="mt-12 first:mt-0">
      <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="font-serif text-[1.3rem] leading-snug font-medium">
          <span className="mr-2.5 font-sans text-sm font-normal text-ink-3 tabular">{number}</span>
          {title}
        </h3>
        {note && <span className="text-xs text-ink-3">{note}</span>}
      </div>
      {children}
    </section>
  );
}

// Figures in a hairline grid.
function Figures({ items }: { items: [string, string, string][] }) {
  return (
    <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-rule bg-rule sm:grid-cols-2 lg:grid-cols-3">
      {items.map(([label, value, note]) => (
        <div key={label} className="bg-surface px-4 py-3.5">
          <dt className="kicker">{label}</dt>
          <dd className="mt-1 text-[1.6rem] leading-tight font-medium tracking-[-0.01em] tabular">{value}</dd>
          <dd className="mt-0.5 text-xs text-ink-3">{note}</dd>
        </div>
      ))}
    </dl>
  );
}

function Table({ head, rows, numeric = [] }: { head: string[]; rows: React.ReactNode[][]; numeric?: number[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-rule-strong">
            {head.map((cell, index) => (
              <th
                key={index}
                className={`py-2 pr-4 text-xs font-medium text-ink-3 ${numeric.includes(index) ? "text-right" : ""}`}
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">
          {rows.map((row, number) => (
            <tr key={number} className="align-top">
              {row.map((cell, index) => (
                <td
                  key={index}
                  className={`py-2.5 pr-4 ${index === 0 ? "font-medium text-ink" : "text-ink-2"} ${numeric.includes(index) ? "text-right tabular" : ""}`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// A passage set apart: the recommendation, the value proposition, the figures' meaning.
function Callout({ label, color, children }: { label: string; color: string; children: React.ReactNode }) {
  return (
    <div className="rounded-r-lg border-l-[3px] bg-surface py-4 pr-5 pl-5" style={{ borderLeftColor: color }}>
      <p className="kicker">{label}</p>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

const VERDICT_COLOR: Record<Proposal["executive"]["verdict"], string> = {
  Go: "var(--good)",
  "Go with conditions": "var(--warn)",
  "Not yet": "var(--bad)",
};

function snapshot(proposal: Proposal, metrics: InvestmentMetrics, currency: string): [string, string, string][] {
  const revenue = metrics.revenue;
  return [
    ["Total CapEx", money(metrics.capex, currency), "one-off, before launch"],
    [
      "Revenue, years 1–3",
      revenue.length ? `${money(revenue[0], currency)} → ${money(revenue[revenue.length - 1], currency)}` : "–",
      "from the Financial Planning Agent's drivers",
    ],
    ["NPV", money(metrics.npv, currency), `at a ${percent(proposal.financial.discount_rate)} discount rate`],
    ["IRR", ...describeIrr(metrics)],
    ["Payback", describePayback(metrics), "from the start of the project"],
    ["Break-even", describeBreakEven(metrics), "paying customers to cover the fixed costs"],
  ];
}

export function ExecutiveSection({ proposal, metrics }: View) {
  const currency = useCurrency();
  const e = proposal.executive;
  return (
    <div>
      <Callout label="Recommendation" color={VERDICT_COLOR[e.verdict]}>
        <p className="font-serif text-xl font-semibold" style={{ color: VERDICT_COLOR[e.verdict] }}>
          {e.verdict}
        </p>
        <div className="mt-2">
          <Markdown compact path="proposal.executive.recommendation">{e.recommendation}</Markdown>
        </div>
      </Callout>
      <div className="mt-12">
        <Sub number="1.1" title="Project overview">
          <Markdown path="proposal.executive.overview">{e.overview}</Markdown>
        </Sub>
        <Sub number="1.2" title="The opportunity">
          <Markdown path="proposal.executive.opportunity">{e.opportunity}</Markdown>
        </Sub>
        <Sub number="1.3" title="Strategic alignment">
          <Markdown path="proposal.executive.strategic_alignment">{e.strategic_alignment}</Markdown>
        </Sub>
        <Sub number="1.4" title="Financial snapshot" note="Calculated from the financial plan">
          <Figures items={snapshot(proposal, metrics, currency)} />
          <div className="mt-6">
            <Callout label="What the numbers say" color="var(--primary)">
              <Markdown compact path="proposal.executive.financial_case">{e.financial_case}</Markdown>
            </Callout>
          </div>
        </Sub>
      </div>
    </div>
  );
}

export function MarketSection({ proposal }: View) {
  const currency = useCurrency();
  const m = proposal.market;
  const sizes = [
    ["TAM", "Total addressable market", m.tam, ""],
    ["SAM", "Serviceable addressable market", m.sam, m.tam.value ? `${share(m.sam.value, m.tam.value)} of TAM` : ""],
    ["SOM", "Serviceable obtainable market", m.som, m.sam.value ? `${share(m.som.value, m.sam.value)} of SAM` : ""],
  ] as const;
  const budget = m.channels.reduce((sum, channel) => sum + channel.monthly_budget, 0);
  return (
    <div>
      <Sub number="2.1" title="Target audience and buyer personas">
        <Markdown path="proposal.market.personas">{m.personas}</Markdown>
      </Sub>
      <Sub number="2.2" title="Market size">
        <BarList
          keepOrder
          items={sizes.map(([short, , size, share], index) => ({
            label: short,
            value: size.value,
            color: ramp(index * 2, 5),
            note: share,
          }))}
        />
        <dl className="mt-5 space-y-2 text-sm">
          {sizes.map(([short, long, size]) => (
            <div key={short} className="grid grid-cols-1 gap-x-4 sm:grid-cols-[3.5rem_minmax(0,1fr)]">
              <dt className="font-medium" title={long}>
                {short}
              </dt>
              <dd className="text-ink-2">{size.basis}</dd>
            </div>
          ))}
        </dl>
      </Sub>
      <Sub number="2.3" title="Competitive landscape">
        <Table
          head={["Competitor", "Type", "Est. share", "Strengths", "Weaknesses"]}
          rows={m.competitors.map((c) => [c.name, c.kind, c.market_share, c.strengths, c.weaknesses])}
        />
      </Sub>
      <Sub number="2.4" title="Unique value proposition">
        <blockquote className="border-l-[3px] border-primary py-1 pl-5 font-serif text-[1.3rem] leading-snug text-ink">
          {m.value_proposition.replace(/\*\*/g, "")}
        </blockquote>
      </Sub>
      <Sub number="2.5" title="Go-to-market channels">
        <Table
          head={["Channel", "How it is used", "Monthly budget"]}
          numeric={[2]}
          rows={[
            ...m.channels.map((c) => [c.channel, c.approach, full(c.monthly_budget, currency)]),
            ["Total", "", <span key="v" className="font-medium text-ink">{full(budget, currency)}</span>],
          ]}
        />
        {m.channels.length > 1 && (
          <div className="mt-6 max-w-xl">
            <BarList items={m.channels.map((c) => ({ label: c.channel, value: c.monthly_budget }))} />
          </div>
        )}
      </Sub>
      <Sub number="2.6" title="Pricing strategy">
        <Markdown path="proposal.market.pricing_strategy">{m.pricing_strategy}</Markdown>
      </Sub>
      <Sub number="2.7" title="Sales funnel" note="Estimated monthly volumes at the end of year 1">
        <Funnel stages={m.funnel} />
      </Sub>
    </div>
  );
}

export function TechnicalSection({ proposal }: View) {
  const t = proposal.technical;
  const phases = [...t.roadmap].sort((a, b) => a.start_month - b.start_month);
  // Rounded, so fractions of a person add up as written: 0.1 + 0.2 is 0.3, not 0.30000000000000004.
  const fte = Number(t.staffing.reduce((sum, line) => sum + line.count, 0).toFixed(2));
  return (
    <div>
      <Sub number="3.1" title="Infrastructure">
        <Markdown path="proposal.technical.infrastructure">{t.infrastructure}</Markdown>
      </Sub>
      <Sub number="3.2" title="Technology stack">
        <Markdown path="proposal.technical.stack">{t.stack}</Markdown>
      </Sub>
      <Sub number="3.3" title="Scalability and performance">
        <Markdown path="proposal.technical.scalability">{t.scalability}</Markdown>
      </Sub>
      <Sub number="3.4" title="Implementation roadmap">
        <Gantt phases={phases} />
        <div className="mt-6">
          <Table
            head={["Phase", "Months", "Deliverables"]}
            rows={phases.map((p) => [p.name, monthRange(p.start_month, p.duration_months), p.deliverables])}
          />
        </div>
      </Sub>
      <Sub number="3.5" title="Resource and staffing plan">
        <Table
          head={["Role", "FTE", "When"]}
          numeric={[1]}
          rows={[...t.staffing.map((s) => [s.role, String(s.count), s.timing]), ["Total", <span key="v" className="font-medium text-ink">{fte}</span>, ""]]}
        />
      </Sub>
    </div>
  );
}

export function FinancialSection({ proposal, metrics, checks }: View) {
  const currency = useCurrency();
  const f = proposal.financial;
  const years = [...f.projections].sort((a, b) => a.year - b.year).slice(0, 3);
  const labels = years.map((year) => `Year ${year.year}`);
  const contribution = f.price_per_customer_month - f.variable_cost_per_customer_month;
  const flows = metrics.net_cash_flow;
  const cumulative = flows.map((_, index) => ({
    label: index ? `End of year ${index}` : "Start",
    value: flows.slice(0, index + 1).reduce((sum, cash) => sum + cash, 0),
  }));
  const row = (name: string, values: string[]) => [name, ...values];
  return (
    <div>
      {checks.length > 0 && (
        <Notice tone="warn" className="mb-10">
          <p className="font-medium">Checks on the figures, calculated from them</p>
          <ul className="mt-1 list-disc pl-4">
            {checks.map((check) => (
              <li key={check}>{check}</li>
            ))}
          </ul>
        </Notice>
      )}
      <Sub number="4.1" title="Capital and operating expenditures">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
          <div>
            <p className="mb-3 text-sm">
              <span className="font-medium">CapEx</span> <span className="text-ink-3">· {money(metrics.capex, currency)} one-off</span>
            </p>
            {/* Blue is revenue in this chapter and orange operating costs; one-off spend is neither. */}
            <BarList color="var(--ink-3)" items={f.capex.map((line) => ({ label: line.item, value: line.amount }))} />
          </div>
          <div>
            <p className="mb-3 text-sm">
              <span className="font-medium">OpEx at launch</span>{" "}
              <span className="text-ink-3">· {money(metrics.monthly_fixed_costs, currency)} a month</span>
            </p>
            <BarList color={DATA_2} items={f.monthly_opex.map((line) => ({ label: line.item, value: line.amount }))} />
          </div>
        </div>
      </Sub>
      <Sub number="4.2" title="Three-year projections">
        {years.length > 0 && (
          <GroupedColumns
            categories={labels}
            series={[
              { name: "Revenue", color: DATA_1, values: metrics.revenue },
              { name: "Operating costs", color: DATA_2, values: metrics.opex },
            ]}
          />
        )}
        <p className="mt-8 mb-2 kicker">Drivers from the Financial Planning Agent</p>
        <Table
          head={["", ...labels]}
          numeric={labels.map((_, index) => index + 1)}
          rows={[
            row("Paying customers (year end)", years.map((y) => y.customers.toLocaleString("en-US"))),
            row("Average paying customers", years.map((y) => String(Number(y.average_customers.toFixed(1))))),
            row("Fixed costs a month", years.map((y) => full(y.fixed_costs_month, currency))),
            row("One-off revenue", years.map((y) => full(y.one_off_revenue, currency))),
            row("Customer acquisition cost", years.map((y) => full(y.cac, currency))),
          ]}
        />
        <p className="mt-8 mb-1 kicker">Results</p>
        <p className="mb-2 text-xs text-ink-3">
          Calculated from the drivers: revenue = average customers × price × 12 + one-off revenue; OpEx = (fixed costs +
          average customers × cost to serve) × 12.
        </p>
        <Table
          head={["", ...labels]}
          numeric={labels.map((_, index) => index + 1)}
          rows={[
            row("Revenue", metrics.revenue.map((value) => full(value, currency))),
            row("Operating costs (OpEx), with the cost to serve", metrics.opex.map((value) => full(value, currency))),
            row("Net cash flow", metrics.net_cash_flow.slice(1).map((value) => full(value, currency))),
            row("Net margin", metrics.net_margin.map((margin) => (margin === null ? "–" : percent(margin)))),
          ]}
        />
      </Sub>
      <Sub number="4.3" title="Investment metrics" note="Calculated from the figures above">
        <Figures
          items={[
            ["NPV", money(metrics.npv, currency), `at a ${percent(f.discount_rate)} discount rate`],
            ["IRR", ...describeIrr(metrics)],
            ["Payback", describePayback(metrics), "cumulative cash back to zero"],
            ["Break-even", describeBreakEven(metrics), `at ${money(metrics.monthly_fixed_costs, currency)} fixed costs a month`],
            ["Contribution", `${money(contribution, currency)}/mo`, "per customer, after the cost to serve"],
            ["Price", `${money(f.price_per_customer_month, currency)}/mo`, `per customer; ${money(f.variable_cost_per_customer_month, currency)} to serve`],
          ]}
        />
        <div className="mt-10">
          <CashPosition
            points={cumulative}
            note={metrics.payback_months === null ? "Not paid back within three years" : `Paid back: ${describePayback(metrics).toLowerCase()}`}
          />
        </div>
      </Sub>
      <Sub number="4.4" title="Assumptions">
        <Markdown path="proposal.financial.assumptions">{f.assumptions}</Markdown>
      </Sub>
    </div>
  );
}

const LEVEL_TONE: Record<string, Tone> = { Low: "good", Medium: "warn", High: "bad" };

export function RiskSection({ proposal }: View) {
  const r = proposal.risk;
  const risks = r.risks.map((risk, index) => ({ ...risk, id: `R${index + 1}` }));
  return (
    <div>
      <Sub number="5.1" title="Data protection">
        <Markdown path="proposal.risk.data_protection">{r.data_protection}</Markdown>
      </Sub>
      <Sub number="5.2" title="Compliance">
        <Markdown path="proposal.risk.compliance">{r.compliance}</Markdown>
      </Sub>
      <Sub number="5.3" title="Risk matrix">
        <RiskMatrix risks={risks} />
        <ol className="mt-8 divide-y divide-rule border-y border-rule">
          {risks.map((risk) => {
            const level = severity(risk.probability, risk.impact);
            return (
              <li key={risk.id} className="grid grid-cols-1 gap-x-4 py-4 text-sm sm:grid-cols-[3rem_minmax(0,1fr)]">
                <span className="flex items-center gap-2 pt-0.5 sm:block">
                  <span className="font-semibold tabular">{risk.id}</span>
                  <span aria-hidden className="mt-1.5 block h-1 w-6 rounded-full" style={{ background: SEVERITY_FILL[level] }} />
                </span>
                <div>
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-xs text-ink-3">{risk.category}</span>
                    <Badge tone={LEVEL_TONE[risk.probability]}>Probability: {risk.probability}</Badge>
                    <Badge tone={LEVEL_TONE[risk.impact]}>Impact: {risk.impact}</Badge>
                    <span className="text-xs text-ink-3">Severity: {level}</span>
                  </p>
                  <p className="mt-1.5 font-medium text-ink">{risk.description}</p>
                  <p className="mt-1 text-ink-2">
                    <span className="text-ink-3">Mitigation.</span> {risk.mitigation}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      </Sub>
    </div>
  );
}

const KPI_COLORS: Record<Kpi["category"], string> = { Financial: DATA_1, Technical: DATA_2, Marketing: DATA_3 };

export function KpiSection({ proposal }: View) {
  const kpis = proposal.executive.kpis;
  const categories = (["Financial", "Technical", "Marketing"] as const).filter((category) =>
    kpis.some((kpi) => kpi.category === category),
  );
  return (
    <div className="grid grid-cols-1 gap-10 md:grid-cols-3">
      {categories.map((category) => (
        <section key={category} aria-label={`${category} metrics`}>
          <h3 className="flex items-center gap-2 border-b border-rule-strong pb-2 text-sm font-medium">
            <span aria-hidden className="size-2.5 rounded-[2px]" style={{ background: KPI_COLORS[category] }} />
            {category}
          </h3>
          <ul className="divide-y divide-rule">
            {kpis
              .filter((kpi) => kpi.category === category)
              .map((kpi) => (
                <li key={kpi.metric} className="py-3 text-sm">
                  <p className="font-medium text-ink">{kpi.metric}</p>
                  <p className="mt-0.5 text-ink-2">{kpi.target.replace(/\*\*/g, "")}</p>
                </li>
              ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

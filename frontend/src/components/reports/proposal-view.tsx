// The investment proposal on screen, one section at a time: text, tables and
// charts, each marked with the agent it came from, or "calculated" for the
// figures the API works out.

import { BarList, BLUE, CashPosition, Funnel, Gantt, GroupedColumns, ORANGE, ramp, RiskMatrix, SEVERITY_STYLE } from "@/components/reports/charts";
import { Markdown } from "@/components/markdown";
import { Badge, type Tone } from "@/components/ui/badge";
import type { InvestmentMetrics, Kpi, Proposal } from "@/lib/api";
import {
  describeBreakEven,
  describeIrr,
  describePayback,
  money,
  PART_AGENTS,
  percent,
  severity,
  usd,
} from "@/lib/proposal";

type View = { proposal: Proposal; metrics: InvestmentMetrics; checks: string[] };

function Source({ part }: { part: keyof Proposal }) {
  return <Badge>Written by the {PART_AGENTS[part]}</Badge>;
}

function Calculated({ what }: { what: string }) {
  return <Badge tone="gray">Calculated {what}</Badge>;
}

function Heading({ children, badge }: { children: React.ReactNode; badge?: React.ReactNode }) {
  return (
    <div className="mt-8 mb-3 flex flex-wrap items-center gap-3 first:mt-0">
      <h3 className="text-base font-semibold">{children}</h3>
      {badge}
    </div>
  );
}

function Tiles({ items }: { items: [string, string, string][] }) {
  return (
    <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map(([label, value, note]) => (
        <div key={label} className="rounded-lg border border-zinc-200 bg-surface p-4 dark:border-zinc-800">
          <dt className="text-xs tracking-wide text-zinc-500 uppercase">{label}</dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
          <dd className="mt-1 text-xs text-zinc-500">{note}</dd>
        </div>
      ))}
    </dl>
  );
}

function Table({ head, rows, numeric = [] }: { head: string[]; rows: React.ReactNode[][]; numeric?: number[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="bg-accent-soft/40 text-xs text-navy uppercase dark:bg-accent/15 dark:text-accent-soft">
          <tr>
            {head.map((cell, index) => (
              <th key={index} className={`px-3 py-2 font-semibold ${numeric.includes(index) ? "text-right" : ""}`}>
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
          {rows.map((row, number) => (
            <tr key={number} className="align-top">
              {row.map((cell, index) => (
                <td key={index} className={`px-3 py-2 ${numeric.includes(index) ? "text-right tabular-nums" : ""}`}>
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

const VERDICT: Record<Proposal["executive"]["verdict"], { tone: string; badge: Tone }> = {
  Go: { tone: "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/40", badge: "green" },
  "Go with conditions": { tone: "border-amber-400 bg-amber-50 dark:bg-amber-950/40", badge: "amber" },
  "Not yet": { tone: "border-red-500 bg-red-50 dark:bg-red-950/40", badge: "red" },
};

function snapshot(proposal: Proposal, metrics: InvestmentMetrics): [string, string, string][] {
  const years = metrics.revenue_usd;
  return [
    ["Total CapEx", money(metrics.capex_usd), "one-off, before launch"],
    [
      "Revenue, years 1-3",
      years.length ? `${money(years[0])} → ${money(years[years.length - 1])}` : "-",
      "from the Financial Planning Agent's drivers",
    ],
    ["NPV", money(metrics.npv_usd), `at a ${percent(proposal.financial.discount_rate)} discount rate`],
    ["IRR", ...describeIrr(metrics)],
    ["Payback", describePayback(metrics), "from the start of the project"],
    ["Break-even", describeBreakEven(metrics), "paying customers to cover the fixed costs"],
  ];
}

export function ExecutiveSection({ proposal, metrics }: View) {
  const e = proposal.executive;
  return (
    <div>
      <Source part="executive" />
      <div className={`mt-4 rounded-lg border-l-4 p-4 ${VERDICT[e.verdict].tone}`}>
        <p className="mb-1 flex items-center gap-2 font-semibold">
          Recommendation <Badge tone={VERDICT[e.verdict].badge}>{e.verdict}</Badge>
        </p>
        <Markdown>{e.recommendation}</Markdown>
      </div>
      <Heading>Project overview</Heading>
      <Markdown>{e.overview}</Markdown>
      <Heading>The opportunity</Heading>
      <Markdown>{e.opportunity}</Markdown>
      <Heading>Strategic alignment</Heading>
      <Markdown>{e.strategic_alignment}</Markdown>
      <Heading badge={<Calculated what="from the financial plan" />}>Financial snapshot</Heading>
      <Tiles items={snapshot(proposal, metrics)} />
      <div className="mt-4 rounded-lg border-l-4 border-accent bg-accent-soft/30 p-4 dark:bg-accent/10">
        <p className="mb-1 font-semibold">What the numbers say</p>
        <Markdown>{e.financial_case}</Markdown>
      </div>
    </div>
  );
}

export function MarketSection({ proposal }: View) {
  const m = proposal.market;
  const sizes = [
    ["TAM", "Total addressable market", m.tam, ""],
    ["SAM", "Serviceable addressable market", m.sam, m.tam.value_usd ? `${((m.sam.value_usd / m.tam.value_usd) * 100).toFixed(1)}% of TAM` : ""],
    ["SOM", "Serviceable obtainable market", m.som, m.sam.value_usd ? `${((m.som.value_usd / m.sam.value_usd) * 100).toFixed(1)}% of SAM` : ""],
  ] as const;
  const budget = m.channels.reduce((sum, channel) => sum + channel.monthly_budget_usd, 0);
  return (
    <div>
      <Source part="market" />
      <Heading>Target audience and buyer personas</Heading>
      <Markdown>{m.personas}</Markdown>
      <Heading>Market size</Heading>
      <BarList
        keepOrder
        items={sizes.map(([short, , size, share], index) => ({
          label: short,
          value: size.value_usd,
          color: ramp(index * 2, 5),
          note: share,
        }))}
      />
      <ul className="mt-3 space-y-1 text-sm text-zinc-700 dark:text-zinc-300">
        {sizes.map(([short, long, size]) => (
          <li key={short}>
            <span className="font-semibold">{short}</span> ({long}): {size.basis}
          </li>
        ))}
      </ul>
      <Heading>Competitive landscape</Heading>
      <Table
        head={["Competitor", "Type", "Est. share", "Strengths", "Weaknesses"]}
        rows={m.competitors.map((c) => [c.name, c.kind, c.market_share, c.strengths, c.weaknesses])}
      />
      <Heading>Unique value proposition</Heading>
      <div className="rounded-lg border-l-4 border-accent bg-accent-soft/30 p-4 dark:bg-accent/10">
        <Markdown>{m.value_proposition}</Markdown>
      </div>
      <Heading>Go-to-market channels</Heading>
      <Table
        head={["Channel", "How it is used", "Monthly budget"]}
        numeric={[2]}
        rows={[
          ...m.channels.map((c) => [c.channel, c.approach, usd(c.monthly_budget_usd)]),
          [<strong key="t">Total</strong>, "", <strong key="v">{usd(budget)}</strong>],
        ]}
      />
      {m.channels.length > 1 && (
        <div className="mt-4">
          <BarList items={m.channels.map((c) => ({ label: c.channel, value: c.monthly_budget_usd }))} />
        </div>
      )}
      <Heading>Pricing strategy</Heading>
      <Markdown>{m.pricing_strategy}</Markdown>
      <Heading badge={<Badge tone="amber">Estimated monthly volumes at the end of year 1</Badge>}>Sales funnel</Heading>
      <Funnel stages={m.funnel} />
    </div>
  );
}

export function TechnicalSection({ proposal }: View) {
  const t = proposal.technical;
  const phases = [...t.roadmap].sort((a, b) => a.start_month - b.start_month);
  const fte = t.staffing.reduce((sum, line) => sum + line.count, 0);
  return (
    <div>
      <Source part="technical" />
      <Heading>Infrastructure</Heading>
      <Markdown>{t.infrastructure}</Markdown>
      <Heading>Technology stack</Heading>
      <Markdown>{t.stack}</Markdown>
      <Heading>Scalability and performance</Heading>
      <Markdown>{t.scalability}</Markdown>
      <Heading>Implementation roadmap</Heading>
      <Gantt phases={phases} />
      <div className="mt-4">
        <Table
          head={["Phase", "Months", "Deliverables"]}
          rows={phases.map((p) => [p.name, `${p.start_month}-${p.start_month + p.duration_months - 1}`, p.deliverables])}
        />
      </div>
      <Heading>Resource and staffing plan</Heading>
      <Table
        head={["Role", "FTE", "When"]}
        numeric={[1]}
        rows={[...t.staffing.map((s) => [s.role, String(s.count), s.timing]), [<strong key="t">Total</strong>, <strong key="v">{fte}</strong>, ""]]}
      />
    </div>
  );
}

export function FinancialSection({ proposal, metrics, checks }: View) {
  const f = proposal.financial;
  const years = [...f.projections].sort((a, b) => a.year - b.year).slice(0, 3);
  const labels = years.map((year) => `Year ${year.year}`);
  const contribution = f.price_per_customer_month_usd - f.variable_cost_per_customer_month_usd;
  const flows = metrics.net_cash_flow_usd;
  const cumulative = flows.map((_, index) => ({
    label: index ? `End of year ${index}` : "Start",
    value: flows.slice(0, index + 1).reduce((sum, cash) => sum + cash, 0),
  }));
  const row = (name: string, values: string[]) => [name, ...values];
  return (
    <div>
      <Source part="financial" />
      {checks.length > 0 && (
        <div role="note" className="mt-4 rounded-lg border-l-4 border-amber-400 bg-amber-50 p-4 text-sm dark:bg-amber-950/40">
          <p className="font-semibold">Checks on the figures (calculated from them)</p>
          <ul className="mt-1 list-disc pl-5">
            {checks.map((check) => (
              <li key={check}>{check}</li>
            ))}
          </ul>
        </div>
      )}
      <Heading>Capital and operating expenditures</Heading>
      <div className="grid gap-8 md:grid-cols-2">
        <div>
          <p className="mb-3 text-sm font-semibold">CapEx: {money(metrics.capex_usd)} one-off</p>
          <BarList items={f.capex.map((line) => ({ label: line.item, value: line.amount_usd }))} />
        </div>
        <div>
          <p className="mb-3 text-sm font-semibold">OpEx at launch: {money(metrics.monthly_fixed_costs_usd)} a month</p>
          <BarList color={ORANGE} items={f.monthly_opex.map((line) => ({ label: line.item, value: line.amount_usd }))} />
        </div>
      </div>
      <Heading>Three-year projections</Heading>
      {years.length > 0 && (
        <GroupedColumns
          categories={labels}
          series={[
            { name: "Revenue", color: BLUE, values: metrics.revenue_usd },
            { name: "Operating costs", color: ORANGE, values: metrics.opex_usd },
          ]}
        />
      )}
      <p className="mt-5 mb-2 text-sm font-semibold">Drivers from the Financial Planning Agent</p>
      <Table
        head={["", ...labels]}
        numeric={labels.map((_, index) => index + 1)}
        rows={[
          row("Paying customers (year end)", years.map((y) => y.customers.toLocaleString("en-US"))),
          row("Average paying customers", years.map((y) => String(Number(y.average_customers.toFixed(1))))),
          row("Fixed costs a month", years.map((y) => usd(y.fixed_costs_month_usd))),
          row("One-off revenue", years.map((y) => usd(y.one_off_revenue_usd))),
          row("Customer acquisition cost", years.map((y) => usd(y.cac_usd))),
        ]}
      />
      <div className="mt-5 mb-2 flex flex-wrap items-center gap-3">
        <p className="text-sm font-semibold">Results</p>
        <Calculated what="from the drivers: revenue = average customers × price × 12 + one-off revenue; OpEx = (fixed costs + average customers × cost to serve) × 12" />
      </div>
      <Table
        head={["", ...labels]}
        numeric={labels.map((_, index) => index + 1)}
        rows={[
          row("Revenue", metrics.revenue_usd.map(usd)),
          row("Operating costs (OpEx), with the cost to serve", metrics.opex_usd.map(usd)),
          row("Net cash flow", metrics.net_cash_flow_usd.slice(1).map(usd)),
          row("Net margin", metrics.net_margin.map((margin) => (margin === null ? "-" : percent(margin)))),
        ]}
      />
      <Heading badge={<Calculated what="from the figures above" />}>Investment metrics</Heading>
      <Tiles
        items={[
          ["NPV", money(metrics.npv_usd), `at a ${percent(f.discount_rate)} discount rate`],
          ["IRR", ...describeIrr(metrics)],
          ["Payback", describePayback(metrics), "cumulative cash back to zero"],
          ["Break-even", describeBreakEven(metrics), `at ${money(metrics.monthly_fixed_costs_usd)} fixed costs a month`],
          ["Contribution", `${money(contribution)}/mo`, "per customer, after the cost to serve"],
          ["Price", `${money(f.price_per_customer_month_usd)}/mo`, `per customer; ${money(f.variable_cost_per_customer_month_usd)} to serve`],
        ]}
      />
      <div className="mt-6">
        <CashPosition
          points={cumulative}
          note={metrics.payback_months === null ? "Not paid back within three years" : `Paid back: ${describePayback(metrics).toLowerCase()}`}
        />
      </div>
      <Heading>Assumptions</Heading>
      <Markdown>{f.assumptions}</Markdown>
    </div>
  );
}

const LEVEL_TONE: Record<string, Tone> = { Low: "green", Medium: "amber", High: "red" };

export function RiskSection({ proposal }: View) {
  const r = proposal.risk;
  const risks = r.risks.map((risk, index) => ({ ...risk, id: `R${index + 1}` }));
  return (
    <div>
      <Source part="risk" />
      <Heading>Data protection</Heading>
      <Markdown>{r.data_protection}</Markdown>
      <Heading>Compliance</Heading>
      <Markdown>{r.compliance}</Markdown>
      <Heading>Risk matrix</Heading>
      <RiskMatrix risks={risks} />
      <ul className="mt-5 space-y-3">
        {risks.map((risk) => {
          const level = severity(risk.probability, risk.impact);
          return (
            <li key={risk.id} className="flex overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
              <span aria-hidden className={`w-1.5 shrink-0 ${SEVERITY_STYLE[level]}`} />
              <div className="p-4 text-sm">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">
                    {risk.id} · {risk.category}
                  </span>
                  <Badge tone={LEVEL_TONE[risk.probability]}>Probability: {risk.probability}</Badge>
                  <Badge tone={LEVEL_TONE[risk.impact]}>Impact: {risk.impact}</Badge>
                  <Badge tone="gray">Severity: {level}</Badge>
                </p>
                <p className="mt-2 font-semibold">{risk.description}</p>
                <p className="mt-1 text-zinc-700 dark:text-zinc-300">
                  <span className="font-medium">Mitigation:</span> {risk.mitigation}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const KPI_COLORS: Record<Kpi["category"], string> = { Financial: BLUE, Technical: ORANGE, Marketing: "#1baf7a" };

export function KpiSection({ proposal }: View) {
  const kpis = proposal.executive.kpis;
  const categories = (["Financial", "Technical", "Marketing"] as const).filter((category) =>
    kpis.some((kpi) => kpi.category === category),
  );
  return (
    <div>
      <Source part="executive" />
      <div className="mt-4 grid gap-6 md:grid-cols-3">
        {categories.map((category) => (
          <section key={category} aria-label={`${category} metrics`}>
            <h3 className="mb-3 flex items-center gap-2 font-semibold">
              <span aria-hidden className="size-2.5 rounded-sm" style={{ background: KPI_COLORS[category] }} />
              {category}
            </h3>
            <ul className="space-y-2">
              {kpis
                .filter((kpi) => kpi.category === category)
                .map((kpi) => (
                  <li
                    key={kpi.metric}
                    className="rounded-md border border-l-4 border-zinc-200 p-3 text-sm dark:border-zinc-800"
                    style={{ borderLeftColor: KPI_COLORS[category] }}
                  >
                    <p className="font-semibold">{kpi.metric}</p>
                    <p className="text-zinc-600 dark:text-zinc-400">{kpi.target}</p>
                  </li>
                ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

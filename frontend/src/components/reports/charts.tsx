// The proposal's charts, drawn with plain HTML and CSS. Every mark carries a
// visible value and a tooltip with the exact figure; colours come from the
// app's tokens (globals.css): blue for one series, blue and orange for two, a
// light-to-dark blue ramp for ordered stages, red only for cash below zero.

import type { Level } from "@/lib/api";
import { full, LEVELS, money, monthRange, type Severity, severity, useCurrency } from "@/lib/proposal";

export const DATA_1 = "var(--data-1)";
export const DATA_2 = "var(--data-2)";
export const DATA_3 = "var(--data-3)";
const NEGATIVE = "var(--data-negative)";
const RAMP = ["var(--ramp-1)", "var(--ramp-2)", "var(--ramp-3)", "var(--ramp-4)", "var(--ramp-5)"];

export function ramp(index: number, count: number): string {
  return RAMP[Math.round((index * (RAMP.length - 1)) / Math.max(count - 1, 1))];
}

export type Bar = { label: string; value: number; color?: string; note?: string };

// A bar per item, largest first unless `keepOrder`, each with its value.
export function BarList({ items, color = DATA_1, keepOrder = false }: { items: Bar[]; color?: string; keepOrder?: boolean }) {
  const currency = useCurrency();
  const rows = keepOrder ? items : [...items].sort((a, b) => b.value - a.value);
  const largest = Math.max(1, ...rows.map((row) => row.value));
  return (
    <ul className="space-y-3">
      {rows.map((row) => (
        <li key={row.label} className="text-sm">
          <div className="flex items-baseline justify-between gap-4">
            <span className="text-ink-2">{row.label}</span>
            <span className="font-medium text-ink tabular">
              {money(row.value, currency)}
              {row.note && <span className="ml-2 text-xs font-normal text-ink-3">{row.note}</span>}
            </span>
          </div>
          <div className="mt-1.5 h-1.5 rounded-full bg-sunken">
            <div
              className="h-full rounded-full"
              title={`${row.label}: ${full(row.value, currency)}`}
              style={{ width: `${Math.max(0.6, (Math.max(row.value, 0) / largest) * 100)}%`, background: row.color ?? color }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

// The sales funnel: a centred bar per stage, width to scale, with each stage's
// volume and how many of the stage before convert.
export function Funnel({ stages }: { stages: { stage: string; monthly_volume: number }[] }) {
  const largest = Math.max(1, ...stages.map((stage) => stage.monthly_volume));
  return (
    <ol className="space-y-1">
      {stages.map((stage, index) => {
        const before = index ? stages[index - 1].monthly_volume : 0;
        const volume = Number(stage.monthly_volume.toFixed(1)).toLocaleString("en-US");
        const conversion = before ? `${Math.round((stage.monthly_volume / before) * 100)}% convert` : "";
        return (
          <li key={stage.stage} className="grid grid-cols-[minmax(6rem,12rem)_minmax(0,1fr)_6.5rem] items-center gap-4 text-sm">
            <span className="text-ink-2">{stage.stage}</span>
            <div className="flex justify-center">
              <div
                className="h-7 rounded-sm"
                title={`${stage.stage}: ${volume} a month${conversion ? `, ${conversion}` : ""}`}
                style={{ width: `${Math.max(2, (stage.monthly_volume / largest) * 100)}%`, background: ramp(index, stages.length) }}
              />
            </div>
            <span className="text-right">
              <span className="font-medium tabular">{volume}</span>
              {conversion && <span className="block text-xs text-ink-3">{conversion}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// The roadmap: a row per phase on a timeline marked every three months, with
// the months each spans under its name. A phase is at least a month long.
export function Gantt({ phases }: { phases: { name: string; start_month: number; duration_months: number }[] }) {
  const rows = phases.map((phase) => ({
    name: phase.name,
    start: Math.max(phase.start_month, 1),
    length: Math.max(Math.ceil(phase.duration_months), 1),
    span: monthRange(phase.start_month, phase.duration_months),
  }));
  const last = Math.max(3, ...rows.map((row) => row.start + row.length - 1));
  const months = Math.ceil(last / 3) * 3;
  const marks = Array.from({ length: months / 3 + 1 }, (_, index) => index * 3);
  return (
    <div className="text-sm">
      <div className="grid grid-cols-[minmax(7rem,13rem)_minmax(0,1fr)] gap-4">
        <span />
        <div className="relative h-5 text-[11px] text-ink-3 tabular">
          {marks.slice(0, -1).map((month) => (
            <span key={month} className="absolute" style={{ left: `${(month / months) * 100}%` }}>
              M{month + 1}
            </span>
          ))}
        </div>
      </div>
      <ul>
        {rows.map((row) => (
          <li key={row.name} className="grid grid-cols-[minmax(7rem,13rem)_minmax(0,1fr)] items-center gap-4 border-t border-rule py-2">
            <span>
              <span className="block text-ink-2">{row.name}</span>
              <span className="block text-xs text-ink-3 tabular">
                {row.span.includes("–") ? "Months" : "Month"} {row.span}
              </span>
            </span>
            <div className="relative h-5">
              {marks.map((month) => (
                <span
                  key={month}
                  aria-hidden
                  className="absolute inset-y-0 w-px bg-rule"
                  style={{ left: `${(month / months) * 100}%` }}
                />
              ))}
              <div
                className="absolute inset-y-0.5 rounded-sm"
                title={`${row.name}: ${row.span.includes("–") ? "months" : "month"} ${row.span}`}
                style={{
                  left: `${((row.start - 1) / months) * 100}%`,
                  width: `${(row.length / months) * 100}%`,
                  background: DATA_1,
                }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Legend({ entries }: { entries: { name: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap gap-4 text-xs text-ink-2">
      {entries.map((entry) => (
        <span key={entry.name} className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-[2px]" style={{ background: entry.color }} />
          {entry.name}
        </span>
      ))}
    </div>
  );
}

// Columns grouped by category, one colour per series, each with its value.
export function GroupedColumns({
  categories,
  series,
}: {
  categories: string[];
  series: { name: string; color: string; values: number[] }[];
}) {
  const currency = useCurrency();
  const largest = Math.max(1, ...series.flatMap((one) => one.values));
  return (
    <figure>
      <Legend entries={series} />
      <div className="mt-4 flex h-52 items-end gap-8 border-b border-rule-strong px-2">
        {categories.map((category, index) => (
          <div key={category} className="flex h-full flex-1 items-end justify-center gap-1.5">
            {series.map((one) => (
              <div key={one.name} className="flex h-full w-9 flex-col items-center justify-end sm:w-12">
                <span className="mb-1 text-[11px] text-ink-2 tabular">{money(one.values[index], currency)}</span>
                <div
                  className="w-full rounded-t-[3px]"
                  title={`${category}, ${one.name}: ${full(one.values[index], currency)}`}
                  style={{ height: `${(Math.max(one.values[index], 0) / largest) * 82}%`, background: one.color }}
                />
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-8 px-2">
        {categories.map((category) => (
          <span key={category} className="flex-1 text-center text-xs text-ink-3">
            {category}
          </span>
        ))}
      </div>
    </figure>
  );
}

// The cumulative cash position, above or below zero.
export function CashPosition({ points, note }: { points: { label: string; value: number }[]; note: string }) {
  const currency = useCurrency();
  const top = Math.max(0, ...points.map((point) => point.value));
  const bottom = Math.min(0, ...points.map((point) => point.value));
  const span = top - bottom || 1;
  const zero = (top / span) * 100;
  return (
    <figure>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Legend
          entries={[
            { name: "Cash position above zero", color: DATA_1 },
            { name: "Below zero", color: NEGATIVE },
          ]}
        />
        <p className="text-sm font-medium">{note}</p>
      </div>
      <div className="relative mt-6 flex h-48 gap-4 px-2">
        <div aria-hidden className="absolute inset-x-0 border-t border-rule-strong" style={{ top: `${zero}%` }} />
        {points.map((point) => {
          const height = (Math.abs(point.value) / span) * 100;
          const above = point.value >= 0;
          return (
            <div key={point.label} className="relative flex-1">
              <div
                className="absolute inset-x-[30%] rounded-[3px]"
                title={`${point.label}: ${full(point.value, currency)}`}
                style={{
                  top: above ? `${zero - height}%` : `${zero}%`,
                  height: `${Math.max(height, 0.5)}%`,
                  background: above ? DATA_1 : NEGATIVE,
                }}
              />
              <span
                className="absolute inset-x-0 text-center text-[11px] font-medium text-ink-2 tabular"
                style={above ? { bottom: `${100 - zero + height + 2}%` } : { top: `${zero + height + 2}%` }}
              >
                {money(point.value, currency)}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-6 flex gap-4 px-2">
        {points.map((point) => (
          <span key={point.label} className="flex-1 text-center text-xs text-ink-3">
            {point.label}
          </span>
        ))}
      </div>
    </figure>
  );
}

export const SEVERITY_FILL: Record<Severity, string> = {
  Low: "var(--sev-low)",
  Moderate: "var(--sev-moderate)",
  High: "var(--sev-high)",
  Critical: "var(--sev-critical)",
};

// Risks placed by probability (across) and impact (up), the cells shaded by severity.
export function RiskMatrix({ risks }: { risks: { id: string; probability: Level; impact: Level }[] }) {
  return (
    <figure className="flex flex-wrap items-start gap-x-10 gap-y-6">
      <div className="grid grid-cols-[auto_repeat(3,minmax(4.5rem,7.5rem))] gap-1 text-xs">
        <span className="pr-2 pb-0.5 text-right text-[11px] font-medium text-ink-2">Impact</span>
        <span className="col-span-3" />
        {[...LEVELS].reverse().map((impact) => (
          <div key={impact} className="contents">
            <span className="self-center pr-2 text-right text-ink-3">{impact}</span>
            {LEVELS.map((probability) => {
              const here = risks.filter((risk) => risk.probability === probability && risk.impact === impact);
              const level = severity(probability, impact);
              return (
                <div
                  key={probability}
                  title={`Probability ${probability}, impact ${impact}: ${level}`}
                  className="flex min-h-14 flex-wrap content-center items-center justify-center gap-1 rounded-sm p-1.5"
                  style={{ background: SEVERITY_FILL[level] }}
                >
                  {here.map((risk) => (
                    <span key={risk.id} className="rounded-full bg-ink px-1.5 py-px text-[10px] font-semibold text-paper tabular">
                      {risk.id}
                    </span>
                  ))}
                </div>
              );
            })}
          </div>
        ))}
        <span />
        {LEVELS.map((probability) => (
          <span key={probability} className="pt-1 text-center text-ink-3">
            {probability}
          </span>
        ))}
        <span />
        <span className="col-span-3 text-center text-[11px] font-medium text-ink-2">Probability</span>
      </div>
      <figcaption className="space-y-1.5 text-xs text-ink-2">
        <p className="kicker">Severity</p>
        {(["Low", "Moderate", "High", "Critical"] as Severity[]).map((level) => (
          <p key={level} className="flex items-center gap-2">
            <span aria-hidden className="size-3 rounded-[2px]" style={{ background: SEVERITY_FILL[level] }} />
            {level}
          </p>
        ))}
      </figcaption>
    </figure>
  );
}

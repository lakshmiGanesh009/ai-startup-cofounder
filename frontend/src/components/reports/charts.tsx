// The proposal's charts, drawn with plain HTML and CSS. Each mark has a visible
// label and a tooltip with the exact figure, and the colours follow the PDF's:
// blue for one series, blue and orange for two, a light-to-dark blue ramp for
// ordered stages, red only for a cash position below zero.

import type { Level } from "@/lib/api";
import { LEVELS, money, type Severity, severity, usd } from "@/lib/proposal";

export const BLUE = "#2a78d6";
export const ORANGE = "#eb6834";
const NEGATIVE = "#e34948";
const RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"];

export function ramp(index: number, count: number): string {
  return RAMP[Math.round((index * (RAMP.length - 1)) / Math.max(count - 1, 1))];
}

export type Bar = { label: string; value: number; color?: string; note?: string };

// A horizontal bar per item, largest first unless `keepOrder`, each labelled with its value.
export function BarList({ items, color = BLUE, keepOrder = false }: { items: Bar[]; color?: string; keepOrder?: boolean }) {
  const rows = keepOrder ? items : [...items].sort((a, b) => b.value - a.value);
  const largest = Math.max(1, ...rows.map((row) => row.value));
  return (
    <ul className="space-y-2.5">
      {rows.map((row) => (
        <li key={row.label} className="text-sm">
          <div className="mb-1 flex justify-between gap-3">
            <span>{row.label}</span>
            {row.note && <span className="text-right text-xs text-zinc-500">{row.note}</span>}
          </div>
          <div className="flex items-center gap-2">
            <div
              className="h-3 rounded-r"
              title={`${row.label}: ${usd(row.value)}`}
              style={{ width: `${Math.max(0.5, (Math.max(row.value, 0) / largest) * 85)}%`, background: row.color ?? color }}
            />
            <span className="text-xs font-semibold tabular-nums">{money(row.value)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

// The sales funnel: a centred bar per stage, width to scale, with each
// stage's volume and its conversion from the stage before.
export function Funnel({ stages }: { stages: { stage: string; monthly_volume: number }[] }) {
  const largest = Math.max(1, ...stages.map((stage) => stage.monthly_volume));
  return (
    <ol className="space-y-1.5">
      {stages.map((stage, index) => {
        const before = index ? stages[index - 1].monthly_volume : 0;
        const volume = Number(stage.monthly_volume.toFixed(1)).toLocaleString("en-US");
        const note = before ? `${volume} a month · ${Math.round((stage.monthly_volume / before) * 100)}% convert` : `${volume} a month`;
        return (
          <li key={stage.stage} className="grid grid-cols-[minmax(6rem,11rem)_1fr_minmax(8rem,13rem)] items-center gap-3 text-sm">
            <span className="font-medium">{stage.stage}</span>
            <div className="flex justify-center">
              <div
                className="h-6 rounded"
                title={`${stage.stage}: ${note}`}
                style={{ width: `${Math.max(3, (stage.monthly_volume / largest) * 100)}%`, background: ramp(index, stages.length) }}
              />
            </div>
            <span className="text-xs text-zinc-600 dark:text-zinc-400">{note}</span>
          </li>
        );
      })}
    </ol>
  );
}

// The roadmap: a row per phase on a timeline marked every three months.
export function Gantt({ phases }: { phases: { name: string; start_month: number; duration_months: number }[] }) {
  const last = Math.max(3, ...phases.map((phase) => phase.start_month + phase.duration_months - 1));
  const months = Math.ceil(last / 3) * 3;
  const marks = Array.from({ length: months / 3 }, (_, index) => index * 3);
  return (
    <div className="text-sm">
      <div className="grid grid-cols-[minmax(7rem,13rem)_1fr] gap-3">
        <span />
        <div className="relative h-5 text-xs text-zinc-500">
          {marks.map((month) => (
            <span key={month} className="absolute" style={{ left: `${(month / months) * 100}%` }}>
              Month {month + 1}
            </span>
          ))}
        </div>
      </div>
      <ul className="space-y-2">
        {phases.map((phase) => (
          <li key={phase.name} className="grid grid-cols-[minmax(7rem,13rem)_1fr] items-center gap-3">
            <span className="font-medium">{phase.name}</span>
            <div className="relative h-7 rounded bg-zinc-100 dark:bg-zinc-800/60">
              <div
                className="absolute inset-y-0 flex items-center justify-center rounded text-xs font-semibold text-white"
                title={`${phase.name}: months ${phase.start_month}-${phase.start_month + phase.duration_months - 1}`}
                style={{
                  left: `${((Math.max(phase.start_month, 1) - 1) / months) * 100}%`,
                  width: `${(Math.max(phase.duration_months, 1) / months) * 100}%`,
                  background: BLUE,
                }}
              >
                {phase.duration_months} mo
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Legend({ entries }: { entries: { name: string; color: string }[] }) {
  return (
    <div className="mb-3 flex flex-wrap gap-4 text-xs text-zinc-600 dark:text-zinc-400">
      {entries.map((entry) => (
        <span key={entry.name} className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-sm" style={{ background: entry.color }} />
          {entry.name}
        </span>
      ))}
    </div>
  );
}

// Columns grouped by category, one colour per series, each labelled with its value.
export function GroupedColumns({
  categories,
  series,
}: {
  categories: string[];
  series: { name: string; color: string; values: number[] }[];
}) {
  const largest = Math.max(1, ...series.flatMap((one) => one.values));
  return (
    <figure>
      <Legend entries={series} />
      <div className="flex h-56 items-end gap-6 border-b border-zinc-300 dark:border-zinc-700">
        {categories.map((category, index) => (
          <div key={category} className="flex h-full flex-1 items-end justify-center gap-1.5">
            {series.map((one) => (
              <div key={one.name} className="flex h-full w-10 flex-col items-center justify-end sm:w-14">
                <span className="mb-1 text-xs tabular-nums">{money(one.values[index])}</span>
                <div
                  className="w-full rounded-t"
                  title={`${category}, ${one.name}: ${usd(one.values[index])}`}
                  style={{ height: `${(Math.max(one.values[index], 0) / largest) * 85}%`, background: one.color }}
                />
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-6">
        {categories.map((category) => (
          <span key={category} className="flex-1 text-center text-xs font-medium text-zinc-600 dark:text-zinc-400">
            {category}
          </span>
        ))}
      </div>
    </figure>
  );
}

// The cumulative cash position, above or below zero.
export function CashPosition({ points, note }: { points: { label: string; value: number }[]; note: string }) {
  const top = Math.max(0, ...points.map((point) => point.value));
  const bottom = Math.min(0, ...points.map((point) => point.value));
  const span = top - bottom || 1;
  const zero = (top / span) * 100;
  return (
    <figure>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Legend
          entries={[
            { name: "Cash position above zero", color: BLUE },
            { name: "Below zero", color: NEGATIVE },
          ]}
        />
        <p className="mb-3 text-sm font-semibold">{note}</p>
      </div>
      <div className="relative flex h-56 gap-4">
        <div aria-hidden className="absolute inset-x-0 border-t border-zinc-400 dark:border-zinc-600" style={{ top: `${zero}%` }} />
        {points.map((point) => {
          const height = (Math.abs(point.value) / span) * 100;
          const above = point.value >= 0;
          return (
            <div key={point.label} className="relative flex-1">
              <div
                className="absolute inset-x-[25%] rounded"
                title={`${point.label}: ${usd(point.value)}`}
                style={{
                  top: above ? `${zero - height}%` : `${zero}%`,
                  height: `${Math.max(height, 0.5)}%`,
                  background: above ? BLUE : NEGATIVE,
                }}
              />
              <span
                className="absolute inset-x-0 text-center text-xs font-semibold tabular-nums"
                style={above ? { bottom: `${100 - zero + height + 1}%` } : { top: `${zero + height + 1}%` }}
              >
                {money(point.value)}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex gap-4">
        {points.map((point) => (
          <span key={point.label} className="flex-1 text-center text-xs text-zinc-600 dark:text-zinc-400">
            {point.label}
          </span>
        ))}
      </div>
    </figure>
  );
}

export const SEVERITY_STYLE: Record<Severity, string> = {
  Low: "bg-emerald-200/80 dark:bg-emerald-900/60",
  Moderate: "bg-amber-200/80 dark:bg-amber-900/60",
  High: "bg-orange-200/80 dark:bg-orange-900/60",
  Critical: "bg-red-300/80 dark:bg-red-900/70",
};

// Risks placed by probability (across) and impact (up), the cells shaded by severity.
export function RiskMatrix({ risks }: { risks: { id: string; probability: Level; impact: Level }[] }) {
  return (
    <figure className="flex flex-wrap items-start gap-6">
      <div className="grid grid-cols-[auto_repeat(3,minmax(4.5rem,8rem))] gap-1 text-xs">
        {[...LEVELS].reverse().map((impact) => (
          <div key={impact} className="contents">
            <span className="self-center pr-2 text-right text-zinc-600 dark:text-zinc-400">{impact}</span>
            {LEVELS.map((probability) => {
              const here = risks.filter((risk) => risk.probability === probability && risk.impact === impact);
              const level = severity(probability, impact);
              return (
                <div
                  key={probability}
                  title={`Probability ${probability}, impact ${impact}: ${level}`}
                  className={`flex min-h-14 flex-wrap content-center items-center justify-center gap-1 rounded p-1 ${SEVERITY_STYLE[level]}`}
                >
                  {here.map((risk) => (
                    <span key={risk.id} className="rounded-full bg-zinc-900 px-1.5 py-0.5 text-[10px] font-bold text-white dark:bg-zinc-100 dark:text-zinc-900">
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
          <span key={probability} className="text-center text-zinc-600 dark:text-zinc-400">
            {probability}
          </span>
        ))}
        <span />
        <span className="col-span-3 text-center font-semibold text-zinc-600 dark:text-zinc-400">Probability (impact upward)</span>
      </div>
      <figcaption className="space-y-1.5 text-xs">
        <p className="font-semibold text-zinc-600 dark:text-zinc-400">Severity</p>
        {(["Low", "Moderate", "High", "Critical"] as Severity[]).map((level) => (
          <p key={level} className="flex items-center gap-2">
            <span aria-hidden className={`size-3 rounded-sm ${SEVERITY_STYLE[level]}`} />
            {level}
          </p>
        ))}
      </figcaption>
    </figure>
  );
}

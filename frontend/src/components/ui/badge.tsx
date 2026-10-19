// A small label: the source of a section, a verdict, a state.

const TONES = {
  blue: "bg-accent-soft/70 text-navy dark:bg-accent/20 dark:text-accent-soft",
  green: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  amber: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  red: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
  gray: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

export type Tone = keyof typeof TONES;

export function Badge({ children, tone = "blue" }: { children: React.ReactNode; tone?: Tone }) {
  return <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>{children}</span>;
}

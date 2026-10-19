// A message in the flow of the page: what happened, or what to watch for.

import { AlertIcon, CheckIcon, InfoIcon } from "@/components/ui/icons";

export type Tone = "info" | "good" | "warn" | "bad";

const TONES: Record<Tone, string> = {
  info: "bg-primary-soft text-ink",
  good: "bg-good-soft text-good",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
};

const ICONS = { info: InfoIcon, good: CheckIcon, warn: AlertIcon, bad: AlertIcon };

export function Notice({
  tone = "info",
  children,
  className = "",
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
}) {
  const Glyph = ICONS[tone];
  return (
    <div
      role={tone === "bad" || tone === "warn" ? "alert" : "status"}
      className={`flex items-start gap-2.5 rounded-md px-3.5 py-2.5 text-sm leading-relaxed ${TONES[tone]} ${className}`}
    >
      <Glyph className="mt-0.5 size-4" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

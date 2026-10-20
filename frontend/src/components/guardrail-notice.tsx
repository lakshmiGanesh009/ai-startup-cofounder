// What tried to instruct the agents, and that it was taken out of what they
// read: the guardrails (guardrails.py) say so rather than stay silent.

import { Notice } from "@/components/ui/notice";
import type { GuardrailFlag } from "@/lib/api";

const SHOWN = 5;

function lead(flags: GuardrailFlag[]): string {
  if (flags.every((flag) => flag.origin === "web")) return "A web page the team read tried to give it instructions.";
  if (flags.every((flag) => flag.origin === "founder")) return "Part of what you sent read like instructions to the agents.";
  return "Some of what the team read tried to give it instructions.";
}

export function GuardrailNotice({ flags, className = "" }: { flags?: GuardrailFlag[]; className?: string }) {
  if (!flags?.length) return null;
  return (
    <Notice tone="warn" className={className}>
      <p>
        <span className="font-medium">{lead(flags)}</span> It was taken out of what the agents read, and the team
        carried on.
      </p>
      <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
        {flags.slice(0, SHOWN).map((flag, index) => (
          <li key={`${flag.source}-${flag.kind}-${index}`}>
            {flag.source.charAt(0).toUpperCase() + flag.source.slice(1)}: an attempt to {flag.kind} (“{flag.excerpt}”).
          </li>
        ))}
      </ul>
      {flags.length > SHOWN && <p className="mt-1">And {flags.length - SHOWN} more.</p>}
    </Notice>
  );
}

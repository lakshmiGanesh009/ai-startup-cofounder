// Preparing a brief: a decision template filled in, and the research the
// founder keeps once the Chief of Staff has prepared it (brief.py).

import type { Research, Template } from "@/lib/api";

export type TemplateValues = Record<string, string>;

// A field's answer as it reads inside the template's sentence: trimmed, with
// no closing full stop, which the sentence supplies.
function asPhrase(value: string): string {
  return value.trim().replace(/[\s.]+$/, "");
}

// The brief a template makes from its fields' answers.
export function fillTemplate(template: Template, values: TemplateValues): string {
  return template.prompt.replace(/\{(\w+)\}/g, (_, key: string) => asPhrase(values[key] ?? "") || `[${key}]`);
}

// The first field still to fill in, if any.
export function missingField(template: Template, values: TemplateValues) {
  return template.fields.find((field) => !asPhrase(values[field.key] ?? ""));
}

// The research without the facts the founder left out, its sources numbered
// again 1, 2, 3 in order of first citation and limited to those still cited;
// null when no fact is left.
export function keepFindings(research: Research | null, leftOut: ReadonlySet<number>): Research | null {
  if (!research) return null;
  const order = new Map<number, number>();
  const findings = research.findings
    .filter((_, index) => !leftOut.has(index))
    .map((finding) => ({
      point: finding.point,
      sources: finding.sources.map((n) => {
        if (!order.has(n)) order.set(n, order.size + 1);
        return order.get(n)!;
      }),
    }));
  if (!findings.length) return null;
  const sources = [...order.keys()].map((n) => research.sources[n - 1]).filter(Boolean);
  return { findings, sources };
}

// A source's site, to show beside its title: "ama-assn.org".
export function domain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

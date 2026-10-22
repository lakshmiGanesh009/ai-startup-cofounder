// A stand-in for the API's /reports endpoints in tests: it keeps one report,
// changes it as the API would, and can be told to fail a call.

import type { Answering } from "@/test/backend";
import { fakeBackend } from "@/test/backend";
import sample from "@/test/sample-report.json";
import type { Draft, FieldChange, Proposal, Rates, Report } from "@/lib/api";

export const SAMPLE_REPORT = sample as unknown as Report;
export const SESSION = SAMPLE_REPORT.session_id;
const PATH = `/reports/${SESSION}`;

// Today's rates from the dollar (GET /rates/USD).
export const RATES: Rates = {
  base: "USD",
  date: "2026-10-21",
  source: "European Central Bank reference rates",
  rates: { EUR: 0.92, GBP: 0.746173, INR: 94.469, AED: 3.6725, SAR: 3.75 },
  pegged: ["AED", "SAR"],
};

export function fakeReports({ proposal = false, failures = {} as Record<string, number>, extra = {} as Record<string, Answering> } = {}) {
  const state = {
    report: {
      ...structuredClone(SAMPLE_REPORT),
      version: 1,
      edited: false,
      proposal: proposal ? structuredClone(SAMPLE_REPORT.proposal) : null,
      investment: proposal ? structuredClone(SAMPLE_REPORT.investment) : null,
    } as Report,
    failures,
  };
  const changed = (updates: Partial<Report>) => {
    state.report = { ...state.report, ...updates, version: state.report.version + 1 };
    return state.report;
  };
  const draftOf = (report: Report, summary: string, changes: FieldChange[]): Draft => ({
    report,
    summary,
    changes,
    base_version: state.report.version,
  });
  const revisedProposal = () =>
    state.report.proposal && {
      ...state.report.proposal,
      market: { ...state.report.proposal.market, pricing_strategy: "Charge $129 a month." },
    };
  // As document.py makes them: a draft of each kind of change.
  const draftFor = (change: Record<string, unknown>): Draft => {
    const report = state.report;
    switch (change.kind) {
      case "currency":
        return draftOf(
          { ...report, settings: { ...report.settings, currency: String(change.to) } },
          `Converted 22 figures and 15 amounts in the text from USD to ${change.to} at 1 USD = ${change.rate} ${change.to}.`,
          [
            { path: "proposal.financial.capex.0.amount", label: "Financial plan · CapEx · Build · Amount", before: 9000, after: 8280, money: true },
            { path: "settings.currency", label: "Settings · Currency", before: "USD", after: String(change.to), money: false },
          ],
        );
      case "redact":
        return draftOf(report, `Redacted 2 occurrences of ${(change.terms as string[]).length} terms.`, [
          { path: "sections.strategy", label: "Team report · Launch Strategy", before: "Hire Dana Reyes.", after: "Hire ██████████.", money: false },
        ]);
      case "remove":
        return draftOf(report, "Removed a passage from Market & marketing · Pricing strategy.", [
          { path: String(change.path), label: "Market & marketing · Pricing strategy", before: String(change.passage), after: "", money: false },
        ]);
      default:
        return draftOf(report, `Made a ${change.kind} change.`, [
          { path: "title", label: "Title", before: report.title, after: `${report.title}!`, money: false },
        ]);
    }
  };
  const answer = (key: string, ok: (body: { version?: number } & Record<string, unknown>) => unknown): Answering => (body) => {
    const status = state.failures[key];
    if (status) return { status, body: { detail: `It failed (${status}).` } };
    const request = (body ?? {}) as { version?: number } & Record<string, unknown>;
    if (request.version !== undefined && request.version !== state.report.version) {
      return { status: 409, body: { detail: "The report changed." } };
    }
    return { body: ok(request) };
  };
  const backend = fakeBackend({
    "GET /reports": answer("list", () => [
      {
        session_id: SESSION,
        title: state.report.title,
        version: state.report.version,
        has_proposal: Boolean(state.report.proposal),
        edited: state.report.edited,
        outdated: state.report.outdated,
        updated_at: state.report.updated_at,
      },
    ]),
    [`GET ${PATH}`]: answer("get", () => state.report),
    [`PUT ${PATH}`]: answer("save", (body) => changed({ sections: body.sections as Report["sections"], edited: true })),
    [`POST ${PATH}/reset`]: answer("reset", () => changed({ proposal: null, investment: null, edited: false })),
    [`POST ${PATH}/proposal`]: answer("write", () => ({
      report: changed({ proposal: structuredClone(SAMPLE_REPORT.proposal), investment: structuredClone(SAMPLE_REPORT.investment) }),
      failed: [],
    })),
    [`POST ${PATH}/proposal/revise`]: answer("revise", () => ({
      draft: draftOf(
        { ...state.report, proposal: revisedProposal() },
        "The marketing agent revised Market & Marketing Strategy as you asked.",
        [{ path: "proposal.market.pricing_strategy", label: "Market & marketing · Pricing strategy", before: "Charge $149 a month.", after: "Charge $129 a month.", money: false }],
      ),
      failed: ["Financial Plan & Projections"],
    })),
    [`POST ${PATH}/revise`]: answer("reviseText", (body) => ({
      draft: draftOf(
        { ...state.report, proposal: revisedProposal() },
        "Rewrote a passage of Market & marketing · Pricing strategy as you asked.",
        [{ path: String(body.path), label: "Market & marketing · Pricing strategy", before: String(body.passage), after: "A sharper passage.", money: false }],
      ),
      failed: [],
    })),
    [`POST ${PATH}/drafts`]: answer("draft", (body) => draftFor(body.change as Record<string, unknown>)),
    [`POST ${PATH}/accept`]: answer("accept", (body) => {
      const content = body.content as Partial<Report>;
      return changed({ ...content, edited: true, change: String(body.change) });
    }),
    [`GET ${PATH}/versions`]: answer("versions", () => [
      { version: state.report.version, updated_at: state.report.updated_at, change: state.report.change, has_proposal: Boolean(state.report.proposal), current: true },
      { version: 0, updated_at: "2026-10-18T09:00:00Z", change: "Written by the team", has_proposal: false, current: false },
    ]),
    [`GET ${PATH}/versions/0`]: answer("version", () => ({ ...state.report, version: 0, change: "Written by the team", proposal: null })),
    [`POST ${PATH}/versions/0/restore`]: answer("restore", () => changed({ proposal: null, investment: null, change: "Restored version 0" })),
    [`PUT ${PATH}/proposal`]: answer("saveProposal", (body) => changed({ proposal: body.proposal as Proposal, edited: true })),
    [`GET ${PATH}/pdf`]: answer("pdf", () => "%PDF"),
    [`POST ${PATH}/pdf`]: answer("previewPdf", () => "%PDF"),
    "GET /rates/USD": answer("rates", () => RATES),
    "GET /rates/EUR": answer("rates", () => ({ ...RATES, base: "EUR", rates: { USD: 1.08696, AED: 3.99185 } })),
    ...extra,
  });
  return { ...backend, state };
}

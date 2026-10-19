// A stand-in for the API's /reports endpoints in tests: it keeps one report,
// changes it as the API would, and can be told to fail a call.

import type { Answering } from "@/test/backend";
import { fakeBackend } from "@/test/backend";
import sample from "@/test/sample-report.json";
import type { Proposal, Report } from "@/lib/api";

export const SAMPLE_REPORT = sample as unknown as Report;
export const SESSION = SAMPLE_REPORT.session_id;
const PATH = `/reports/${SESSION}`;

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
    [`POST ${PATH}/proposal/revise`]: answer("revise", () => ({ report: changed({}), failed: ["Financial Plan & Projections"] })),
    [`PUT ${PATH}/proposal`]: answer("saveProposal", (body) => changed({ proposal: body.proposal as Proposal, edited: true })),
    [`GET ${PATH}/pdf`]: answer("pdf", () => "%PDF"),
    ...extra,
  });
  return { ...backend, state };
}

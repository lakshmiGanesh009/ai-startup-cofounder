import { describe, expect, test } from "vitest";

import { domain, fillTemplate, keepFindings, missingField } from "@/lib/brief";
import { PREPARED, TEMPLATES } from "@/test/backend";

const [idea] = TEMPLATES;

describe("a decision template", () => {
  test("reads as a sentence once filled in, with its blanks shown until then", () => {
    expect(fillTemplate(idea, { idea: " An app. ", customer: "clinics..." })).toBe(
      "Evaluate this startup idea: An app. It is for clinics. Is it worth building, and how should we launch it?",
    );
    expect(fillTemplate(idea, { idea: "An app" })).toBe(
      "Evaluate this startup idea: An app. It is for [customer]. Is it worth building, and how should we launch it?",
    );
  });

  test("names the first field still to fill in", () => {
    expect(missingField(idea, {})?.key).toBe("idea");
    expect(missingField(idea, { idea: "An app", customer: " . " })?.key).toBe("customer");
    expect(missingField(idea, { idea: "An app", customer: "Clinics" })).toBeUndefined();
  });
});

describe("the research the founder keeps", () => {
  test("drops the facts left out, and numbers the sources still cited again", () => {
    expect(keepFindings(PREPARED.research, new Set([0]))).toEqual({
      findings: [
        { point: "Scheduling tools cost $20-$300 per provider a month in 2025.", sources: [1, 2] },
        { point: "Most small practices still book follow-ups by phone.", sources: [1] },
      ],
      sources: [PREPARED.research!.sources[1], PREPARED.research!.sources[0]],
    });
    expect(keepFindings(PREPARED.research, new Set())).toEqual(PREPARED.research);
  });

  test("is nothing when every fact is left out, or there was no research", () => {
    expect(keepFindings(PREPARED.research, new Set([0, 1, 2]))).toBeNull();
    expect(keepFindings(null, new Set())).toBeNull();
  });
});

test("a source shows its site", () => {
  expect(domain("https://www.ama-assn.org/survey?x=1")).toBe("ama-assn.org");
  expect(domain("not a url")).toBe("not a url");
});

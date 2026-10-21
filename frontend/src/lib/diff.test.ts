import { describe, expect, test } from "vitest";

import { diffWords } from "@/lib/diff";

const shown = (before: string, after: string) =>
  diffWords(before, after)
    .map(({ text, kind }) => (kind === "same" ? text : kind === "added" ? `[+${text}]` : `[-${text}]`))
    .join("");

describe("what changed in a text", () => {
  test("changed words are marked, the rest kept", () => {
    expect(shown("Charge $149 a month per clinic.", "Charge €137 a month per clinic.")).toBe(
      "Charge [-$149][+€137] a month per clinic.",
    );
  });

  test("a long text with one changed line compares that line alone", () => {
    const before = ["One line.", "Two at $10.", "Three."].join("\n");
    const after = ["One line.", "Two at €9.", "Three."].join("\n");
    expect(shown(before, after)).toBe("One line.\nTwo at [-$10.][+€9.]\nThree.");
  });

  test("added and removed lines, and an emptied text", () => {
    expect(shown("A.\nB.", "A.\nB.\nC.")).toContain("[+C.]");
    expect(shown("A.\n- Hire Dana.", "A.")).toContain("[-- Hire Dana.]");
    expect(shown("Gone.", "")).toBe("[-Gone.]");
  });
});

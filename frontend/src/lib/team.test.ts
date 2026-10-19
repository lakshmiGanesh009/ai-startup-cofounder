import { describe, expect, test } from "vitest";

import type { Step } from "@/lib/api";
import { activity, assigned, formatSeconds, joinNames, nodeStates, specialistTitle, STAGES, stageState } from "@/lib/team";
import { STEPS } from "@/test/backend";

const start = (node: string, at = 0): Step => ({ type: "start", node, at });
const done = (node: string, at = 0, extra: Partial<Step> = {}): Step => ({ type: "done", node, at, ...extra });
const stage = (key: string) => STAGES.find((each) => each.key === key)!;

describe("what the team is doing now", () => {
  test("each step of the graph has its own sentence", () => {
    expect(activity([])).toBe("The Chief of Staff is reading the brief and planning the work.");
    expect(activity([start("plan")])).toBe("The Chief of Staff is reading the brief and planning the work.");
    expect(activity([start("review")])).toBe("The Chief of Staff is reviewing the reports.");
    expect(activity([start("critique")])).toBe("The specialists are cross-checking each other's reports.");
    expect(activity([start("resolve")])).toBe("The Chief of Staff is settling the conflicts.");
    expect(activity([start("synthesis")])).toBe("The Chief of Staff is writing the launch strategy.");
    expect(activity([start("plan"), done("plan")])).toBe("Passing the work on.");
  });

  test("specialists write together, and a second run is a revision", () => {
    expect(activity([start("marketing"), start("finance"), start("risk")])).toBe(
      "Marketing Strategy, Financial Planning and Risk & Compliance are writing their reports.",
    );
    expect(activity([start("finance"), done("finance"), start("finance")])).toBe(
      "Financial Planning is revising its report.",
    );
    expect(
      activity([start("finance"), done("finance"), start("finance"), start("marketing"), start("technical")]),
    ).toBe("Marketing Strategy and Technical Feasibility are writing their reports. Financial Planning is revising its report.");
  });
});

describe("the stages", () => {
  test("follow the steps from waiting to done", () => {
    const team = assigned(STEPS);
    expect(team).toEqual(["finance", "marketing"]);
    const early = nodeStates(STEPS.slice(0, 5));
    expect(stageState(stage("reports"), early, team)).toBe("working");
    expect(stageState(stage("review"), early, team)).toBe("waiting");
    const all = nodeStates(STEPS);
    expect(STAGES.map((each) => stageState(each, all, team))).toEqual(["done", "done", "done", "done", "done"]);
  });

  test("the cross-check is skipped when the strategy starts without it", () => {
    const steps = [start("plan"), done("plan", 1, { assigned: ["finance"] }), start("finance"), done("finance"), start("review"), done("review"), start("synthesis")];
    expect(stageState(stage("cross-check"), nodeStates(steps), ["finance"])).toBe("skipped");
  });

  test("the reports are done only when every assigned specialist has written", () => {
    const steps = [start("finance"), done("finance"), start("marketing")];
    expect(stageState(stage("reports"), nodeStates(steps.slice(0, 2)), ["finance", "marketing"])).toBe("waiting");
    expect(stageState(stage("reports"), nodeStates(steps.slice(0, 2)), ["finance"])).toBe("done");
  });
});

test("names and times read naturally", () => {
  expect(specialistTitle("finance")).toBe("Financial Planning");
  expect(specialistTitle("someone")).toBe("someone");
  expect(joinNames([])).toBe("");
  expect(joinNames(["A"])).toBe("A");
  expect(joinNames(["A", "B"])).toBe("A and B");
  expect(formatSeconds(117.4)).toBe("1:57");
  expect(formatSeconds(-3)).toBe("0:00");
});

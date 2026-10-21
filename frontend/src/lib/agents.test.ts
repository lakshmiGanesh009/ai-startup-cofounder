import { describe, expect, test } from "vitest";

import { agentFill, agentOf, agentsOf, agentsOfSource, PART_AGENT, SECTION_AGENT, specialistAgent } from "@/lib/agents";

describe("who does what", () => {
  test("each step of the graph belongs to the agent who does it", () => {
    expect(["plan", "review", "resolve", "synthesis"].map(agentOf)).toEqual(["chief", "chief", "chief", "chief"]);
    expect(agentOf("finance")).toBe("finance");
    expect(agentOf("research")).toBe("research");
    // The cross-check is the specialists', each checking the others.
    expect(agentsOf("critique")).toEqual(["marketing", "finance", "technical", "risk"]);
  });

  test("the Monitor's own events belong to no agent", () => {
    expect(agentsOfSource("system")).toEqual([]);
    expect(agentsOfSource("proposal")).toEqual(["chief"]);
    expect(agentsOfSource("risk")).toEqual(["risk"]);
  });

  test("the proposal's parts and the report's sections name their writers", () => {
    expect(PART_AGENT.financial).toBe("finance");
    expect(PART_AGENT.executive).toBe("chief");
    expect(SECTION_AGENT.decisions).toBe("chief");
    expect(specialistAgent("technical")).toBe("technical");
  });

  test("a bar is one colour, or the colours of several in turn", () => {
    expect(agentFill(["finance"])).toBe("var(--agent-finance)");
    expect(agentFill(["marketing", "finance"])).toBe(
      "linear-gradient(90deg, var(--agent-marketing) 0% 50%, var(--agent-finance) 50% 100%)",
    );
  });
});

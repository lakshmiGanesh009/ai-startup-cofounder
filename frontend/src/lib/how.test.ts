import { describe, expect, test } from "vitest";

import { decisionsDiagram, flowDiagram, graphDiagram, type Palette, translucent } from "@/lib/how";
import { PIPELINE } from "@/test/backend";

const swatch = (line: string) => ({ line, fill: `${line}22` });
const PALETTE: Palette = {
  roles: {
    you: swatch("#163c6b"),
    chief: swatch("#4a3aa7"),
    research: swatch("#6b7889"),
    marketing: swatch("#eb6834"),
    finance: swatch("#1baf7a"),
    technical: swatch("#2a78d6"),
    risk: swatch("#e87ba4"),
    team: swatch("#7c786d"),
  },
  ink: "#1c1b18",
  muted: "#7c786d",
  surface: "#fdfcf9",
};

// As LangGraph draws it: the specialists declared last, the edges in the order of their names.
const GRAPH = `---
config:
  flowchart:
    curve: linear
---
graph TD;
\t__start__([start])
\tplan(plan)
\treview(review)
\tfinance(finance)
\tmarketing(marketing)
\t__start__ --> plan;
\tfinance -.-> review;
\tmarketing -.-> review;
\tplan -.-> finance;
\tplan -.-> marketing;
\treview -.-> finance;`;

describe("the diagrams in the team's colours", () => {
  test("the graph runs in the order of the work, each node and edge in its agent's colours", () => {
    const drawn = graphDiagram(GRAPH, PALETTE).split("\n");
    expect(drawn.slice(0, 6)).toEqual(["---", "config:", "  flowchart:", "    curve: linear", "---", "graph TD;"]);
    expect(drawn.filter((line) => line.includes("(")).map((line) => line.trim())).toEqual([
      "__start__([start])",
      "plan(plan)",
      "marketing(marketing)",
      "finance(finance)",
      "review(review)",
    ]);
    const edges = drawn.filter((line) => / -\.?->? /.test(line)).map((line) => line.trim());
    // The edge back up to finance is drawn from it, without an arrowhead, so the layout reads downward.
    expect(edges).toEqual([
      "__start__ --> plan;",
      "plan -.-> marketing;",
      "plan -.-> finance;",
      "marketing -.-> review;",
      "finance -.-> review;",
      "finance -.- review;",
    ]);
    expect(drawn).toContain("  class plan,review chief");
    expect(drawn).toContain("  classDef finance fill:#1baf7a22,stroke:#1baf7a,stroke-width:2px,color:#1c1b18");
    // Each edge in the colour of the node it leaves: review's, back to finance, the Chief of Staff's.
    expect(drawn).toContain("  linkStyle 0 stroke:#163c6b,stroke-width:1.5px");
    expect(drawn).toContain("  linkStyle 3 stroke:#eb6834,stroke-width:1.5px");
    expect(drawn).toContain("  linkStyle 5 stroke:#4a3aa7,stroke-width:1.5px");
  });

  test("a graph it cannot read is drawn as it is", () => {
    expect(graphDiagram("flowchart LR\n  a --- b", PALETTE)).toBe("flowchart LR\n  a --- b");
  });

  test("the data flow puts each stretch of the work on a band in its colour", () => {
    const flow = flowDiagram(PIPELINE.rules, PALETTE);
    expect(flow).toContain("rect rgba(74, 58, 167, 0.1)\n    API->>C: Plan two to four searches");
    expect(flow).toContain("rect rgba(107, 120, 137, 0.1)\n    opt Deep research is on");
    expect(flow).toContain("rect rgba(124, 120, 109, 0.1)\n    par Each assigned specialist, at once");
  });

  test("the decisions show each specialist, and each box in the colours of who does it", () => {
    const decisions = decisionsDiagram(PIPELINE.rules, PALETTE);
    expect(decisions).toContain("subgraph work [The specialists write their reports, at once]");
    expect(decisions).toContain("  class plan,review,many,conflicts,decide,strategy chief");
    expect(decisions).toContain("  class back,critique,revise team");
    // Their four colours are painted on once drawn; a class's colours would hide them.
    expect(decisions).toContain("  classDef team color:#1c1b18");
    expect(decisions).toContain("  class brief,out you");
  });

  test("a colour can be made translucent", () => {
    expect(translucent("#4a3aa7", 0.1)).toBe("rgba(74, 58, 167, 0.1)");
    expect(translucent("#fff", 0.5)).toBe("rgba(255, 255, 255, 0.5)");
    expect(translucent("oklch(0.5 0.1 200)", 0.5)).toBe("oklch(0.5 0.1 200)");
  });
});

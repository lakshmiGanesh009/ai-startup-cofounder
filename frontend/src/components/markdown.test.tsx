import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { Markdown } from "@/components/markdown";

const headings = () => screen.queryAllByRole("heading").map((heading) => [heading.tagName, heading.textContent]);

describe("the agents' markdown", () => {
  test("a label on its own line before a list or table becomes a heading", () => {
    render(
      <Markdown labels>
        {[
          "Recommendation: go with conditions, because the pilot pays for itself.",
          "Key facts driving the decision\n- Price: $199\n- Budget: $15k",
          "**Next steps:**\n1. Sign the BAA",
          "| Item | Cost |\n| --- | --- |\n| Legal | $1,500 |",
          "Budget summary (as reported)\n\n| Item | Cost |\n| --- | --- |\n| Hosting | $40 |",
        ].join("\n\n")}
      </Markdown>,
    );

    expect(headings()).toEqual([
      ["H3", "Key facts driving the decision"],
      ["H3", "Next steps"],
      ["H3", "Budget summary (as reported)"],
    ]);
    expect(screen.getByText(/^Recommendation: go with conditions/).tagName).toBe("P");
  });

  test("sentences, long lines and labels inside lists stay as they are", () => {
    render(
      <Markdown labels>
        {[
          "The plan has three parts:\n- One\n- Two",
          "A line that runs on far too long to be a section label in any report the agents would write\n- One",
          "Who buys\n\nOffice managers at small clinics.",
          "- Variable costs\n  - LLM: $1.60",
        ].join("\n\n")}
      </Markdown>,
    );

    expect(headings()).toEqual([]);
  });

  test("labels sit a level below the document's own headings, or at the level given", () => {
    const { unmount } = render(<Markdown labels>{"### Pricing\n\nFirst-year prices\n- $199"}</Markdown>);
    expect(headings()).toEqual([
      ["H3", "Pricing"],
      ["H4", "First-year prices"],
    ]);
    unmount();

    render(<Markdown labels={4}>{"Key risks\n- PHI exposure"}</Markdown>);
    expect(headings()).toEqual([["H4", "Key risks"]]);
  });

  test("renders tables, highlights assumptions and shows raw HTML as text", () => {
    const { container } = render(
      <Markdown>
        {"| Plan | Price |\n| --- | --- |\n| Pilot | $149 (estimate) |\n\nSome **bold** (assumption) text <b>raw</b>."}
      </Markdown>,
    );

    expect(container.querySelector("table")).toBeTruthy();
    expect([...container.querySelectorAll("mark.assumption")].map((mark) => mark.textContent)).toEqual([
      "(estimate)",
      "(assumption)",
    ]);
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<b>raw</b>");
  });

  test("without labels, the text is set as written, with assumptions marked", () => {
    const { container } = render(<Markdown compact>{"Key risks\n- Churn of 5% (assumption)"}</Markdown>);

    expect(headings()).toEqual([]);
    expect(container.querySelector(".doc-compact mark.assumption")?.textContent).toBe("(assumption)");
  });

  test("the agents the Chief of Staff cites are set as tags in their colours", () => {
    const { container } = render(
      <Markdown>
        {"Go with paid pilots [finance][marketing], within the budget [Chief of Staff]. See `[risk]` and [someone]."}
      </Markdown>,
    );

    const tags = [...container.querySelectorAll(".cite")].map((tag) => [tag.className, tag.textContent]);
    expect(tags).toEqual([
      ["cite agent-finance", "Finance"],
      ["cite agent-marketing", "Marketing"],
      ["cite agent-chief", "Chief of Staff"],
    ]);
    // Code keeps its brackets, and a name that is no agent stays as written.
    expect(container.querySelector("code")?.textContent).toBe("[risk]");
    expect(container.textContent).toContain("[someone]");
  });
});

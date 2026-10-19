import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { Markdown } from "@/components/markdown";
import { Tabs } from "@/components/ui/tabs";
import { formatSeconds, specialistTitle } from "@/lib/team";

describe("tabs", () => {
  test("the arrow keys move between tabs, wrapping round", () => {
    render(
      <Tabs
        label="Parts"
        tabs={[
          { label: "One", content: "First" },
          { label: "Two", content: "Second" },
        ]}
      />,
    );
    const one = screen.getByRole("tab", { name: "One" });

    fireEvent.keyDown(one, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Two" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel", { name: "Two" }).textContent).toBe("Second");

    fireEvent.keyDown(screen.getByRole("tab", { name: "Two" }), { key: "ArrowRight" });
    expect(one.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(one, { key: "ArrowLeft" });
    expect(document.activeElement?.textContent).toBe("Two");
  });
});

describe("markdown", () => {
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
});

describe("the team's wording", () => {
  test("names and times read as words", () => {
    expect(specialistTitle("finance")).toBe("Financial Planning");
    expect(specialistTitle("someone")).toBe("someone");
    expect(formatSeconds(125.7)).toBe("2:05");
    expect(formatSeconds(-3)).toBe("0:00");
  });
});

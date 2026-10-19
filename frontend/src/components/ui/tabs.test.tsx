import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { Tabs } from "@/components/ui/tabs";

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
    // Across the top, the panels have no link to the next.
    expect(screen.queryByRole("button", { name: /^Next/ })).toBeNull();
  });

  test("down the side, the up and down arrows move, and each panel but the last links to the next", async () => {
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    render(
      <Tabs
        label="Chapters"
        orientation="vertical"
        initial={1}
        tabs={[
          { label: "Overview", marker: "1", content: "First" },
          { label: "Market", marker: "2", content: "Second" },
          { label: "Appendix", marker: "A", content: "Last" },
        ]}
      />,
    );
    expect(screen.getByRole("tablist", { name: "Chapters" }).getAttribute("aria-orientation")).toBe("vertical");
    // The marker numbers the tab without being part of its name.
    const market = screen.getByRole("tab", { name: "Market" });
    expect(market.getAttribute("aria-selected")).toBe("true");

    fireEvent.keyDown(market, { key: "ArrowUp" });
    expect(screen.getByRole("tab", { name: "Overview" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Overview" }), { key: "ArrowDown" });
    expect(market.getAttribute("aria-selected")).toBe("true");

    const panel = screen.getByRole("tabpanel", { name: "Market" });
    await userEvent.click(screen.getAllByRole("button", { name: /^Next/ }).find((button) => panel.contains(button))!);
    expect(screen.getByRole("tab", { name: "Appendix" }).getAttribute("aria-selected")).toBe("true");
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
    expect(screen.queryAllByRole("button", { name: /^Next/ })).toEqual([]);
  });
});

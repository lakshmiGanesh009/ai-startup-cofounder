import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { ThemeSwitch } from "@/components/theme-switch";
import { isDark, THEME_SCRIPT } from "@/lib/theme";

const radio = (name: string) => screen.getByRole("radio", { name }) as HTMLInputElement;

// The system says dark.
function systemDark() {
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }));
}

afterEach(() => {
  delete document.documentElement.dataset.theme;
});

describe("light or dark", () => {
  test("the founder's choice wins over the system's, and is remembered", async () => {
    systemDark();
    const user = userEvent.setup();
    render(<ThemeSwitch />);

    expect(radio("System").checked).toBe(true);
    expect(isDark()).toBe(true);

    await user.click(radio("Light"));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem("cofounder-theme")).toBe("light");
    expect(isDark()).toBe(false);

    await user.click(radio("Dark"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(radio("Dark").checked).toBe(true);

    await user.click(radio("System"));
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(window.localStorage.getItem("cofounder-theme")).toBeNull();
    expect(isDark()).toBe(true);
  });

  test("a remembered choice is set before the page paints; anything else is ignored", () => {
    window.localStorage.setItem("cofounder-theme", "dark");
    new Function(THEME_SCRIPT)();
    expect(document.documentElement.dataset.theme).toBe("dark");

    delete document.documentElement.dataset.theme;
    window.localStorage.setItem("cofounder-theme", "purple");
    new Function(THEME_SCRIPT)();
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  test("the switch shows the remembered choice", () => {
    window.localStorage.setItem("cofounder-theme", "dark");
    render(<ThemeSwitch />);
    expect(radio("Dark").checked).toBe(true);
  });
});

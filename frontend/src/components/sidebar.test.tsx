import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { Sidebar } from "@/components/sidebar";
import { BackendProvider, useBackend } from "@/lib/backend";
import { fakeBackend, HEALTH } from "@/test/backend";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

function renderSidebar() {
  return render(
    <BackendProvider>
      <Sidebar />
    </BackendProvider>,
  );
}

describe("the sidebar", () => {
  test("shows the pages, the connection and the configured efforts", async () => {
    fakeBackend();
    renderSidebar();

    expect(await screen.findByText(/API connected/)).toBeTruthy();
    const pages = screen.getByRole("navigation", { name: "Pages" });
    expect(within(pages).getByRole("link", { name: "Evaluate" }).getAttribute("aria-current")).toBe("page");
    expect(within(pages).getByRole("link", { name: "Reports" }).getAttribute("href")).toBe("/reports");
    expect(within(pages).getByRole("link", { name: "Reports" }).getAttribute("aria-current")).toBeNull();
    expect(screen.getByLabelText<HTMLInputElement>("Specialists").getAttribute("aria-valuetext")).toBe("minimal");
    expect(screen.getByLabelText<HTMLInputElement>("Chief of Staff").getAttribute("aria-valuetext")).toBe("medium");
    expect(screen.getByText(/This takes about two minutes/)).toBeTruthy();
    // The value beside each slider, with what a call takes at it.
    expect(screen.getByText("medium").textContent).toBe("medium · ~9 s");
  });

  test("a slider changes the effort, which this browser remembers", async () => {
    fakeBackend();
    renderSidebar();
    const chief = await screen.findByLabelText<HTMLInputElement>("Chief of Staff");
    await screen.findByText(/API connected/);

    fireEvent.change(chief, { target: { value: "3" } });

    expect(chief.getAttribute("aria-valuetext")).toBe("high");
    expect(screen.getByText(/At high reasoning this takes 5 to 10 minutes/)).toBeTruthy();
    expect(JSON.parse(window.localStorage.getItem("cofounder-reasoning") ?? "{}")).toEqual({
      specialist: "minimal",
      chief: "high",
    });
  });

  test("a remembered effort wins over the configured one", async () => {
    window.localStorage.setItem("cofounder-reasoning", JSON.stringify({ specialist: "low", chief: "xhigh" }));
    fakeBackend();
    renderSidebar();
    await screen.findByText(/API connected/);

    expect(screen.getByLabelText("Specialists").getAttribute("aria-valuetext")).toBe("low");
    // Not an effort the API offers, so the configured one is used.
    expect(screen.getByLabelText("Chief of Staff").getAttribute("aria-valuetext")).toBe("medium");
  });

  test("the sliders are off when the provider takes no reasoning", async () => {
    fakeBackend({ "GET /health": { body: { ...HEALTH, reasoning: { ...HEALTH.reasoning, adjustable: false } } } });
    renderSidebar();

    expect(await screen.findByText(/only Azure OpenAI does/)).toBeTruthy();
    expect(screen.getByLabelText<HTMLInputElement>("Chief of Staff").disabled).toBe(true);
  });

  test("an unreachable backend is explained", async () => {
    fakeBackend({ "GET /health": undefined });
    renderSidebar();

    expect(await screen.findByText(/Can.t reach the API/)).toBeTruthy();
    expect(screen.getByText("Unavailable until the backend answers.")).toBeTruthy();
  });

  test("it checks the backend again every 30 s, so an outage and the recovery both show", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let down = false;
    fakeBackend({ "GET /health": () => (down ? { status: 503, body: { detail: "Down." } } : { body: HEALTH }) });
    renderSidebar();
    const chief = await screen.findByLabelText<HTMLInputElement>("Chief of Staff");
    await screen.findByText(/API connected/);
    fireEvent.change(chief, { target: { value: "3" } });

    down = true;
    await act(async () => vi.advanceTimersByTimeAsync(30000));
    expect(await screen.findByText(/Can.t reach the API/)).toBeTruthy();
    expect(screen.getByText(/The backend returned 503: Down\./)).toBeTruthy();

    down = false;
    await act(async () => vi.advanceTimersByTimeAsync(30000));
    expect(await screen.findByText(/API connected/)).toBeTruthy();
    expect(chief.getAttribute("aria-valuetext")).toBe("high"); // the choice made before the outage stands
  });

  test("on a phone the rail folds into a menu", async () => {
    fakeBackend();
    const user = userEvent.setup();
    renderSidebar();
    const toggle = screen.getByRole("button", { name: "Open the menu" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    await user.click(toggle);

    expect(screen.getByRole("button", { name: "Close the menu" }).getAttribute("aria-expanded")).toBe("true");
    await user.click(within(screen.getByRole("navigation", { name: "Pages" })).getByRole("link", { name: "Reports" }));
    expect(screen.getByRole("button", { name: "Open the menu" })).toBeTruthy();
  });

  test("the backend's state is only available inside its provider", () => {
    function Orphan() {
      useBackend();
      return null;
    }
    vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<Orphan />)).toThrow("useBackend must be used inside <BackendProvider>.");
  });
});

describe("the web research switch", () => {
  const radio = (name: string) => screen.getByRole<HTMLInputElement>("radio", { name });

  test("starts at the backend's default, Azure OpenAI, and remembers a switch to Tavily", async () => {
    fakeBackend();
    const { unmount } = renderSidebar();
    const group = await screen.findByRole("group", { name: "Web research" });
    await within(group).findByText(/Bing search through your Azure OpenAI deployment/);
    expect(radio("Azure OpenAI").checked).toBe(true);

    await userEvent.click(radio("Tavily"));

    expect(radio("Tavily").checked).toBe(true);
    expect(within(group).getByText("Deeper research for demanding tasks, from your Tavily credits.")).toBeTruthy();
    expect(window.localStorage.getItem("cofounder-research")).toBe("tavily");
    unmount();

    renderSidebar();
    await screen.findByText("Deeper research for demanding tasks, from your Tavily credits.");
    expect(radio("Tavily").checked).toBe(true);
  });

  test("a provider the server has not set up cannot be chosen", async () => {
    window.localStorage.setItem("cofounder-research", "tavily");
    fakeBackend({ "GET /health": { body: { ...HEALTH, research: { providers: { azure: true, tavily: false }, default: "azure" } } } });
    renderSidebar();

    expect(await screen.findByText(/Add a TAVILY_API_KEY to use Tavily\./)).toBeTruthy();
    expect(radio("Tavily").disabled).toBe(true);
    expect(radio("Azure OpenAI").checked).toBe(true); // the remembered Tavily is not available
  });

  test("with neither set up, or before the backend answers, it says so", async () => {
    fakeBackend({ "GET /health": { body: { ...HEALTH, research: { providers: { azure: false, tavily: false }, default: null } } } });
    const { unmount } = renderSidebar();
    expect(await screen.findByText("No web research: set up Azure OpenAI, or add a TAVILY_API_KEY.")).toBeTruthy();
    expect(radio("Azure OpenAI").disabled && radio("Tavily").disabled).toBe(true);
    unmount();

    fakeBackend({ "GET /health": () => new Promise(() => {}) });
    renderSidebar();
    expect(screen.getByText("Shown once the backend answers.")).toBeTruthy();
  });
});

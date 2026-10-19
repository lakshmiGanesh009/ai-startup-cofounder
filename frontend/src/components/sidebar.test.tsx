import { fireEvent, render, screen } from "@testing-library/react";
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

    expect(await screen.findByText(/Connected to http:\/\/localhost:8000/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Evaluate" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: /Reports/ }).getAttribute("href")).toBe(
      "http://localhost:8501/reports_page",
    );
    expect(screen.getByLabelText<HTMLInputElement>("Specialists").getAttribute("aria-valuetext")).toBe("minimal");
    expect(screen.getByLabelText<HTMLInputElement>("Chief of Staff").getAttribute("aria-valuetext")).toBe("medium");
    expect(screen.getByText(/This takes about two minutes/)).toBeTruthy();
  });

  test("a slider changes the effort, which this browser remembers", async () => {
    fakeBackend();
    renderSidebar();
    const chief = await screen.findByLabelText<HTMLInputElement>("Chief of Staff");
    await screen.findByText(/Connected/);

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
    await screen.findByText(/Connected/);

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

    expect(await screen.findByText(/Can.t reach http:\/\/localhost:8000/)).toBeTruthy();
    expect(screen.getByText("Unavailable until the backend answers.")).toBeTruthy();
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

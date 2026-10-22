import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { EvaluateApp } from "@/components/evaluate/evaluate-app";
import type { EvaluateResponse } from "@/lib/api";
import { BackendProvider } from "@/lib/backend";
import { fakeBackend, RESULT, sse, STEPS } from "@/test/backend";

const TRACE = "0af7651916cd43dd8448eb211c80319c";
const TRACED: EvaluateResponse = {
  ...RESULT,
  trace_id: TRACE,
  trace_url: `https://cloud.langfuse.com/project/p1/traces/${TRACE}`,
};

async function evaluate(result: EvaluateResponse, recorded = true) {
  const backend = fakeBackend({
    "POST /evaluate/stream": () => ({ stream: sse(STEPS, { result }) }),
    "POST /feedback": { status: 202, body: { recorded } },
  });
  const user = userEvent.setup();
  render(
    <BackendProvider>
      <EvaluateApp />
    </BackendProvider>,
  );
  await user.type(screen.getByLabelText("The brief"), "An idea");
  await user.click(screen.getByRole("checkbox", { name: /Research it and check the brief first/ }));
  await user.click(screen.getByRole("button", { name: /^Evaluate\s*⌘↵$/ }));
  await screen.findByRole("heading", { name: "Go with conditions" });
  return { ...backend, user };
}

describe("Langfuse on the result", () => {
  test("a traced run links to its trace, beside the reviews and in the Run tab", async () => {
    const { user } = await evaluate(TRACED);
    const reviews = screen.getByRole("complementary", { name: "The team's reviews" });
    const link = within(reviews).getByRole("link", { name: "Open the run in Langfuse ↗" });
    expect(link.getAttribute("href")).toBe(TRACED.trace_url);
    expect(link.getAttribute("target")).toBe("_blank");

    await user.click(screen.getByRole("tab", { name: "Run" }));
    expect(screen.getByRole("tabpanel", { name: "Run" }).querySelector(`a[href="${TRACED.trace_url}"]`)).toBeTruthy();
  });

  test("the founder's verdict and comment are sent as a score on the run", async () => {
    const { user, sent } = await evaluate(TRACED);
    const form = screen.getByRole("form", { name: "Was this strategy useful?" });
    expect(within(form).queryByRole("button", { name: "Send" })).toBeNull();

    await user.click(within(form).getByRole("button", { name: "Not useful" }));
    expect(within(form).getByRole("button", { name: "Not useful" }).getAttribute("aria-pressed")).toBe("true");
    await user.type(within(form).getByLabelText(/What would have made it useful\?/), "Name owners for the next steps.");
    await user.click(within(form).getByRole("button", { name: "Send" }));

    expect((await screen.findByRole("status")).textContent).toContain("Your verdict is a score on this run in Langfuse");
    expect(sent.at(-1)).toEqual({
      path: "/feedback",
      body: { session_id: RESULT.session_id, trace_id: TRACE, useful: false, comment: "Name owners for the next steps." },
    });
  });

  test("a verdict the server could not keep says so", async () => {
    const { user } = await evaluate(TRACED, false);
    const form = screen.getByRole("form", { name: "Was this strategy useful?" });
    await user.click(within(form).getByRole("button", { name: "Useful" }));
    await user.click(within(form).getByRole("button", { name: "Send" }));
    expect((await screen.findByRole("status")).textContent).toContain("was not kept");
  });

  test("without Langfuse there is no trace link and no verdict to give", async () => {
    await evaluate(RESULT);
    expect(screen.queryByRole("link", { name: /Open the run in Langfuse/ })).toBeNull();
    expect(screen.queryByRole("form", { name: "Was this strategy useful?" })).toBeNull();
  });
});

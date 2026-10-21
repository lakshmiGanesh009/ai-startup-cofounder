import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { DocumentNamesProvider } from "@/components/documents";
import { EvaluateApp } from "@/components/evaluate/evaluate-app";
import { Markdown } from "@/components/markdown";
import ReportsPage from "@/app/reports/page";
import type { UploadSummary } from "@/lib/api";
import { BackendProvider } from "@/lib/backend";
import { type Answer, fakeBackend } from "@/test/backend";
import { fakeReports, SAMPLE_REPORT, SESSION } from "@/test/reports";

const PLAN: UploadSummary = {
  id: "a".repeat(32),
  name: "plan.pdf",
  kind: "PDF",
  parts: "12 pages",
  size: 48_000,
  characters: 21_000,
  warnings: [],
  preview: "Clinic plan. We charge $149 a month.",
};

const EARLIER = { session_id: "earlier-1", title: "Dental reminders", version: 2, has_proposal: false, edited: false, outdated: false, updated_at: "2026-10-18T09:30:00Z" };

const file = (name: string, size = 20) => new File(["x".repeat(size)], name, { type: "application/pdf" });

function renderEvaluate() {
  return render(
    <BackendProvider>
      <EvaluateApp />
    </BackendProvider>,
  );
}

describe("documents for a run", () => {
  test("files and an earlier report go with the brief, and the result names them", async () => {
    const { sent, fetch } = fakeBackend({
      "POST /uploads": { status: 201, body: { upload: PLAN, guardrails: [] } },
      "GET /reports": { body: [EARLIER] },
    });
    const user = userEvent.setup();
    renderEvaluate();

    await user.type(screen.getByLabelText("The brief"), "An idea");
    await user.upload(screen.getByLabelText("Add files"), file("plan.pdf"));
    const files = await screen.findByRole("list", { name: "Files" });
    expect(await within(files).findByText("PDF · 12 pages")).toBeTruthy();
    expect(within(files).getByText("D1")).toBeTruthy();
    expect(String(fetch.mock.calls.find(([url]) => String(url).includes("/uploads"))?.[0])).toBe("/api/uploads?name=plan.pdf");

    await user.selectOptions(await screen.findByLabelText("Add an earlier report"), "earlier-1");
    expect(within(screen.getByRole("list", { name: "Earlier reports" })).getByText("R1")).toBeTruthy();

    await user.click(screen.getByRole("checkbox", { name: /Research it and check the brief first/ }));
    await user.click(screen.getByRole("button", { name: /^Evaluate\s*⌘↵$/ }));

    expect(await screen.findByRole("heading", { name: "Go with conditions" })).toBeTruthy();
    expect(sent.find((call) => call.path === "/evaluate/stream")?.body).toMatchObject({
      context: { uploads: [PLAN.id], reports: ["earlier-1"] },
    });
    expect(screen.getByText("Worked from:")).toBeTruthy();
    expect(screen.getByText("Dental reminders")).toBeTruthy();
  });

  test("a file that cannot be read says why, and is not sent", async () => {
    const { sent } = fakeBackend({
      "POST /uploads": { status: 422, body: { detail: "This is not a kind of file the team can read." } },
      "GET /reports": { body: [] },
    });
    const user = userEvent.setup();
    renderEvaluate();

    await user.type(screen.getByLabelText("The brief"), "An idea");
    await user.upload(screen.getByLabelText("Add files"), [file("scan.pdf"), file("huge.pdf", 10_000_001)]);
    expect(await screen.findByText("This is not a kind of file the team can read.")).toBeTruthy();
    expect(screen.getByText("The file is larger than 10 MB.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Remove huge.pdf" }));
    expect(screen.queryByText("huge.pdf")).toBeNull();

    await user.click(screen.getByRole("checkbox", { name: /Research it and check the brief first/ }));
    await user.click(screen.getByRole("button", { name: /^Evaluate\s*⌘↵$/ }));
    await screen.findByRole("heading", { name: "Go with conditions" });
    expect(sent.find((call) => call.path === "/evaluate/stream")?.body).toMatchObject({ context: null });
  });

  test("the brief waits until the files are read", async () => {
    let finish: (value: Answer) => void = () => {};
    const { sent } = fakeBackend({
      "POST /uploads": () => new Promise((resolve) => (finish = resolve)),
      "GET /reports": { body: [] },
    });
    const user = userEvent.setup();
    renderEvaluate();

    await user.type(screen.getByLabelText("The brief"), "An idea");
    await user.upload(screen.getByLabelText("Add files"), file("plan.pdf"));
    expect(screen.getByText("Reading…")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /^Check the brief/ }));
    expect(screen.getByRole("alert").textContent).toBe("Wait until the files have been read.");
    expect(sent.some((call) => call.path === "/brief/prepare")).toBe(false);

    finish({ status: 201, body: { upload: PLAN, guardrails: [] } });
    await screen.findByText("PDF · 12 pages");
    await user.click(screen.getByRole("button", { name: /^Check the brief/ }));
    await waitFor(() => expect(sent.find((call) => call.path === "/brief/prepare")?.body).toMatchObject({ context: { uploads: [PLAN.id] } }));
    expect(await screen.findByText("With your documents:")).toBeTruthy();
  });
});

describe("citations of the documents", () => {
  test("a passage's mark is set as a tag that names its document", () => {
    render(
      <DocumentNamesProvider value={[{ ref: "D1", name: "plan.pdf", detail: "PDF · 12 pages" }]}>
        <Markdown>
          {"Churn is 4% a month [D1 · page 3], below plan [R2 · Financial Plan; D1 · sheet Revenue, rows 2–7]. " +
            "Price it at $99 [D1; finance] [D1; see below], as the web says [3]. All of them [D1–D3, R1]."}
        </Markdown>
      </DocumentNamesProvider>,
    );
    const tags = [...document.querySelectorAll(".doc-cite, .cite")].map((tag) => [tag.textContent, tag.getAttribute("title")]);
    expect(tags).toEqual([
      ["D1page 3", "plan.pdf, page 3"],
      ["R2Financial Plan", "Document R2, Financial Plan"],
      ["D1sheet Revenue, rows 2–7", "plan.pdf, sheet Revenue, rows 2–7"],
      ["D1", "plan.pdf"],
      ["Finance", "From Financial Planning"],
      ["D1", "plan.pdf"],
      ["D1–D3", "Document D1–D3"],
      ["R1", "Document R1"],
    ]);
    // What is not a citation stays: a note beside one, and the web's numbered sources.
    expect(document.body.textContent).toContain("see below");
    expect(document.body.textContent).toContain("[3]");
  });
});

describe("asking about a report", () => {
  test("the Chief of Staff answers from the report and its files, citing the passages", async () => {
    const answer = {
      answer: "Churn is 4% a month [D1 · page 3], which the report's plan assumes too [R1 · Launch Strategy].",
      sources: [
        { mark: "[D1 · page 3]", name: "plan.pdf", where: "page 3", text: "Churn is 4% a month in the pilot." },
        { mark: "[R1 · Launch Strategy]", name: SAMPLE_REPORT.title, where: "Launch Strategy", text: "Plan for 4% churn." },
      ],
      guardrails: [],
    };
    const { sent, state } = fakeReports({
      extra: {
        [`GET /uploads/${PLAN.id}`]: { body: PLAN },
        "POST /ask": { body: answer },
      },
    });
    // The run the report came from worked from a file.
    state.report = { ...state.report, worked_from: { uploads: [PLAN.id], reports: [] } };
    const user = userEvent.setup();
    render(
      <BackendProvider>
        <ReportsPage />
      </BackendProvider>,
    );

    await user.click(await screen.findByRole("button", { name: "Ask about it" }));
    const dialog = await screen.findByRole("dialog", { name: "Ask about this report" });
    const asking = await within(dialog).findByRole("complementary", { name: "Documents to ask about" });
    expect(within(asking).getByText(SAMPLE_REPORT.title)).toBeTruthy();
    expect(await within(asking).findByText("plan.pdf")).toBeTruthy();

    await user.type(within(dialog).getByLabelText("Your question"), "What churn did we assume?");
    await user.click(within(dialog).getByRole("button", { name: /^Ask/ }));

    const answered = await within(dialog).findByRole("article", { name: "What churn did we assume?" });
    expect(sent.find((call) => call.path === "/ask")?.body).toEqual({
      question: "What churn did we assume?",
      uploads: [PLAN.id],
      reports: [SESSION],
      reasoning: { specialist: "minimal", chief: "medium" },
    });
    expect(answered.querySelectorAll(".doc-cite")).toHaveLength(2);
    await user.click(within(answered).getByText("2 passages cited"));
    expect(within(answered).getByText("Churn is 4% a month in the pilot.")).toBeTruthy();
  });
});

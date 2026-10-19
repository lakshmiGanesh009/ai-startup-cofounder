import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { PageHeader, titleSize } from "@/components/ui/page-header";

test("a page's header names it and says what it is for", () => {
  render(<PageHeader title="Reports" description="Each session's report." aside={<button type="button">Pick</button>} />);

  expect(screen.getByRole("heading", { level: 1, name: "Reports" })).toBeTruthy();
  expect(screen.getByText("Each session's report.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Pick" })).toBeTruthy();
});

test("the longer a document's title, the smaller it is set", () => {
  expect(titleSize("Decide whether to launch a paid pilot.")).toBe("text-[1.75rem]");
  expect(titleSize("x".repeat(150))).toBe("text-[1.5rem]");
  expect(titleSize("x".repeat(250))).toBe("text-[1.3rem]");
});

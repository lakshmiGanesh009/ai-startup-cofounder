import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { EvaluateApp } from "@/components/evaluate/evaluate-app";
import { insertInto, Voice } from "@/components/voice";
import { BackendProvider } from "@/lib/backend";
import { fakeBackend, HEALTH } from "@/test/backend";

// A stand-in for the browser's recorder: what it records is `recorded`.
let recorded = 4_000;
class FakeRecorder {
  static isTypeSupported = (type: string) => type === "audio/webm;codecs=opus";
  state: "inactive" | "recording" = "inactive";
  mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(_stream: unknown, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? "";
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob([new Uint8Array(recorded)], { type: this.mimeType }) });
    this.onstop?.();
  }
}

const stopTrack = vi.fn();
const getUserMedia = vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] }));

beforeEach(() => {
  recorded = 4_000;
  stopTrack.mockClear();
  getUserMedia.mockClear();
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function Box({ multiline = false, start = "Price it at." }: { multiline?: boolean; start?: string }) {
  const [value, setValue] = useState(start);
  return (
    <>
      <Voice label="the brief" multiline={multiline}>
        {multiline ? (
          <textarea aria-label="Brief" value={value} onChange={(event) => setValue(event.target.value)} />
        ) : (
          <input aria-label="Brief" value={value} onChange={(event) => setValue(event.target.value)} />
        )}
      </Voice>
      <output aria-label="What the page holds">{value}</output>
    </>
  );
}

const held = () => screen.getByRole("status", { name: "What the page holds" }).textContent;

describe("dictation", () => {
  test("writes down what is said where the cursor was, as if typed", async () => {
    const { sent } = fakeBackend({ "POST /transcribe": { body: { text: " launch at $99 a month " } } });
    render(<Box />);
    const field = screen.getByRole("textbox", { name: "Brief" }) as HTMLInputElement;
    field.focus();
    field.setSelectionRange(8, 8);

    await userEvent.click(screen.getByRole("button", { name: "Dictate into the brief" }));
    const stop = await screen.findByRole("button", { name: /^Stop and write it down \(0:00 recorded\)$/ });
    expect(stop.getAttribute("data-phase")).toBe("recording");
    expect(stop.querySelectorAll(".voice-bars > span")).toHaveLength(5);
    expect(document.activeElement).toBe(field);

    await userEvent.click(stop);
    // The words go in at the cursor, spaced from those either side, and the page's own state has them.
    await waitFor(() => expect(held()).toBe("Price it launch at $99 a month at."));
    expect(field.selectionStart).toBe("Price it launch at $99 a month".length);
    const [request] = sent.filter((each) => each.path === "/transcribe");
    expect(request.body).toBeInstanceOf(Blob);
    expect((request.body as Blob).type).toBe("audio/webm;codecs=opus");
    expect(stopTrack).toHaveBeenCalled();
  });

  test("Enter writes it down, and Escape throws it away without sending it", async () => {
    const { sent } = fakeBackend({ "POST /transcribe": { body: { text: "Two pilots." } } });
    render(<Box multiline start="" />);
    expect(document.querySelector(".voice-field")?.getAttribute("data-lines")).toBe("many");

    await userEvent.click(screen.getByRole("button", { name: "Dictate into the brief" }));
    await screen.findByRole("button", { name: /^Stop and write it down/ });
    await userEvent.keyboard("{Escape}");
    await screen.findByRole("button", { name: "Dictate into the brief" });
    expect(sent.some((each) => each.path === "/transcribe")).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "Dictate into the brief" }));
    await screen.findByRole("button", { name: /^Stop and write it down/ });
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(held()).toBe("Two pilots."));
  });

  test("says why when it cannot write anything down", async () => {
    fakeBackend({ "POST /transcribe": { status: 502, body: { detail: "The speech-to-text call failed: 401." } } });
    render(<Box />);
    const mic = () => screen.getByRole("button", { name: "Dictate into the brief" });

    await userEvent.click(mic());
    await userEvent.click(await screen.findByRole("button", { name: /^Stop and write it down/ }));
    expect(await screen.findByText(/The speech-to-text call failed: 401\./)).toBeTruthy();
    expect(held()).toBe("Price it at.");

    recorded = 200;
    await userEvent.click(mic());
    await userEvent.click(await screen.findByRole("button", { name: /^Stop and write it down/ }));
    expect(await screen.findByText(/too short to hear/)).toBeTruthy();

    getUserMedia.mockRejectedValueOnce(Object.assign(new Error("denied"), { name: "NotAllowedError" }));
    await userEvent.click(mic());
    expect(await screen.findByText(/The microphone is blocked/)).toBeTruthy();
  });

  test("offers no mic when the API has no Whisper deployment, and leaves the box as it is", async () => {
    const { fetch } = fakeBackend({ "GET /health": { body: { ...HEALTH, voice: { dictation: false } } } });
    render(
      <BackendProvider>
        <Box />
      </BackendProvider>,
    );
    // Once the API has said what it has.
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/health"))).toBe(true));
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
    expect(screen.queryByRole("button", { name: "Dictate into the brief" })).toBeNull();
    expect(screen.getByRole("textbox", { name: "Brief" })).toBeTruthy();
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  test("a word is spaced from those either side, and a box's length is kept", () => {
    const field = document.createElement("textarea");
    document.body.append(field);
    field.value = "Launch";
    insertInto(field, "in Ohio", null);
    expect(field.value).toBe("Launch in Ohio");
    insertInto(field, "now", [0, 0]);
    expect(field.value).toBe("now Launch in Ohio");
    field.maxLength = 12;
    insertInto(field, "with a pilot", null);
    expect(field.value).toBe("now Launch i");
    field.remove();
  });

  test("the Evaluate page's input boxes each have the mic", async () => {
    fakeBackend();
    render(
      <BackendProvider>
        <EvaluateApp />
      </BackendProvider>,
    );
    for (const name of ["the brief", "Target market", "Constraints", "Competition"]) {
      expect(await screen.findByRole("button", { name: `Dictate into ${name}` })).toBeTruthy();
    }
  });
});

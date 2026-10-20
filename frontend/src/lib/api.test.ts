import { describe, expect, test, vi } from "vitest";

import { ApiError, evaluate, evaluateStream, getHealth, getScenarios, getTemplates, prepareBrief, type Step } from "@/lib/api";
import { fakeBackend, HEALTH, liveStream, PREPARED, RESULT, SCENARIOS, sse, STEPS, TEMPLATES } from "@/test/backend";

// The error a call fails with.
async function failure(call: Promise<unknown>): Promise<ApiError> {
  try {
    await call;
  } catch (error) {
    return error as ApiError;
  }
  throw new Error("The call succeeded.");
}

describe("the API client", () => {
  test("reads the health check, the scenarios and the templates", async () => {
    fakeBackend();

    expect(await getHealth()).toEqual(HEALTH);
    expect(await getScenarios()).toEqual(SCENARIOS);
    expect(await getTemplates()).toEqual(TEMPLATES);
  });

  test("posts a brief to be prepared", async () => {
    const { sent } = fakeBackend();

    const prepared = await prepareBrief({ prompt: "An idea", context: null, template: "pricing", reasoning: null });

    expect(prepared).toEqual(PREPARED);
    expect(sent).toEqual([{ path: "/brief/prepare", body: { prompt: "An idea", context: null, template: "pricing", reasoning: null } }]);
  });

  test("posts an evaluation as JSON", async () => {
    const { fetch, sent } = fakeBackend();

    const result = await evaluate({ prompt: "An idea", session_id: null, reasoning: { chief: "high" } });

    expect(result).toEqual(RESULT);
    expect(sent).toEqual([{ path: "/evaluate", body: { prompt: "An idea", session_id: null, reasoning: { chief: "high" } } }]);
    expect(fetch.mock.calls[0][1]?.headers).toEqual({ "Content-Type": "application/json" });
  });

  test("an error carries the backend's reason and status", async () => {
    fakeBackend({ "POST /evaluate": { status: 503, body: { detail: "No LLM provider configured." } } });

    const error = await failure(evaluate({ prompt: "An idea" }));

    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe("The backend returned 503: No LLM provider configured.");
    expect(error.status).toBe(503);
  });

  test("an error names the request, so it can be found in the API's logs", async () => {
    fakeBackend({
      "POST /evaluate": {
        status: 500,
        body: { detail: "The server failed unexpectedly.", request_id: "3f2a9c1b7d4e5f60" },
        headers: { "X-Request-ID": "3f2a9c1b7d4e5f60" },
      },
      "POST /evaluate/stream": {
        stream: sse(STEPS.slice(0, 2), { error: { status: 502, detail: "The LLM call failed: timeout" } }),
        headers: { "X-Request-ID": "a1b2c3d4e5f60718" },
      },
    });

    const error = await failure(evaluate({ prompt: "An idea" }));
    expect(error.message).toBe("The backend returned 500: The server failed unexpectedly. (request 3f2a9c1b7d4e5f60)");
    expect(error.requestId).toBe("3f2a9c1b7d4e5f60");

    const streamed = await failure(evaluateStream({ prompt: "An idea" }, () => {}));
    expect(streamed.message).toBe("The backend returned 502: The LLM call failed: timeout (request a1b2c3d4e5f60718)");
  });

  test("a validation error lists its problems", async () => {
    fakeBackend({
      "POST /evaluate": {
        status: 422,
        body: { detail: [{ msg: "Input should be 'minimal', 'low', 'medium' or 'high'" }, {}] },
      },
    });

    await expect(evaluate({ prompt: "An idea" })).rejects.toThrow(
      "422: Input should be 'minimal', 'low', 'medium' or 'high'; Invalid request",
    );
  });

  test("an error without a reason gives its status", async () => {
    fakeBackend({ "GET /health": { status: 500, body: null } });

    await expect(getHealth()).rejects.toThrow("The backend returned 500: HTTP 500");
  });

  test("an unreachable backend is named", async () => {
    fakeBackend({ "GET /health": undefined });

    const error = await failure(getHealth());

    expect(error.message).toBe("Could not reach this app's server; check the connection.");
    expect(error.status).toBeNull();
  });
});

describe("the streamed evaluation", () => {
  test("reports each step as it arrives, then resolves with the result", async () => {
    const live = liveStream();
    const { fetch, sent } = fakeBackend({ "POST /evaluate/stream": () => ({ stream: live.stream }) });
    const steps: Step[] = [];

    const running = evaluateStream({ prompt: "An idea" }, (step) => steps.push(step));
    // Events split across chunks anywhere, with the line endings some proxies use.
    const text = `: a comment to keep the connection open\n\n${sse(STEPS.slice(0, 3), { result: RESULT })}`.replace(/\n/g, "\r\n");
    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    live.send(text.slice(0, 50));
    live.send(text.slice(50, 333));
    live.send(text.slice(333));

    expect(await running).toEqual(RESULT);
    expect(steps).toEqual(STEPS.slice(0, 3));
    expect(sent).toEqual([{ path: "/evaluate/stream", body: { prompt: "An idea" } }]);
    expect(fetch.mock.calls[0][1]?.headers).toEqual({ "Content-Type": "application/json", Accept: "text/event-stream" });
  });

  test("an error partway through carries the backend's status and reason", async () => {
    fakeBackend({
      "POST /evaluate/stream": () => ({ stream: sse(STEPS.slice(0, 2), { error: { status: 502, detail: "The LLM call failed: timeout" } }) }),
    });
    const steps: Step[] = [];

    const error = await failure(evaluateStream({ prompt: "An idea" }, (step) => steps.push(step)));

    expect(error.message).toBe("The backend returned 502: The LLM call failed: timeout");
    expect(error.status).toBe(502);
    expect(steps).toHaveLength(2);
  });

  test("a stream that ends, or breaks, before the result is a lost connection", async () => {
    fakeBackend({ "POST /evaluate/stream": () => ({ stream: sse(STEPS.slice(0, 2), null) }) });
    expect((await failure(evaluateStream({ prompt: "An idea" }, () => {}))).message).toBe(
      "The connection to the backend was lost before the evaluation finished.",
    );

    const live = liveStream();
    fakeBackend({ "POST /evaluate/stream": () => ({ stream: live.stream }) });
    const running = failure(evaluateStream({ prompt: "An idea" }, () => {}));
    await vi.waitFor(() => live.fail());
    expect((await running).message).toBe("The connection to the backend was lost before the evaluation finished.");
  });

  test("a refused request, or an unreachable backend, fails before any step", async () => {
    fakeBackend({ "POST /evaluate/stream": { status: 422, body: { detail: [{ msg: "Field required" }] } } });
    const refused = await failure(evaluateStream({ prompt: "" }, () => {}));
    expect(refused.message).toBe("The backend returned 422: Field required");
    expect(refused.status).toBe(422);

    fakeBackend({ "POST /evaluate/stream": undefined });
    expect((await failure(evaluateStream({ prompt: "An idea" }, () => {}))).message).toBe(
      "Could not reach this app's server; check the connection.",
    );
  });
});

import { describe, expect, test } from "vitest";

import { ApiError, evaluate, getHealth, getScenarios } from "@/lib/api";
import { fakeBackend, HEALTH, RESULT, SCENARIOS } from "@/test/backend";

describe("the API client", () => {
  test("reads the health check and the scenarios", async () => {
    fakeBackend();

    expect(await getHealth()).toEqual(HEALTH);
    expect(await getScenarios()).toEqual(SCENARIOS);
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

    const error = await evaluate({ prompt: "An idea" }).catch((reason: ApiError) => reason);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe("The backend returned 503: No LLM provider configured.");
    expect(error.status).toBe(503);
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

    const error = await getHealth().catch((reason: ApiError) => reason);

    expect(error.message).toBe("Could not reach the backend at http://localhost:8000.");
    expect(error.status).toBeNull();
  });
});

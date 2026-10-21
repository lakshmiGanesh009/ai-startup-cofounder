import { afterEach, describe, expect, test, vi } from "vitest";

// The proxy reads where the API is and its body cap when it loads.
process.env.BACKEND_URL = "http://api.test:8000/";
process.env.MAX_REQUEST_BYTES = "100";
process.env.MAX_UPLOAD_BYTES = "300";
const { GET, POST } = await import("./route");

type Handler = typeof GET;

function call(handler: Handler, url: string, init?: RequestInit) {
  const path = new URL(url).pathname.replace(/^\/api\//, "").split("/");
  return handler(new Request(url, init), { params: Promise.resolve({ path }) });
}

function backend(answer: () => Response | Promise<Response>) {
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    void url;
    void init;
    return answer();
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  delete process.env.API_KEY;
});

describe("the API proxy", () => {
  test("forwards a call with the API's key, and passes back only what the page needs", async () => {
    process.env.API_KEY = "server-side-key";
    const fetch = backend(
      () =>
        new Response('{"ok":true}', {
          status: 201,
          headers: { "content-type": "application/json", "x-request-id": "3f2a9c1b7d4e5f60", "set-cookie": "a=1", server: "uvicorn" },
        }),
    );

    const answer = await call(GET, "http://app.test/api/reports/s-1?x=1", {
      headers: { accept: "application/json", cookie: "session=1", "x-forwarded-for": "203.0.113.7" },
    });

    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("http://api.test:8000/reports/s-1?x=1");
    const sent = new Headers(init.headers);
    expect(sent.get("authorization")).toBe("Bearer server-side-key");
    expect(sent.get("x-forwarded-for")).toBe("203.0.113.7");
    expect(sent.get("accept")).toBe("application/json");
    expect(sent.get("cookie")).toBeNull();
    expect(answer.status).toBe(201);
    expect(answer.headers.get("x-request-id")).toBe("3f2a9c1b7d4e5f60");
    expect(answer.headers.get("set-cookie")).toBeNull();
    expect(answer.headers.get("server")).toBeNull();
    expect(answer.headers.get("cache-control")).toBe("no-store");
    expect(await answer.json()).toEqual({ ok: true });
  });

  test("without a key on the server, none is sent", async () => {
    const fetch = backend(() => Response.json({ status: "healthy" }));

    await call(GET, "http://app.test/api/health");

    expect(new Headers(fetch.mock.calls[0][1].headers).get("authorization")).toBeNull();
  });

  test("streams an evaluation's events through as they come", async () => {
    const encoder = new TextEncoder();
    backend(
      () =>
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(encoder.encode('event: start\ndata: {"node":"plan"}\n\n'));
              controller.enqueue(encoder.encode('event: result\ndata: {"ok":true}\n\n'));
              controller.close();
            },
          }),
          { headers: { "content-type": "text/event-stream" } },
        ),
    );

    const answer = await call(POST, "http://app.test/api/evaluate/stream", { method: "POST", body: '{"prompt":"x"}' });

    expect(answer.headers.get("content-type")).toBe("text/event-stream");
    expect(answer.headers.get("cache-control")).toBe("no-cache, no-transform");
    expect(answer.headers.get("x-accel-buffering")).toBe("no");
    expect(await answer.text()).toBe('event: start\ndata: {"node":"plan"}\n\nevent: result\ndata: {"ok":true}\n\n');
  });

  test("forwards a body, and refuses one over the cap before reading it all", async () => {
    const fetch = backend(() => Response.json({ ok: true }));

    await call(POST, "http://app.test/api/brief/prepare", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: '{"prompt":"An idea."}',
    });
    const said = await call(POST, "http://app.test/api/brief/prepare", {
      method: "POST",
      headers: { "content-length": "101" },
      body: "x".repeat(101),
    });
    const unsaid = await call(POST, "http://app.test/api/brief/prepare", {
      method: "POST",
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode("x".repeat(80)));
          controller.enqueue(new TextEncoder().encode("x".repeat(80)));
          controller.close();
        },
      }),
      duplex: "half",
    } as RequestInit);

    expect(new TextDecoder().decode(fetch.mock.calls[0][1].body as Uint8Array)).toBe('{"prompt":"An idea."}');
    expect([said.status, unsaid.status]).toEqual([413, 413]);
    expect((await said.json()).detail).toBe("The request is larger than the 100 bytes the API accepts.");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  test("lets an uploaded file be larger than other requests, up to its own limit", async () => {
    const fetch = backend(() => Response.json({}, { status: 201 }));

    const upload = await call(POST, "http://app.test/api/uploads?name=plan.pdf", { method: "POST", body: "x".repeat(250) });
    const tooLarge = await call(POST, "http://app.test/api/uploads?name=plan.pdf", { method: "POST", body: "x".repeat(301) });
    const question = await call(POST, "http://app.test/api/ask", { method: "POST", body: "x".repeat(250) });

    expect([upload.status, tooLarge.status, question.status]).toEqual([201, 413, 413]);
    expect((await tooLarge.json()).detail).toBe("The request is larger than the 300 bytes the API accepts.");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("http://api.test:8000/uploads?name=plan.pdf");
  });

  test("forwards only the API's routes the pages use", async () => {
    const fetch = backend(() => Response.json({}));

    const metrics = await call(GET, "http://app.test/api/metrics");
    const climbing = await GET(new Request("http://app.test/api/reports/x"), {
      params: Promise.resolve({ path: ["reports", ".."] }),
    });

    expect([metrics.status, climbing.status]).toEqual([404, 404]);
    expect(fetch).not.toHaveBeenCalled();
  });

  test("an API that cannot be reached is a 502 that says so", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    const answer = await call(GET, "http://app.test/api/health");

    expect(answer.status).toBe(502);
    expect(await answer.json()).toEqual({ detail: "The API could not be reached." });
  });
});

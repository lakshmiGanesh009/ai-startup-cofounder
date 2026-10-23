// The browser's way to the API. The pages call /api/<path> on this app's own
// origin, and this forwards the call to the API (BACKEND_URL) with the API's
// key (API_KEY), so the key stays on this server and never reaches a browser.
// The answer streams back as it comes: an evaluation's events, a PDF, JSON.
// Only the API's routes the pages use are forwarded, and a body is capped
// before it is held in memory: an uploaded file at the upload limit, anything
// else at the request limit.

const BACKEND = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const MAX_BYTES = Number(process.env.MAX_REQUEST_BYTES ?? 1_000_000);
const MAX_UPLOAD_BYTES = Number(process.env.MAX_UPLOAD_BYTES ?? 10_000_000);
const ROUTES = new Set([
  "health",
  "scenarios",
  "templates",
  "rates",
  "pipeline",
  "monitoring",
  "brief",
  "evaluate",
  "reports",
  "uploads",
  "ask",
  "feedback",
]);
const SEGMENT = /^[A-Za-z0-9_-]{1,64}$/;
// What goes on to the API, and what comes back from it.
const FORWARDED = ["content-type", "accept", "x-request-id"];
const RETURNED = ["content-type", "content-disposition", "x-request-id", "retry-after", "www-authenticate"];

function problem(status: number, detail: string): Response {
  return Response.json({ detail }, { status, headers: { "cache-control": "no-store" } });
}

// The body, or null when it is larger than `most` bytes; read only that far.
async function cappedBody(request: Request, most: number): Promise<Uint8Array<ArrayBuffer> | null> {
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array(0);
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > most) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let at = 0;
  for (const chunk of chunks) {
    body.set(chunk, at);
    at += chunk.byteLength;
  }
  return body;
}

async function forward(request: Request, { params }: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await params;
  if (!ROUTES.has(path[0]) || !path.every((segment) => SEGMENT.test(segment))) {
    return problem(404, "There is no such API route.");
  }
  const headers = new Headers();
  for (const name of FORWARDED) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (process.env.API_KEY) headers.set("authorization", `Bearer ${process.env.API_KEY}`);
  // The browser's address, for the API's per-caller limits: what the proxy in
  // front of this app says, which the API trusts because the key comes with it.
  const forwardedFor = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);

  let body: Uint8Array<ArrayBuffer> | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    const most = request.method === "POST" && path.length === 1 && path[0] === "uploads" ? MAX_UPLOAD_BYTES : MAX_BYTES;
    const length = Number(request.headers.get("content-length") ?? 0);
    const read = length > most ? null : await cappedBody(request, most);
    if (!read) return problem(413, `The request is larger than the ${most.toLocaleString("en")} bytes the API accepts.`);
    body = read;
  }

  let answer: Response;
  try {
    answer = await fetch(`${BACKEND}/${path.join("/")}${new URL(request.url).search}`, {
      method: request.method,
      headers,
      body,
      signal: request.signal,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return problem(502, "The API could not be reached.");
  }
  const returned = new Headers();
  for (const name of RETURNED) {
    const value = answer.headers.get(name);
    if (value) returned.set(name, value);
  }
  // Each event as it comes: nothing on the way may cache, buffer or compress it.
  const streamed = returned.get("content-type")?.startsWith("text/event-stream");
  returned.set("cache-control", streamed ? "no-cache, no-transform" : "no-store");
  if (streamed) returned.set("x-accel-buffering", "no");
  return new Response(answer.body, { status: answer.status, headers: returned });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const DELETE = forward;

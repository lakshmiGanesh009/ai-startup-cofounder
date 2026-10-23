"""Who may call the API, and how much, checked on every request before it
reaches a route, in this order:

- The key: with API_KEY set, every request but /health must carry it, as
  `Authorization: Bearer <key>` or `X-API-Key: <key>` (401 otherwise). The
  Next.js app's server adds it to the browser's calls it forwards, so the key
  never reaches a browser.
- Size: a body over MAX_REQUEST_BYTES is refused (413), whether it says how
  long it is or not; an uploaded file (POST /uploads) and a recording to
  write down (POST /transcribe) may be up to the upload limit instead.
- Rate: each caller may send REQUESTS_PER_MINUTE requests a minute and start
  RUNS_PER_HOUR runs (evaluations, briefs and proposals) an hour (429, with
  Retry-After). A caller is its address or, behind the app's proxy, the browser
  address the proxy forwards (X-Forwarded-For); only a request with the key may
  name one, so a caller cannot pose as another.
- Runs: at most MAX_CONCURRENT_RUNS at once (429 while full), held until the
  response ends, a streamed one included, so a burst cannot exhaust the model
  deployment.

The counts live in the process, like the Monitor's statistics: with several
workers, each enforces its own share.
"""

import hmac
import json
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Literal

from pydantic_core import PydanticCustomError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

OPEN_PATHS = frozenset({"/health"})
# The requests that start a run: an evaluation, a brief, a proposal written or
# revised, one passage of a report revised, or a question about documents.
RUN_PATH = re.compile(r"/(evaluate(/stream)?|brief/prepare|ask|reports/[^/]+/(proposal(/revise)?|revise))")
# Where a file is uploaded or a recording sent: its body may be as large as the upload limit.
UPLOAD_PATHS = frozenset({"/uploads", "/transcribe"})

Reason = Literal["key", "size", "rate", "busy"]

# What a request may hold. A prompt or an instruction is a brief, not a
# document; the context's fields a paragraph or two; edits and proposals fit
# well within MAX_REQUEST_BYTES.
MAX_PROMPT_CHARS = 8_000
MAX_FIELD_CHARS = 4_000
MAX_ANSWERS = 10
MAX_QUESTION_CHARS = 500
MAX_ANSWER_CHARS = 2_000
MAX_FACTS = 20
MAX_FACT_CHARS = 1_000
MAX_SOURCES = 50
MAX_SOURCE_TITLE_CHARS = 500
MAX_URL_CHARS = 2_000
MAX_SECTIONS = 30
MAX_SECTION_CHARS = 60_000
SESSION_ID = r"^[A-Za-z0-9_-]{1,64}$"


class RateLimiter:
    """At most `limit` events a `window` of seconds for each key, counted from
    each event (a sliding window)."""

    MAX_KEYS = 10_000  # callers remembered before the idle ones are forgotten

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def take(self, key: str) -> float:
        """Count an event for `key`: 0 if it is allowed, else the seconds until
        one would be."""
        now = self.clock()
        with self._lock:
            if len(self._events) > self.MAX_KEYS:
                self._forget_idle(now)
            events = self._events.setdefault(key, deque())
            while events and events[0] <= now - self.window:
                events.popleft()
            if len(events) >= self.limit:
                return events[0] + self.window - now
            events.append(now)
            return 0.0

    def _forget_idle(self, now: float) -> None:
        for key in [key for key, events in self._events.items() if not events or events[-1] <= now - self.window]:
            del self._events[key]


class RunSlots:
    """How many runs may go at once."""

    def __init__(self, limit: int):
        self.limit = limit
        self.running = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.running >= self.limit:
                return False
            self.running += 1
            return True

    def give_back(self) -> None:
        with self._lock:
            self.running = max(self.running - 1, 0)


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope["headers"]:
        if key == name:
            return value.decode("latin-1")
    return ""


def _sent_key(scope: Scope) -> str:
    bearer = _header(scope, b"authorization")
    if bearer[:7].lower() == "bearer ":
        return bearer[7:].strip()
    return _header(scope, b"x-api-key").strip()


def _caller(scope: Scope, trusted: bool) -> str:
    """The caller's address: the browser's, as the app's proxy forwards it, when
    the request carries the key; else the connection's."""
    if trusted:
        forwarded = _header(scope, b"x-forwarded-for").split(",")[0].strip()
        if forwarded:
            return forwarded
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _refuse(send: Send, status: int, detail: str, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            *(headers or []),
        ],
    })
    await send({"type": "http.response.body", "body": body})


class Guard:
    """The key and the limits the API enforces; the middleware reads them on
    every request."""

    def __init__(self, api_key: str, max_bytes: int, requests_per_minute: int, runs_per_hour: int, max_runs: int,
                 upload_bytes: int = 0):
        self.api_key = api_key
        self.max_bytes = max_bytes
        self.upload_bytes = max(upload_bytes, max_bytes)
        self.requests = RateLimiter(requests_per_minute, 60)
        self.runs_rate = RateLimiter(runs_per_hour, 3600)
        self.slots = RunSlots(max_runs)


class GuardMiddleware:
    """The key, the size, the rates and the runs, in that order. `on_refuse`
    is told each refusal's reason (the monitor counts them)."""

    def __init__(self, app: ASGIApp, guard: Guard, on_refuse: Callable[[Reason], None] | None = None):
        self.app = app
        self.guard = guard
        self.on_refuse = on_refuse or (lambda reason: None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        guard = self.guard
        path, method = scope["path"], scope["method"]
        keyed = bool(guard.api_key) and hmac.compare_digest(_sent_key(scope).encode(), guard.api_key.encode())
        if guard.api_key and not keyed and path not in OPEN_PATHS:
            self.on_refuse("key")
            await _refuse(send, 401, "This API needs its key: send it as Authorization: Bearer <key>.",
                          [(b"www-authenticate", b'Bearer realm="cofounder"')])
            return

        most = guard.upload_bytes if method == "POST" and path in UPLOAD_PATHS else guard.max_bytes
        length = _header(scope, b"content-length")
        if length.isdigit() and int(length) > most:
            self.on_refuse("size")
            await _refuse(send, 413, _too_large(most))
            return

        caller = _caller(scope, keyed)
        run = method == "POST" and RUN_PATH.fullmatch(path) is not None
        wait = guard.requests.take(caller)
        if not wait and run:
            # A run turned away because the team is busy does not count against
            # the caller's runs; one over the caller's limit gives its slot back.
            if not guard.slots.take():
                self.on_refuse("busy")
                await _refuse(send, 429, f"The team is busy with {guard.slots.limit} runs; try again in a minute.",
                              [(b"retry-after", b"30")])
                return
            wait = guard.runs_rate.take(f"run:{caller}")
            if wait:
                guard.slots.give_back()
        if wait:
            self.on_refuse("rate")
            what = "evaluations, briefs and proposals" if run else "requests"
            await _refuse(send, 429, f"Too many {what} from this address; try again in {wait:.0f} s.",
                          [(b"retry-after", str(max(1, round(wait))).encode())])
            return
        try:
            await self._pass(scope, receive, send, most)
        finally:
            if run:
                guard.slots.give_back()

    async def _pass(self, scope: Scope, receive: Receive, send: Send, most: int) -> None:
        """Hand the request on. A body that outgrows `most` bytes as it is read
        (one that did not say its size) is answered 413 there and then, and the
        app is told the client has gone; its own answer is dropped."""
        read = 0
        responded = refused = False

        async def limited() -> Message:
            nonlocal read, refused
            message = await receive()
            if message["type"] == "http.request" and not refused:
                read += len(message.get("body", b""))
                if read > most:
                    refused = True
                    if not responded:
                        self.on_refuse("size")
                        await _refuse(send, 413, _too_large(most))
                    return {"type": "http.disconnect"}
            return message

        async def watched(message: Message) -> None:
            nonlocal responded
            if refused:
                return
            responded = responded or message["type"] == "http.response.start"
            await send(message)

        await self.app(scope, limited, watched)


def _too_large(most: int) -> str:
    return f"The request is larger than the {most:,} bytes the API accepts."


def _at_most(text: str, most: int, what: str) -> None:
    if len(text) > most:
        raise PydanticCustomError("too_long", "{what} is longer than {most} characters.", {"what": what, "most": f"{most:,}"})


def check_context(context):
    """A request's context, if it is no larger than a brief needs and its sources
    are web pages; else a validation error that says what is wrong."""
    if context is None:
        return None
    for name in ("target_market", "constraints", "competitive_landscape"):
        _at_most(getattr(context, name) or "", MAX_FIELD_CHARS, name.replace("_", " ").capitalize())
    if len(context.answers) > MAX_ANSWERS:
        raise PydanticCustomError("too_many", "At most {most} answers.", {"most": MAX_ANSWERS})
    for answer in context.answers:
        _at_most(answer.question, MAX_QUESTION_CHARS, "A question")
        _at_most(answer.answer, MAX_ANSWER_CHARS, "An answer")
    research = context.research
    if research:
        if len(research.findings) > MAX_FACTS or len(research.sources) > MAX_SOURCES:
            raise PydanticCustomError("too_many", "At most {facts} facts and {sources} sources.",
                                      {"facts": MAX_FACTS, "sources": MAX_SOURCES})
        for finding in research.findings:
            _at_most(finding.point, MAX_FACT_CHARS, "A fact")
        for source in research.sources:
            _at_most(source.title, MAX_SOURCE_TITLE_CHARS, "A source's title")
            _at_most(source.url, MAX_URL_CHARS, "A source's address")
            if not source.url.lower().startswith(("https://", "http://")):
                # Every source is shown as a link: no javascript: or data: ones.
                raise PydanticCustomError("not_web", "A source's address must start with http:// or https://.")
    return context


def check_sections(sections):
    """A report's sections, if none is longer than a report needs."""
    for section in sections:
        _at_most(section.title, MAX_SOURCE_TITLE_CHARS, "A section's title")
        _at_most(section.body, MAX_SECTION_CHARS, "A section")
    return sections

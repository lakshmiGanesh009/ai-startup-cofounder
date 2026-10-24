"""Tracing, prompts and scores in Langfuse (langfuse.com), when it is set up.

Every model call the team makes is traced in the shape of the work: one trace
for each request (an evaluation, a brief, the proposal, a revision, a
question), named for it and grouped by the session, with the graph's steps
inside it and, in each, its model calls with their prompt, reply, tokens, cost
and time. LangChain's callbacks do the work: while a trace is open, a context
variable holds Langfuse's handler, and LangChain adds it to every run it starts
(register_configure_hook), so no call site passes it, and the worker threads
the graph starts inherit it with the rest of the context.

The prompts stay in the code (the founder's choice): at start-up each is
registered in Langfuse, as a new version when its text has changed
(prompt_library.py), and each call is linked to the version it used. The
team's own judgements become scores (the Chief of Staff's review of each
report, the verdict, the conflicts, the revisions, text that tried to instruct
the agents), and so does the founder's feedback. Text is masked before it
leaves: email addresses, phone numbers, card numbers and keys.

Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set; then nothing
here does anything and nothing leaves the app. Tracing never fails a request:
a fault in it is logged and the work goes on untraced.
"""

import logging
import os
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from typing import Any

from langchain_core.tracers.context import register_configure_hook

log = logging.getLogger(__name__)

# Langfuse's LangChain handler for the trace open now; LangChain adds it to
# every run started in this context, and the runs inside inherit it.
_handler: ContextVar[Any] = ContextVar("langfuse_handler", default=None)
register_configure_hook(_handler, inheritable=True)

# Options for the client, set by tests (an in-memory span exporter, an HTTP
# client that answers for Langfuse).
_options: dict[str, Any] = {}
_client: Any = None
_failed = False
_lock = threading.Lock()

# The version in Langfuse of each of the app's prompts, as registered at start-up.
_versions: dict[str, int] = {}

# Seconds Langfuse may take to receive a batch of spans. An evaluation's spans
# carry the team's state, so a batch can be large, and the SDK's 5 s lost one in
# the live check; LANGFUSE_TIMEOUT overrides it.
SEND_TIMEOUT = 30


def enabled() -> bool:
    """Whether Langfuse is set up: its two keys are in the environment."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY", "").strip() and os.getenv("LANGFUSE_SECRET_KEY", "").strip())


def client():
    """The Langfuse client, made on first use; None when Langfuse is not set up
    or could not be started. It reads LANGFUSE_BASE_URL (the cloud region or a
    server of your own), LANGFUSE_TRACING_ENVIRONMENT, LANGFUSE_RELEASE and
    LANGFUSE_SAMPLE_RATE from the environment itself."""
    global _client, _failed
    if not enabled() or _failed:
        return None
    with _lock:
        if _client is None:
            try:
                from langfuse import Langfuse

                options = {"timeout": int(os.getenv("LANGFUSE_TIMEOUT") or SEND_TIMEOUT), **_options}
                _client = Langfuse(mask=mask, **options)
            except Exception as error:  # a bad setting must not stop the app
                log.warning("Langfuse could not be started, so nothing is traced: %s", error)
                _failed = True
                return None
        return _client


def reset() -> None:
    """Forget the client and the prompt versions (for tests, and a change of keys)."""
    global _client, _failed
    with _lock:
        if _client is not None:
            try:
                _client.shutdown()
            except Exception:
                pass
        _client = None
        _failed = False
    _versions.clear()


def flush() -> None:
    """Send what is still buffered; called as the API stops, and by scripts."""
    if _client is not None:
        try:
            _client.flush()
        except Exception as error:
            log.warning("Langfuse could not be flushed: %s", error)


# ---- Masking: what never leaves the app ----

def _luhn(digits: str) -> bool:
    total = 0
    for index, digit in enumerate(reversed(digits)):
        value = int(digit) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def _card(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "[card number]" if 13 <= len(digits) <= 19 and _luhn(digits) else match.group(0)


# Each pattern and what takes its place. Keys first, so a key that looks like
# an address or a number is masked as the key it is.
_MASKS: list[tuple[re.Pattern, Any]] = [
    (re.compile(r"\b(?:sk|pk|rk|tvly)-[A-Za-z0-9_-]{16,}"), "[key]"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[key]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*", re.IGNORECASE), "Bearer [key]"),
    (re.compile(r"(?i)\b(api[ _-]?key|secret|password|token)(\s*[:=]\s*)[^\s,;]{6,}"), r"\1\2[key]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    (re.compile(r"\b\d(?:[ -]?\d){12,18}\b"), _card),
    # A number written as a phone number: international (+44 20 7946 0958) or
    # North American ((555) 123-4567, 555-123-4567). Plain figures, prices and
    # dates are not.
    (re.compile(r"(?<![\w+])\+\d{1,3}(?:[ .-]?\(?\d{1,4}\)?){2,5}\d(?!\w)"), "[phone]"),
    (re.compile(r"(?<!\w)\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"), "[phone]"),
]


def mask_text(text: str) -> str:
    for pattern, replacement in _MASKS:
        text = pattern.sub(replacement, text)
    return text


def _masked(value: Any) -> Any:
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {key: _masked(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_masked(item) for item in value]
    return value


def mask(*, data: Any, **_: Any) -> Any:
    """Langfuse's mask: every string in what is sent, masked (mask_text)."""
    return _masked(data)


# ---- Traces ----

class Trace:
    """The trace a request is in: its id and address in Langfuse, its output,
    and scores on it. Without Langfuse every method does nothing."""

    def __init__(self, span: Any = None):
        self._span = span

    @property
    def id(self) -> str | None:
        return getattr(self._span, "trace_id", None)

    def url(self) -> str | None:
        langfuse = client()
        if langfuse is None or not self.id:
            return None
        try:
            return langfuse.get_trace_url(trace_id=self.id)
        except Exception as error:
            log.warning("The trace's address in Langfuse could not be had: %s", error)
            return None

    def output(self, value: Any) -> None:
        if self._span is not None:
            try:
                self._span.update(output=value)
            except Exception as error:
                log.warning("The trace's output could not be set: %s", error)

    def score(self, name: str, value: float | str, *, comment: str | None = None, data_type: str | None = None) -> None:
        if self.id:
            score(name, value, trace_id=self.id, comment=comment, data_type=data_type)


@contextmanager
def trace(name: str, *, session_id: str | None = None, input: Any = None,
          tags: list[str] | None = None, metadata: dict[str, str] | None = None) -> Iterator[Trace]:
    """Open a trace called `name` for the work done inside: every model call,
    in its graph step, grouped under `session_id` and filed under `tags`.
    Yields the Trace; without Langfuse, one that does nothing."""
    langfuse = client()
    if langfuse is None:
        yield Trace()
        return
    try:
        from langfuse import propagate_attributes

        observation = langfuse.start_as_current_observation(as_type="span", name=name, input=input)
        span = observation.__enter__()
        propagation = propagate_attributes(trace_name=name, session_id=session_id, tags=tags or None, metadata=metadata)
        propagation.__enter__()
        token = _handler.set(_new_handler())
    except Exception as error:
        log.warning("The %s trace could not be opened, so it goes untraced: %s", name, error)
        yield Trace()
        return
    raised: BaseException | None = None
    try:
        yield Trace(span)
    except BaseException as error:
        raised = error
        raise
    finally:
        # A stream the browser left is closed from another context, where the
        # context variables cannot be reset; Langfuse's spans still end.
        try:
            _handler.reset(token)
        except ValueError:
            pass
        for manager in (propagation, observation):
            try:
                if raised is None:
                    manager.__exit__(None, None, None)
                else:
                    manager.__exit__(type(raised), raised, raised.__traceback__)
            except Exception as error:
                log.debug("Closing the %s trace: %s", name, error)


def _new_handler():
    from langfuse.langchain import CallbackHandler

    # Told the client by its key: with more than one in the process it would trace nothing.
    return CallbackHandler(public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "").strip())


@contextmanager
def handled() -> Iterator[None]:
    """Trace the LangChain runs made inside into the trace open now, without
    one of their own: an experiment's runner opens the trace (experiments.py)."""
    if client() is None:
        yield
        return
    token = _handler.set(_new_handler())
    try:
        yield
    finally:
        try:
            _handler.reset(token)
        except ValueError:
            pass


def score(name: str, value: float | str, *, trace_id: str | None = None, session_id: str | None = None,
          comment: str | None = None, data_type: str | None = None) -> None:
    """Score a trace, or a session, in Langfuse: a number, a boolean (1 or 0)
    or a category, with a comment. Does nothing without Langfuse."""
    langfuse = client()
    if langfuse is None or not (trace_id or session_id):
        return
    try:
        langfuse.create_score(name=name, value=value, trace_id=trace_id, session_id=None if trace_id else session_id,
                              comment=comment, data_type=data_type)
    except Exception as error:
        log.warning("The %s score could not be sent to Langfuse: %s", name, error)


# ---- Prompts: the code's own, versioned in Langfuse ----

def prompt(name: str):
    """Link the model calls made inside to the prompt called `name`, at the
    version registered for the code's text (register_prompts)."""
    version = _versions.get(name)
    if version is None or client() is None:
        return nullcontext()
    try:
        from langfuse import propagate_attributes

        return propagate_attributes(prompt={"name": name, "version": version})
    except Exception:
        return nullcontext()


def register_prompts() -> dict[str, int]:
    """Register each of the app's prompts in Langfuse (prompt_library.py):
    a new version, labelled production, when the code's text differs from the
    one Langfuse serves; the version for each, which calls are linked to.
    Run once at start-up, in a thread of its own."""
    langfuse = client()
    if langfuse is None:
        return {}
    from prompt_library import prompts

    for name, text in prompts().items():
        try:
            try:
                served = langfuse.get_prompt(name, label="production", cache_ttl_seconds=0, max_retries=0,
                                             fetch_timeout_seconds=10)
            except Exception:  # not there yet
                served = None
            if served is not None and served.prompt == text:
                _versions[name] = served.version
                continue
            created = langfuse.create_prompt(
                name=name, prompt=text, labels=["production"], tags=["cofounder"],
                config={"source": "the app's code"}, commit_message="Registered from the app's code",
            )
            _versions[name] = created.version
        except Exception as error:
            log.warning("The %s prompt could not be registered in Langfuse: %s", name, error)
    log.info("Registered %d prompts in Langfuse.", len(_versions))
    return dict(_versions)


def versions() -> dict[str, int]:
    return dict(_versions)

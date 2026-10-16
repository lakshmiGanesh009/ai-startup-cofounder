"""Per-node run metrics: how many LLM calls a node made, how long it took, and
how many tokens it used.

A node wraps its work in `track(name)` and calls `record(reply)` after each LLM
response. The context manager returns a dict ready to merge into the state's
`metrics` field.
"""

import time
from contextlib import contextmanager

from state import NodeMetric


class _Tracker:
    def __init__(self):
        self.calls = 0
        self.tokens = 0

    def record(self, reply) -> None:
        """Count one LLM call, adding its tokens when the reply reports them."""
        self.calls += 1
        usage = getattr(reply, "usage_metadata", None)
        if usage:
            self.tokens += usage.get("total_tokens", 0)


@contextmanager
def track(name: str, into: dict):
    """Time a node's work and write its metric into `into` under `name`."""
    tracker = _Tracker()
    start = time.perf_counter()
    try:
        yield tracker
    finally:
        into[name] = NodeMetric(
            calls=tracker.calls,
            seconds=round(time.perf_counter() - start, 3),
            tokens=tracker.tokens,
        )

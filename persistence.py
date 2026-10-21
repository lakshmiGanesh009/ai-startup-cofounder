"""Where the API keeps what must outlive it: in PostgreSQL when DATABASE_URL is
set, else in this process's memory, lost when it stops.

- Sessions: LangGraph's AsyncPostgresSaver, on a pool of async connections, so
  a follow-up after a restart starts from the session's state.
- Reports: one row a session, its latest results and its report as JSON. Each
  change locks the row in a transaction, so a change made from an older
  version is refused even with several API workers.
- The Monitor's history: its evaluations and events, written by a thread of
  its own behind the Monitor, so neither a request nor a log line waits on the
  database; the latest are read back when the API starts.

The API opens its storage as it starts and closes it as it stops (main.py's
lifespan). It does not start without the database it was given.
"""

import asyncio
import logging
import queue
import threading
from collections.abc import Callable
from typing import Literal

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.base import SerializerProtocol
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool, ConnectionPool, PoolTimeout

from monitor import Event, Run
from reports import (
    KEEP_VERSIONS,
    MemoryReports,
    Report,
    ReportSummary,
    SessionResults,
    Stored,
)

logger = logging.getLogger(__name__)

# Seconds to wait for the database when the API starts, and for a health check.
OPEN_TIMEOUT = 10.0
PING_TIMEOUT = 2.0
# Taken while the tables are brought up to date, so two workers starting at
# once do not both migrate.
MIGRATION_LOCK = 7_402_311

# This app's tables, one list of statements a version; LangGraph's checkpointer
# keeps its own. A version once released is never edited: add another.
MIGRATIONS: list[list[str]] = [
    [
        """CREATE TABLE reports (
            session_id text PRIMARY KEY,
            results jsonb NOT NULL,
            report jsonb NOT NULL,
            updated_at timestamptz NOT NULL
        )""",
        "CREATE INDEX reports_by_update ON reports (updated_at DESC)",
        "CREATE TABLE monitor_runs (id bigserial PRIMARY KEY, at timestamptz NOT NULL, run jsonb NOT NULL)",
        "CREATE TABLE monitor_events (id bigserial PRIMARY KEY, at timestamptz NOT NULL, event jsonb NOT NULL)",
    ],
    [
        # Each report's earlier versions, to look at or restore (reports.KEEP_VERSIONS).
        """CREATE TABLE report_versions (
            session_id text NOT NULL,
            version integer NOT NULL,
            report jsonb NOT NULL,
            PRIMARY KEY (session_id, version)
        )""",
    ],
]


class StorageUnavailable(RuntimeError):
    """The database could not be reached when the API started."""


def where(url: str) -> str:
    """The database a URL names, without its user or password, for the logs."""
    parts = conninfo_to_dict(url)
    return f"{parts.get('host', 'localhost')}:{parts.get('port', 5432)}/{parts.get('dbname', '')}"


def _stored(row: dict) -> Stored:
    return Stored(SessionResults.model_validate(row["results"]), Report.model_validate(row["report"]))


class PostgresReports:
    """The reports in PostgreSQL, one row a session."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def get(self, session_id: str) -> Stored | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT results, report FROM reports WHERE session_id = %s", (session_id,)).fetchone()
        return _stored(row) if row else None

    def update(self, session_id: str, change: Callable[[Stored | None], Stored]) -> Stored:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "SELECT results, report FROM reports WHERE session_id = %s FOR UPDATE", (session_id,)
            ).fetchone()
            before = _stored(row) if row else None
            stored = change(before)
            if before and before.report.version != stored.report.version:
                self._keep(conn, session_id, before.report)
            conn.execute(
                """INSERT INTO reports (session_id, results, report, updated_at) VALUES (%s, %s, %s, %s)
                   ON CONFLICT (session_id) DO UPDATE
                   SET results = EXCLUDED.results, report = EXCLUDED.report, updated_at = EXCLUDED.updated_at""",
                (
                    session_id,
                    Jsonb(stored.results.model_dump(mode="json")),
                    # The investment figures and checks are calculated, so not kept.
                    Jsonb(stored.report.model_dump(mode="json", exclude={"investment", "checks"})),
                    stored.report.updated_at,
                ),
            )
        return stored

    @staticmethod
    def _keep(conn, session_id: str, report: Report) -> None:
        """Keep a version that is being replaced, and only the latest few."""
        conn.execute(
            """INSERT INTO report_versions (session_id, version, report) VALUES (%s, %s, %s)
               ON CONFLICT (session_id, version) DO NOTHING""",
            (session_id, report.version, Jsonb(report.model_dump(mode="json", exclude={"investment", "checks"}))),
        )
        conn.execute(
            """DELETE FROM report_versions WHERE session_id = %s AND version NOT IN (
                   SELECT version FROM report_versions WHERE session_id = %s ORDER BY version DESC LIMIT %s)""",
            (session_id, session_id, KEEP_VERSIONS),
        )

    def history(self, session_id: str) -> list[Report]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT report FROM report_versions WHERE session_id = %s ORDER BY version DESC", (session_id,)
            ).fetchall()
        return [Report.model_validate(row["report"]) for row in rows]

    def summaries(self) -> list[ReportSummary]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT report - 'objective' - 'context' - 'sections' - 'proposal' AS summary,
                          jsonb_typeof(report -> 'proposal') = 'object' AS has_proposal
                   FROM reports ORDER BY updated_at DESC"""
            ).fetchall()
        return [ReportSummary(**row["summary"], has_proposal=bool(row["has_proposal"])) for row in rows]


class MonitorArchive:
    """The Monitor's evaluations and events in PostgreSQL. A thread of its own
    writes them in batches; while the database is down they are dropped, said
    once, and the Monitor goes on in memory. The latest KEEP_RUNS and
    KEEP_EVENTS are kept."""

    KEEP_RUNS = 1_000
    KEEP_EVENTS = 10_000
    TRIM_EVERY = 500  # rows written between trims
    BATCH = 200

    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        self._failing = False
        self._since_trim = 0

    def add_run(self, run: Run) -> None:
        self._queue.put(("run", run.at, run.model_dump(mode="json")))

    def add_event(self, event: Event) -> None:
        self._queue.put(("event", event.at, event.model_dump(mode="json")))

    def start(self) -> None:
        self._thread = threading.Thread(target=self._work, name="monitor-archive", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Write what is waiting, then stop."""
        if self._thread:
            self._queue.put(None)
            self._thread.join(timeout)
            self._thread = None

    def load(self, runs: int, events: int) -> tuple[list[Run], list[Event]]:
        """The latest evaluations and events, oldest first."""
        with self.pool.connection() as conn:
            run_rows = conn.execute("SELECT run FROM monitor_runs ORDER BY id DESC LIMIT %s", (runs,)).fetchall()
            event_rows = conn.execute("SELECT event FROM monitor_events ORDER BY id DESC LIMIT %s", (events,)).fetchall()
        return (
            [Run.model_validate(row["run"]) for row in reversed(run_rows)],
            [Event.model_validate(row["event"]) for row in reversed(event_rows)],
        )

    def _work(self) -> None:
        while True:
            batch = [self._queue.get()]
            while batch[-1] is not None and len(batch) < self.BATCH:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            items = [item for item in batch if item is not None]
            if items:
                self._write(items)
            if batch[-1] is None:
                return

    def _write(self, items: list[tuple]) -> None:
        runs = [(at, Jsonb(data)) for kind, at, data in items if kind == "run"]
        events = [(at, Jsonb(data)) for kind, at, data in items if kind == "event"]
        try:
            with self.pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
                if runs:
                    cur.executemany("INSERT INTO monitor_runs (at, run) VALUES (%s, %s)", runs)
                if events:
                    cur.executemany("INSERT INTO monitor_events (at, event) VALUES (%s, %s)", events)
                self._since_trim += len(items)
                if self._since_trim >= self.TRIM_EVERY:
                    self._since_trim = 0
                    for table, keep in (("monitor_runs", self.KEEP_RUNS), ("monitor_events", self.KEEP_EVENTS)):
                        cur.execute(
                            f"DELETE FROM {table} WHERE id <= (SELECT id FROM {table} ORDER BY id DESC OFFSET %s LIMIT 1)",
                            (keep,),
                        )
        except Exception as error:  # the database is unreachable or refused the write
            if not self._failing:
                self._failing = True
                logger.warning("The Monitor's history could not be saved (%s); it goes on in memory.", error)
            return
        if self._failing:
            self._failing = False
            logger.info("The Monitor's history is being saved again.")


class MemoryStorage:
    """Everything in this process's memory: nothing to open, all lost on a restart."""

    kind: Literal["memory", "postgres"] = "memory"
    where = "memory"

    def __init__(self):
        self.checkpointer = None  # the graph's own MemorySaver
        self.reports = MemoryReports()
        self.archive: MonitorArchive | None = None

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def ping(self) -> bool:
        return True


class PostgresStorage:
    """Sessions, reports and the Monitor's history in PostgreSQL."""

    kind: Literal["memory", "postgres"] = "postgres"

    def __init__(self, url: str, serde: SerializerProtocol):
        self.url = url
        self.serde = serde
        self.where = where(url)
        # The reports and the history are used from worker threads, on a pool
        # of their own; LangGraph's saver and its async pool belong to the event
        # loop that opens them, so open() makes them.
        self.pool = ConnectionPool(
            url, open=False, min_size=1, max_size=5, name="reports",
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
        self.reports = PostgresReports(self.pool)
        self.archive: MonitorArchive | None = MonitorArchive(self.pool)
        self.async_pool: AsyncConnectionPool | None = None
        self.checkpointer: AsyncPostgresSaver | None = None

    async def open(self) -> None:
        """Connect, bring the tables up to date and start the history's writer.
        Raises StorageUnavailable when the database cannot be reached."""
        self.async_pool = AsyncConnectionPool(
            self.url, open=False, min_size=1, max_size=10, name="checkpoints",
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        try:
            await self.async_pool.open(wait=True, timeout=OPEN_TIMEOUT)
            await asyncio.to_thread(self.pool.open, True, OPEN_TIMEOUT)
        except PoolTimeout as error:
            await self.async_pool.close()
            await asyncio.to_thread(self.pool.close)
            raise StorageUnavailable(
                f"Could not reach PostgreSQL at {self.where} within {OPEN_TIMEOUT:.0f} s. "
                "Check DATABASE_URL and that the database is running."
            ) from error
        self.checkpointer = AsyncPostgresSaver(self.async_pool, serde=self.serde)
        await self.checkpointer.setup()
        await asyncio.to_thread(self.migrate)
        self.archive.start()

    def migrate(self) -> None:
        """Apply the migrations not yet applied, in order, one worker at a time."""
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cofounder_migrations"
                " (version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            done = conn.execute("SELECT coalesce(max(version), -1) AS version FROM cofounder_migrations").fetchone()
            for version, statements in enumerate(MIGRATIONS):
                if version <= done["version"]:
                    continue
                for statement in statements:
                    conn.execute(statement)
                conn.execute("INSERT INTO cofounder_migrations (version) VALUES (%s)", (version,))
                logger.info("Applied database migration %d.", version)

    async def close(self) -> None:
        """Write the history still waiting, then close the connections."""
        await asyncio.to_thread(self.archive.stop)
        await asyncio.to_thread(self.pool.close)
        if self.async_pool:
            await self.async_pool.close()

    def ping(self) -> bool:
        try:
            with self.pool.connection(timeout=PING_TIMEOUT) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False


def open_storage(url: str, serde: SerializerProtocol) -> MemoryStorage | PostgresStorage:
    """The storage DATABASE_URL names, not yet opened."""
    return PostgresStorage(url, serde) if url else MemoryStorage()

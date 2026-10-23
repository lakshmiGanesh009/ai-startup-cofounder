"""Tests for keeping sessions, reports and the Monitor's history in PostgreSQL,
so they survive a restart. They need a database they may empty, named by
TEST_DATABASE_URL (for example postgresql://localhost:5432/cofounder_test), and
are skipped without one.

Each `lifetime` opens the storage, works and closes it on one event loop, as
the API does between starting and stopping; two in a row are a restart."""

import asyncio
import logging
import os
from datetime import datetime, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

import persistence
from graph import SERDE, build_graph
from monitor import Event, Monitor, Run, monitor
from persistence import PostgresStorage, StorageUnavailable
from reports import ReportChanged, ReportSection, ReportStore, SessionResults, store
from state import DelegationPlan, Task

URL = os.getenv("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Set TEST_DATABASE_URL to a PostgreSQL database the tests may empty.")


@pytest.fixture(autouse=True)
def empty_database():
    """Each test starts from an empty database."""
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")


def lifetime(work):
    """Run `work(storage)` between opening and closing the storage, like an API
    between starting and stopping; returns what it returns."""

    async def run():
        storage = PostgresStorage(URL, SERDE)
        await storage.open()
        try:
            return await work(storage)
        finally:
            await storage.close()

    return asyncio.run(run())


def _results(venture: str = "Clinic scheduling") -> SessionResults:
    return SessionResults(
        venture=venture, objective="Decide whether to launch.", context="", final_strategy="Go.",
        analyses={"marketing": "Sell to clinics."}, resolutions=[],
    )


def test_the_tables_are_made_once_and_the_url_never_reaches_the_logs():
    async def migrate_again(storage):
        await asyncio.to_thread(storage.migrate)  # nothing left to do

    lifetime(migrate_again)

    with psycopg.connect(URL) as conn:
        assert conn.execute("SELECT version FROM cofounder_migrations ORDER BY version").fetchall() == [
            (0,), (1,), (2,)]
        tables = {row[0] for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert {"reports", "report_versions", "uploads", "monitor_runs", "monitor_events", "checkpoints"} <= tables
    assert persistence.where("postgresql://me:secret@db.example:6543/cofounder") == "db.example:6543/cofounder"


def test_a_session_and_its_follow_up_survive_a_restart(fake_llm):
    config = {"configurable": {"thread_id": "session-1"}}

    async def evaluate(storage):
        return await build_graph(storage.checkpointer).ainvoke({"request": "An idea.", "deep": False}, config)

    async def follow_up(storage):
        graph = build_graph(storage.checkpointer)
        kept = (await graph.aget_state(config)).values
        return kept, await graph.ainvoke({"request": "Refine the pricing.", "deep": False}, config)

    first = lifetime(evaluate)
    kept, after = lifetime(follow_up)

    assert kept["final_strategy"] == first["final_strategy"]
    assert kept["plan"].objective == first["plan"].objective  # read back as the model it was
    assert after["request"] == "Refine the pricing." and after["final_strategy"]


def test_reports_survive_a_restart_and_a_stale_edit_is_still_refused():
    async def write(storage):
        store = ReportStore(storage.reports)
        store.record("s1", _results())
        store.record("s2", _results("Pricing review"))
        return store.save("s1", 1, [ReportSection(key="strategy", title="Strategy", body="Edited.")])

    async def read(storage):
        store = ReportStore(storage.reports)
        kept = store.get("s1")
        with pytest.raises(ReportChanged, match="at version 2, not 1"):
            store.save("s1", 1, [])
        store.record("s1", _results())  # newer results do not overwrite the edits
        outdated = store.get("s1").outdated
        summaries = [(each.session_id, each.has_proposal) for each in store.summaries()]
        return kept, outdated, summaries, store.reset("s1").version

    edited = lifetime(write)
    kept, outdated, summaries, reset = lifetime(read)

    assert (kept.version, kept.edited, kept.sections[0].body) == (2, True, "Edited.")
    assert kept.updated_at == edited.updated_at
    assert outdated
    assert summaries == [("s1", False), ("s2", False)]
    assert reset == 3


def test_a_reports_earlier_versions_survive_a_restart_and_only_the_latest_are_kept(monkeypatch):
    monkeypatch.setattr(persistence, "KEEP_VERSIONS", 3)

    async def write(storage):
        store = ReportStore(storage.reports)
        store.record("s1", _results())
        for number in range(5):
            store.save("s1", store.get("s1").version, [ReportSection(key="strategy", title="Strategy", body=f"Edit {number}.")])

    async def read(storage):
        store = ReportStore(storage.reports)
        versions = [(v.version, v.change, v.current) for v in store.versions("s1")]
        restored = store.restore("s1", 6, 4)
        return versions, store.version("s1", 4).sections[0].body, restored

    lifetime(write)
    versions, fourth, restored = lifetime(read)

    assert versions == [(6, "Edited the team's report", True), (5, "Edited the team's report", False),
                        (4, "Edited the team's report", False), (3, "Edited the team's report", False)]
    assert fourth == "Edit 2."
    assert (restored.version, restored.change, restored.sections[0].body) == (7, "Restored version 4", "Edit 2.")


def test_uploads_survive_a_restart_and_only_the_newest_are_kept(monkeypatch):
    from extract import Extracted, Passage
    from library import UploadStore

    monkeypatch.setattr(persistence, "KEEP_UPLOADS", 2)
    document = Extracted(kind="PDF", parts="2 pages", passages=[Passage(where="page 2", text="Churn is 4% a month.")])

    async def add(storage):
        kept = UploadStore(storage.uploads)
        return [await asyncio.to_thread(kept.add, f"plan-{n}.pdf", 100, document) for n in range(3)]

    added = lifetime(add)

    async def read(storage):
        return [storage.uploads.get(upload.id) for upload in added]

    first, second, third = lifetime(read)
    assert first is None  # the oldest was let go
    assert (second.name, third.document.passages[0].where) == ("plan-1.pdf", "page 2")


def test_the_monitors_history_is_kept_trimmed_and_read_back(monkeypatch):
    monkeypatch.setattr(persistence.MonitorArchive, "KEEP_EVENTS", 3)
    monkeypatch.setattr(persistence.MonitorArchive, "TRIM_EVERY", 1)

    async def record(storage):
        watch = Monitor()
        watch.attach(storage.archive)
        for number in range(5):
            watch.event("done", "plan", f"Event {number}.")
        watch.run(Run(session="s1", at=datetime.now(timezone.utc), seconds=80.0, ok=True))
        # Closing writes what is waiting.

    async def load(storage):
        return storage.archive.load(50, 300)

    lifetime(record)
    runs, events = lifetime(load)

    assert [run.session for run in runs] == ["s1"]
    assert [event.message for event in events] == ["Event 2.", "Event 3.", "Event 4."]
    later = Monitor()
    later.preload(runs, events)
    seen = later.snapshot()
    assert [event.message for event in seen.events][:1] == ["Event 4."]
    # The statistics count from the start of this API, not the history's.
    assert (seen.totals.evaluations, seen.evaluation_seconds, seen.runs[0].session) == (0, None, "s1")


def test_a_database_that_cannot_be_reached_stops_the_api_starting(monkeypatch):
    monkeypatch.setattr(persistence, "OPEN_TIMEOUT", 1.0)
    storage = PostgresStorage("postgresql://localhost:1/nothing?connect_timeout=1", SERDE)

    with pytest.raises(StorageUnavailable, match="Could not reach PostgreSQL at localhost:1/nothing"):
        asyncio.run(storage.open())
    assert storage.ping() is False


def test_when_the_database_goes_down_the_monitor_goes_on(caplog):
    async def nothing(storage):
        return storage.archive

    archive = lifetime(nothing)  # closed: its connections are gone
    event = Event(at=datetime.now(timezone.utc), kind="done", source="plan", message="Done.")

    with caplog.at_level(logging.INFO, logger="persistence"):
        caplog.clear()
        archive._write([("event", event.at, event.model_dump(mode="json"))])
        archive._write([("event", event.at, event.model_dump(mode="json"))])

    said = [record.getMessage() for record in caplog.records if record.name == "persistence"]
    assert len(said) == 1 and said[0].startswith("The Monitor's history could not be saved")


def test_the_history_is_saved_again_once_the_database_answers(caplog):
    event = Event(at=datetime.now(timezone.utc), kind="done", source="plan", message="Done.")

    async def write_after_a_failure(storage):
        storage.archive._failing = True
        with caplog.at_level(logging.INFO, logger="persistence"):
            caplog.clear()
            storage.archive._write([("event", event.at, event.model_dump(mode="json"))])
        return [record.getMessage() for record in caplog.records if record.name == "persistence"]

    assert lifetime(write_after_a_failure) == ["The Monitor's history is being saved again."]


@pytest.fixture
def api(monkeypatch):
    """Starts of the API as it runs with DATABASE_URL set, on the test database:
    each `with api() as client:` is one, from starting to stopping."""
    import main

    backend = store.backend
    monkeypatch.setattr(main, "graph", main.graph)  # the lifespan rebuilds it; put it back after

    def start() -> TestClient:
        storage = PostgresStorage(URL, SERDE)
        monkeypatch.setattr(main, "storage", storage)
        store.use(storage.reports)
        monitor.reset()  # the API's memory starts empty
        monitor.attach(storage.archive)
        return TestClient(main.app)

    yield start
    store.use(backend)
    monitor.attach(None)


EVERYONE = DelegationPlan(
    objective="Evaluate the venture.",
    tasks=[Task(specialist=name, task=f"Handle {name}.") for name in ("marketing", "finance", "technical", "risk")],
)
PRICING = DelegationPlan(objective="Refine the pricing.", tasks=[Task(specialist="finance", task="Refine the pricing.")])


def test_through_the_api_a_restart_loses_nothing(fake_llm, api):
    fake_llm.plan = EVERYONE
    with api() as client:
        health = client.get("/health").json()
        session = client.post("/evaluate", json={"prompt": "Evaluate an AI tool."}).json()["session_id"]
        edit = {"version": 1, "sections": [{"key": "strategy", "title": "Strategy", "body": "Edited."}]}
        assert client.put(f"/reports/{session}", json=edit).status_code == 200

    fake_llm.plan = PRICING
    with api() as client:
        report = client.get(f"/reports/{session}").json()
        follow_up = client.post("/evaluate", json={"prompt": "Refine the pricing.", "session_id": session}).json()
        seen = client.get("/monitoring").json()

    assert health["status"] == "healthy" and health["storage"] == {"kind": "postgres", "ok": True}
    assert (report["version"], report["edited"], report["sections"][0]["body"]) == (2, True, "Edited.")
    # The follow-up found its session: only finance ran again, on the first request, and
    # the other reports carried over; a new session would have had finance's alone.
    assert set(follow_up["analyses"]) == {"marketing", "finance", "technical", "risk"}
    assert "Startup request:\nEvaluate an AI tool." in follow_up["analyses"]["finance"]
    # The history runs across the restart; the statistics count from the second start.
    assert seen["kept_in"] == "postgres"
    assert [run["session"] for run in seen["runs"]] == [session[:8], session[:8]]
    assert seen["totals"]["evaluations"] == 1
    starts = [event["message"] for event in seen["events"] if event["kind"] == "system"]
    assert starts == ["The API started, keeping sessions and reports in localhost:5432/cofounder_test; "
                      "open to anyone who can reach it (no API_KEY)."] * 2


def test_through_the_api_a_deleted_report_leaves_nothing_behind(fake_llm, api):
    fake_llm.plan = EVERYONE
    with api() as client:
        session = client.post("/evaluate", json={"prompt": "Evaluate an AI tool."}).json()["session_id"]
        edit = {"version": 1, "sections": [{"key": "strategy", "title": "Strategy", "body": "Edited."}]}
        assert client.put(f"/reports/{session}", json=edit).status_code == 200
        assert client.delete(f"/reports/{session}").status_code == 204

    with api() as client:
        assert client.get(f"/reports/{session}").status_code == 404
        assert client.get("/reports").json() == []
    with psycopg.connect(URL) as conn:
        left = conn.execute(
            """SELECT (SELECT count(*) FROM reports), (SELECT count(*) FROM report_versions),
                      (SELECT count(*) FROM checkpoints WHERE thread_id = %s)""",
            (session,),
        ).fetchone()
    assert left == (0, 0, 0)

"""Tests for the tracing in Langfuse (tracing.py, prompt_library.py): a made-up
Langfuse answers the SDK's HTTP calls, and an in-memory exporter keeps the
spans, so nothing leaves the machine."""

import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import prompt_library
import tracing
from main import app

client = TestClient(app)


def _valid_payload(**extra) -> dict:
    return {"prompt": "Evaluate an AI scheduling tool for clinics.", **extra}


@pytest.fixture
def langfuse(monkeypatch):
    """Langfuse set up, on a made-up server that keeps prompts and records every
    call; the spans go to an in-memory exporter."""
    calls: list = []
    stored: dict[str, list[dict]] = {}

    def api(request: httpx.Request):
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, path, body))
        if path == "/api/public/projects":
            return httpx.Response(200, json={"data": [{"id": "project-1", "name": "Co-Founder", "organization": {"id": "o", "name": "o"}, "metadata": {}}]})
        if path.startswith("/api/public/v2/prompts/") and request.method == "GET":
            versions = stored.get(path.removeprefix("/api/public/v2/prompts/"))
            return httpx.Response(200, json=versions[-1]) if versions else httpx.Response(404, json={"message": "Prompt not found"})
        if path == "/api/public/v2/prompts" and request.method == "POST":
            versions = stored.setdefault(body["name"], [])
            versions.append({**body, "version": len(versions) + 1, "type": "text", "tags": body.get("tags") or [],
                             "labels": body.get("labels") or [], "config": body.get("config") or {}})
            return httpx.Response(200, json=versions[-1])
        return httpx.Response(200, json={})

    exporter = InMemorySpanExporter()
    # A key of its own, so the SDK's per-key state from another test is not reused.
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", f"pk-lf-test-{uuid.uuid4().hex[:8]}")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.test")
    monkeypatch.setattr(tracing, "_options", {"span_exporter": exporter, "httpx_client": httpx.Client(transport=httpx.MockTransport(api))})
    tracing.reset()
    yield SimpleNamespace(exporter=exporter, calls=calls, stored=stored)
    tracing.reset()


def _spans(langfuse) -> dict:
    tracing.flush()
    return {span.name: span for span in langfuse.exporter.get_finished_spans()}


def _scores(langfuse) -> dict:
    tracing.flush()
    sent = [score for method, path, body in langfuse.calls if path == "/api/public/scores" for score in body]
    return {score["name"]: score for score in sent}


def test_without_its_keys_nothing_is_traced_and_nothing_leaves(fake_llm):
    assert not tracing.enabled() and tracing.client() is None
    with tracing.trace("evaluate", session_id="s") as run:
        assert run.id is None and run.url() is None
        run.score("verdict", "go")  # does nothing
    body = client.post("/evaluate", json=_valid_payload()).json()
    assert body["trace_id"] is None and body["trace_url"] is None
    assert client.get("/health").json()["tracing"] == {"langfuse": False, "prompts": 0}
    assert client.post("/feedback", json={"session_id": body["session_id"], "useful": True}).json() == {"recorded": False}


def test_langchain_runs_inside_a_trace_are_traced_without_being_passed_a_handler(langfuse):
    double = RunnableLambda(lambda value: value * 2, name="double")
    with tracing.trace("work", session_id="session-1", tags=["test"]) as run:
        assert double.invoke(21) == 42
    assert double.invoke(1) == 2  # outside a trace: not traced
    spans = _spans(langfuse)
    assert spans["work"].attributes["session.id"] == "session-1"
    assert spans["work"].attributes["langfuse.trace.tags"] == ("test",)
    assert spans["double"].context.trace_id == spans["work"].context.trace_id
    assert format(spans["work"].context.trace_id, "032x") == run.id
    assert sum(1 for span in langfuse.exporter.get_finished_spans() if span.name == "double") == 1


def test_an_evaluation_is_one_trace_in_its_session_with_the_graphs_steps_and_the_teams_scores(langfuse, fake_llm):
    answer = client.post("/evaluate", json=_valid_payload(reasoning={"specialist": "low", "chief": "medium"}))
    assert answer.status_code == 200
    body = answer.json()
    assert len(body["trace_id"]) == 32
    assert body["trace_url"] == f"https://langfuse.test/project/project-1/traces/{body['trace_id']}"

    spans = _spans(langfuse)
    root = spans["evaluate"]
    assert root.attributes["session.id"] == body["session_id"]
    assert root.attributes["langfuse.trace.name"] == "evaluate"
    assert set(root.attributes["langfuse.trace.tags"]) == {"evaluate", "first-request"}
    assert root.attributes["langfuse.trace.metadata.reasoning_specialist"] == '"low"'
    # The graph's steps, inside the evaluation's trace.
    for step in ("plan", "review", "synthesis"):
        assert spans[step].context.trace_id == root.context.trace_id, step

    scores = _scores(langfuse)
    assert {"review-average", "approved-first-time", "revisions", "conflicts", "verdict",
            "failed-specialists", "guardrail-flags"} <= set(scores)
    assert all(score["traceId"] == body["trace_id"] for score in scores.values())
    assert scores["verdict"]["dataType"] == "CATEGORICAL"
    assert any(name.startswith("review-") and name != "review-average" for name in scores)


def test_the_prompts_are_registered_once_and_again_only_when_the_code_changes(langfuse, monkeypatch):
    library = prompt_library.prompts()
    versions = tracing.register_prompts()
    assert set(versions) == set(library) and set(versions.values()) == {1}
    created = [body for method, path, body in langfuse.calls if method == "POST" and path == "/api/public/v2/prompts"]
    assert len(created) == len(library)
    assert created[0]["labels"] == ["production"] and created[0]["config"] == {"source": "the app's code"}
    assert "{{currency_rule}}" in langfuse.stored["proposal/market"][-1]["prompt"]

    # Unchanged: nothing new. One prompt changed in the code: a new version of it alone.
    tracing._versions.clear()
    assert tracing.register_prompts() == versions
    changed = {**library, "chief/plan": library["chief/plan"] + " Be brief."}
    monkeypatch.setattr(prompt_library, "prompts", lambda: changed)
    tracing._versions.clear()
    assert tracing.register_prompts()["chief/plan"] == 2
    created = [body for method, path, body in langfuse.calls if method == "POST" and path == "/api/public/v2/prompts"]
    assert len(created) == len(library) + 1


def test_a_call_is_linked_to_the_version_of_its_prompt(langfuse):
    tracing.register_prompts()
    with tracing.trace("work"):
        with tracing.prompt("chief/plan"):
            tracing.client().start_observation(as_type="generation", name="call").end()
        with tracing.prompt("not/a-prompt"):  # not registered: not linked
            tracing.client().start_observation(as_type="generation", name="other").end()
    spans = _spans(langfuse)
    linked = {key: value for key, value in spans["call"].attributes.items() if "prompt" in key}
    assert "chief/plan" in linked.values() and 1 in linked.values()
    assert not any("prompt" in key for key in spans["other"].attributes)


def test_what_leaves_is_masked():
    text = ("Write to ana@clinic.org or +44 20 7946 0958, (555) 123-4567; card 4242 4242 4242 4242; "
            "key sk-proj-abcdefghijklmnop1234 and tvly-dev-0123456789abcdef; api_key=hunter2secret; "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz. Revenue $1,200,000 in 2026-10-21, 300 units, "
            "account 1234567890123 (not a card).")
    masked = tracing.mask_text(text)
    for secret in ("ana@clinic.org", "7946 0958", "123-4567", "4242 4242", "sk-proj-", "tvly-dev", "hunter2", "abcdefghijklmnopqrstuvwxyz"):
        assert secret not in masked, secret
    for kept in ("$1,200,000", "2026-10-21", "300 units", "1234567890123"):
        assert kept in masked, kept
    assert tracing.mask(data={"messages": [{"content": "mail ana@clinic.org"}], "n": 3}) == {
        "messages": [{"content": "mail [email]"}], "n": 3,
    }


def test_traced_text_is_masked_before_it_is_sent(langfuse):
    with tracing.trace("work", input={"brief": "Call me on (555) 123-4567"}):
        pass
    assert _spans(langfuse)["work"].attributes["langfuse.observation.input"] == '{"brief": "Call me on [phone]"}'


def test_the_founders_feedback_is_a_score_on_the_run(langfuse, fake_llm):
    body = client.post("/evaluate", json=_valid_payload()).json()
    answer = client.post("/feedback", json={"session_id": body["session_id"], "trace_id": body["trace_id"],
                                            "useful": False, "comment": "Too vague; mail me at ana@clinic.org"})
    assert answer.status_code == 202 and answer.json() == {"recorded": True}
    score = _scores(langfuse)["founder-feedback"]
    assert score["value"] == 0 and score["dataType"] == "BOOLEAN" and score["traceId"] == body["trace_id"]
    assert score["comment"] == "Too vague; mail me at [email]"
    assert client.post("/feedback", json={"session_id": body["session_id"], "trace_id": "nope", "useful": True}).status_code == 422


def test_a_fault_in_langfuse_never_fails_a_request(monkeypatch, fake_llm):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-broken")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-broken")

    class Broken:
        def __init__(self, **kwargs):
            raise RuntimeError("no such region")

    monkeypatch.setattr("langfuse.Langfuse", Broken)
    answer = client.post("/evaluate", json=_valid_payload())
    assert answer.status_code == 200 and answer.json()["trace_id"] is None


# ---- The experiments (experiments.py) and the judge (judge.py) ----

def test_an_experiments_task_runs_the_team_on_a_scenario_and_the_scores_read_its_run(fake_llm):
    import experiments

    item = SimpleNamespace(input={"prompt": "Evaluate an AI scheduling tool for clinics.",
                                  "context": {"constraints": "Solo founder, $15k"}})
    output = experiments.run_team(item, {"specialist": "low"})
    assert output["brief"] == item.input["prompt"] and output["strategy"]
    assert set(output["reviews"]) == {"marketing", "finance", "technical", "risk"}
    assert output["failed"] == 0 and output["conflicts"] == 0

    scores = {evaluation.name: evaluation for evaluation in experiments.team_scores(output=output)}
    assert scores["review-average"].value == 5 and scores["approved-first-time"].value == 1
    assert scores["within-word-limit"].data_type == "BOOLEAN"

    judged = {evaluation.name: evaluation.value for evaluation in experiments.judge_scores(output=output)}
    # The judge's 7 is kept within 1 to 5.
    assert judged == {"judge-constraints": 4, "judge-consistency": 5, "judge-actionability": 3, "judge-grounding": 5}
    assert fake_llm.calls[-1] == ("chief", "Judgement")

    runs = [SimpleNamespace(evaluations=[*experiments.team_scores(output=output), *experiments.judge_scores(output=output)])] * 2
    means = {evaluation.name: evaluation.value for evaluation in experiments.averages(item_results=runs)}
    assert means["mean-review-average"] == 5 and means["mean-judge-grounding"] == 5


def test_the_judge_reads_a_live_run_after_its_answer_only_when_asked(langfuse, fake_llm, monkeypatch):
    import judge

    body = client.post("/evaluate", json=_valid_payload()).json()
    assert not any(name.startswith("judge-") for name in _scores(langfuse))

    monkeypatch.setenv("LANGFUSE_JUDGE", "true")
    started = []
    monkeypatch.setattr(judge, "judge_later", lambda *args: started.append(args))
    body = client.post("/evaluate", json=_valid_payload()).json()
    trace_id, session_id, brief, strategy = started[0]
    assert (trace_id, session_id, brief) == (body["trace_id"], body["session_id"], _valid_payload()["prompt"])
    assert strategy == body["final_strategy"]


def test_the_live_judges_scores_go_on_the_runs_trace(langfuse, fake_llm, monkeypatch):
    import judge

    class AtOnce:  # the thread's work, done now
        def __init__(self, target, **_):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(judge, "threading", SimpleNamespace(Thread=AtOnce))  # the judge's own, not the module
    judge.judge_later("a" * 32, "session-1", "Evaluate a tool.", "Go: launch in May.")
    scores = _scores(langfuse)
    assert scores["judge-actionability"]["value"] == 3 and scores["judge-grounding"]["traceId"] == "a" * 32
    assert scores["judge-constraints"]["comment"] == "The next steps name no owners."
    assert _spans(langfuse)["judge"].attributes["session.id"] == "session-1"


def test_an_experiments_task_runs_the_team_off_the_runners_event_loop(fake_llm, monkeypatch):
    """Langfuse's runner calls a task on its event loop; the look-ups' MCP clients
    need one of their own, so the team must run in a thread (the live check's
    first experiment lost every FRED look-up to this)."""
    import asyncio

    import experiments
    from tests.mcp_fakes import use_fred

    calls = use_fred(monkeypatch)
    item = SimpleNamespace(input={"prompt": "Evaluate an AI scheduling tool for clinics."})

    async def runner():  # as experiment.py's _run_task: call the task, await what it returns
        return await experiments.task_for({})(item=item)

    output = asyncio.run(runner())
    assert output["strategy"] and calls, "the look-ups reached FRED"

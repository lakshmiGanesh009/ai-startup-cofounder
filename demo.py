"""Walk through one scenario end to end, printing each stage.

Usage:
    uv run python demo.py scenarios/healthcare_scheduling.json

Needs a filled-in .env, since it calls a real model.
"""

import json
import sys
import uuid
from pathlib import Path

import tracing
from graph import build_graph
from state import RequestContext


def _print_stage(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _print_result(result: dict) -> None:
    _print_stage("PLAN")
    print(f"Objective: {result['plan'].objective}")
    for name, task in result["assignments"].items():
        print(f"  - {name}: {task}")

    _print_stage("SPECIALIST REPORTS")
    for name, report in result["analyses"].items():
        print(f"\n## {name}\n{report}")

    _print_stage("REVIEW HISTORY")
    for round_no, reviews in enumerate(result.get("review_history", []), start=1):
        print(f"\nRound {round_no}")
        for name, review in reviews.items():
            verdict = "approved" if review.approved else "needs work"
            print(f"  - {name}: {verdict} (score {review.score}) {review.feedback}".rstrip())

    resolutions = result.get("resolutions", [])
    if resolutions:
        _print_stage("CROSS-CRITIQUE RESOLUTIONS")
        for resolution in resolutions:
            conflict = resolution.conflict
            print(f"\n{conflict.raised_by} vs {conflict.about}: {conflict.issue}")
            print(f"  -> {resolution.decision} (revise: {resolution.revise or 'none'})")

    _print_stage("FINAL STRATEGY")
    print(result["final_strategy"])


def main(path: str) -> None:
    scenario = json.loads(open(path, encoding="utf-8").read())
    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    context = scenario.get("context")
    state = {"request": scenario["prompt"]}
    if context:
        state["context"] = RequestContext(**context)

    # With Langfuse set up, each request is traced in the scenario's session.
    session = config["configurable"]["thread_id"]
    _print_stage(f"REQUEST\n{scenario['prompt']}")
    with tracing.trace("demo", session_id=session, input=scenario["prompt"], tags=["demo", Path(path).stem]):
        _print_result(graph.invoke(state, config))

    follow_up = scenario.get("follow_up")
    if follow_up:
        _print_stage(f"FOLLOW-UP\n{follow_up}")
        with tracing.trace("demo", session_id=session, input=follow_up, tags=["demo", "follow-up"]):
            _print_result(graph.invoke({"request": follow_up}, config))
    tracing.flush()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run python demo.py scenarios/<name>.json")
        raise SystemExit(1)
    main(sys.argv[1])

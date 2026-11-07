"""Experiments in Langfuse: the team run on the example scenarios and scored,
to compare a change (a prompt, the reasoning efforts) with the runs before it.

    uv run python experiments.py
    uv run python experiments.py --name "chief at low" --chief low --specialist minimal

Puts the scenarios (scenarios/*.json) in a Langfuse dataset, then runs the
team on each, every call traced into the experiment's run, and scores each
run with the team's own judgements (the review, the revisions, the conflicts,
the strategy's length) and the LLM judge's (judge.py). Langfuse shows the runs
side by side, item by item. Calls the real model: about two minutes and twenty
calls a scenario; needs the Langfuse keys and the model's in .env.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from langchain_core.runnables import RunnableConfig

import judge
import tracing
from agents.chief_of_staff import STRATEGY_WORDS
from agents.specialist import GAP_PREFIX
from graph import build_graph
from llm import EFFORTS, LLM_ERRORS, reasoning
from state import RequestContext, RequestInput

DATASET = "cofounder-scenarios"
SCENARIOS = Path(__file__).parent / "scenarios"


def sync_dataset(langfuse) -> int:
    """Put each scenario in the dataset, by its file's name, so a changed one is updated."""
    try:
        langfuse.create_dataset(name=DATASET, description="The app's example scenarios (scenarios/*.json).",
                                metadata={"source": "scenarios/"})
    except Exception:  # it is there already
        pass
    paths = sorted(SCENARIOS.glob("*.json"))
    for path in paths:
        scenario = json.loads(path.read_text(encoding="utf-8"))
        langfuse.create_dataset_item(
            dataset_name=DATASET,
            id=f"scenario-{path.stem}",
            input={"prompt": scenario["prompt"], "context": scenario.get("context")},
            metadata={"title": scenario.get("title", path.stem), "follow_up": scenario.get("follow_up")},
        )
    return len(paths)


def run_team(item, efforts: dict[str, str]) -> dict:
    """One evaluation of a scenario, as the API runs it; what the evaluators read."""
    data = item.input
    state: RequestInput = {"request": data["prompt"]}
    if data.get("context"):
        state["context"] = RequestContext(**data["context"])
    config: RunnableConfig = {"configurable": {"thread_id": str(uuid.uuid4())}}
    with tracing.handled(), reasoning(**efforts):
        result = build_graph().invoke(state, config)
    history = result.get("review_history") or []
    latest: dict = {}
    for round_ in history:
        latest.update(round_)
    return {
        "brief": data["prompt"],
        "strategy": result["final_strategy"],
        "reviews": {name: review.score for name, review in latest.items()},
        "approved_first_time": bool(history) and all(review.approved for review in history[0].values()),
        "revised": len({name for round_ in history[1:] for name in round_}
                       | {r.revise for r in result.get("resolutions", []) if r.revise}),
        "conflicts": len(result.get("resolutions", [])),
        "failed": sum(text.startswith(GAP_PREFIX) for text in result["analyses"].values()),
    }


def task_for(efforts: dict[str, str]):
    """The experiment's task. The runner calls a task on its event loop; the
    team runs off it, in a thread, so the scenarios run side by side and the
    look-ups can start the event loop their MCP clients need. The thread copies
    the context, so the run's calls land in its trace."""
    return lambda *, item, **_: asyncio.to_thread(run_team, item, efforts)


def team_scores(*, output, **_):
    """The team's own judgements on the run."""
    from langfuse import Evaluation

    reviews = output["reviews"]
    words = len(output["strategy"].split())
    return [
        Evaluation(name="review-average", value=round(sum(reviews.values()) / len(reviews), 2) if reviews else 0),
        Evaluation(name="approved-first-time", value=1 if output["approved_first_time"] else 0, data_type="BOOLEAN"),
        Evaluation(name="revisions", value=output["revised"]),
        Evaluation(name="conflicts", value=output["conflicts"]),
        Evaluation(name="failed-specialists", value=output["failed"]),
        Evaluation(name="strategy-words", value=words),
        Evaluation(name="within-word-limit", value=1 if words <= STRATEGY_WORDS * 1.1 else 0, data_type="BOOLEAN",
                   comment=f"{words} words; the limit is {STRATEGY_WORDS}."),
    ]


def judge_scores(*, output, **_):
    """The LLM judge's reading of the strategy (judge.py)."""
    from langfuse import Evaluation

    try:
        with tracing.handled():  # the judge's own call, in the run's trace
            judgement = judge.judge(output["brief"], output["strategy"])
    except LLM_ERRORS as error:
        return [Evaluation(name="judge-error", value=str(error)[:200], data_type="CATEGORICAL")]
    return [Evaluation(name=name, value=value, comment=judgement.comment)
            for name, value in judge.scores(judgement).items()]


def averages(*, item_results, **_):
    """The run's averages of the scores that matter most, for the run's row in Langfuse."""
    from langfuse import Evaluation

    names = ["review-average", *(f"judge-{name}" for name in judge.CRITERIA)]
    found: dict[str, list[float]] = {name: [] for name in names}
    for result in item_results:
        for evaluation in result.evaluations:
            if evaluation.name in found and isinstance(evaluation.value, (int, float)):
                found[evaluation.name].append(float(evaluation.value))
    return [Evaluation(name=f"mean-{name}", value=round(sum(values) / len(values), 2))
            for name, values in found.items() if values]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run the team on the example scenarios as a Langfuse experiment.")
    parser.add_argument("--name", default="the team, as configured", help="what this run tries, as Langfuse shows it")
    parser.add_argument("--specialist", choices=EFFORTS, help="the specialists' reasoning effort")
    parser.add_argument("--chief", choices=EFFORTS, help="the Chief of Staff's reasoning effort")
    args = parser.parse_args(argv)

    langfuse = tracing.client()
    if langfuse is None:
        print("Langfuse is not set up: put LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env.", file=sys.stderr)
        return 1
    tracing.register_prompts()
    count = sync_dataset(langfuse)
    efforts = {role: effort for role, effort in (("specialist", args.specialist), ("chief", args.chief)) if effort}
    print(f"Running the team on {count} scenarios: {args.name}.")
    # The judge, like the team (task_for), runs off the runner's event loop.
    result = langfuse.get_dataset(DATASET).run_experiment(
        name=args.name,
        description=f"Reasoning: {efforts or 'as configured'}.",
        task=task_for(efforts),
        evaluators=[team_scores, lambda **given: asyncio.to_thread(lambda: judge_scores(**given))],
        run_evaluators=[averages],
        max_concurrency=2,
        metadata={"specialist": args.specialist or "configured", "chief": args.chief or "configured"},
    )
    print(result.format())
    tracing.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

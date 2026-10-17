"""Tests for the review and refine loop (Step 6)."""

from graph import build_graph
from state import DelegationPlan, ReviewResult, Task

REVISE_MARKER = "asks you to revise"


def _only(name: str) -> DelegationPlan:
    return DelegationPlan(
        objective="Evaluate the request.",
        tasks=[Task(specialist=name, task=f"Handle {name}.")],
    )


def test_rejected_report_is_revised_with_feedback(fake_llm, thread):
    fake_llm.plan = _only("marketing")

    def review_for(report: str) -> ReviewResult:
        if REVISE_MARKER in report:  # the revised report
            return ReviewResult(approved=True, score=5, feedback="")
        return ReviewResult(approved=False, score=2, feedback="Add a target niche.")

    fake_llm._review_for = review_for
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI tool."}, thread)

    # The specialist ran twice: initial report, then a revision.
    assert fake_llm.specialist_calls["marketing"] == 2
    # The revision prompt carried the feedback.
    assert "Add a target niche." in result["analyses"]["marketing"]
    # Two review rounds recorded; the report ends approved.
    assert len(result["review_history"]) == 2
    assert result["reviews"]["marketing"].approved


def test_approved_reports_are_not_rerun(fake_llm, thread):
    fake_llm.plan = _only("marketing")
    # Default review approves everything.
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI tool."}, thread)

    assert fake_llm.specialist_calls["marketing"] == 1
    assert len(result["review_history"]) == 1
    assert fake_llm.synthesis_calls == 1


def test_loop_stops_at_max_iterations(fake_llm, thread):
    fake_llm.plan = _only("marketing")
    # Always reject: the single-revision cap must still end the loop.
    fake_llm._review_for = lambda report: ReviewResult(
        approved=False, score=1, feedback="Still not good enough."
    )
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI tool."}, thread)

    # One initial + one revision, then it stops despite the rejection.
    assert fake_llm.specialist_calls["marketing"] == 2
    assert result["final_strategy"]
    assert fake_llm.synthesis_calls == 1


def test_the_score_decides_the_verdict(fake_llm, thread):
    # Live, the model has scored a report 4 and still rejected it, and the other
    # way round; the verdict follows the score so the rubric holds.
    fake_llm.plan = DelegationPlan(
        objective="Evaluate the request.",
        tasks=[Task(specialist="marketing", task="Position it."),
               Task(specialist="finance", task="Price it.")],
    )

    def review_for(report: str) -> ReviewResult:
        if "Marketing Strategy Agent" in report:
            return ReviewResult(approved=False, score=4, feedback="Could be sharper.")
        return ReviewResult(approved=True, score=3, feedback="The prices contradict each other.")

    fake_llm._review_for = review_for
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI tool."}, thread)

    first_round = result["review_history"][0]
    assert first_round["marketing"].approved and first_round["marketing"].feedback == ""
    assert not first_round["finance"].approved
    # Only the report that scored 3 was sent back.
    assert fake_llm.specialist_calls == {"marketing": 1, "finance": 2}

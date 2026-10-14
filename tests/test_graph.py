"""Tests for the Step 2 graph: START -> marketing -> END."""

from graph import build_graph
from state import RequestContext


def test_graph_returns_all_four_analyses(fake_llm):
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI healthcare scheduling tool."})

    assert set(result["analyses"]) == {"marketing", "finance", "technical", "risk"}
    for analysis in result["analyses"].values():
        assert "AI healthcare scheduling tool" in analysis


def test_each_analysis_is_produced_under_its_own_role(fake_llm):
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI healthcare scheduling tool."})

    assert "Marketing Strategy Agent" in result["analyses"]["marketing"]
    assert "Financial Planning Agent" in result["analyses"]["finance"]
    assert "Technical Feasibility Agent" in result["analyses"]["technical"]
    assert "Risk & Compliance Agent" in result["analyses"]["risk"]


def test_context_fields_reach_the_analysis(fake_llm):
    graph = build_graph()

    result = graph.invoke(
        {
            "request": "Evaluate an AI healthcare scheduling tool.",
            "context": RequestContext(target_market="clinics", constraints="small budget"),
        }
    )

    analysis = result["analyses"]["marketing"]
    assert "clinics" in analysis
    assert "small budget" in analysis

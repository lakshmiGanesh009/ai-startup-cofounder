"""Tests for the Step 2 graph: START -> marketing -> END."""

from graph import build_graph
from state import RequestContext


def test_graph_returns_a_marketing_analysis(fake_llm):
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI healthcare scheduling tool."})

    assert set(result["analyses"]) == {"marketing"}
    analysis = result["analyses"]["marketing"]
    assert "Marketing Strategy Agent" in analysis
    assert "AI healthcare scheduling tool" in analysis


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

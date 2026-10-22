"""The app's prompts, by the name each has in Langfuse (tracing.py).

The code is their source: each module keeps its prompts, and this gathers
them, so that at start-up each is registered in Langfuse as a version, and
every model call is linked to the version it used. A prompt with parts that
depend on the request is registered as a template, with Langfuse's
{{variable}} in each such place (the currency rule, the topics of a decision
template). The names nest like folders: chief/, specialists/, brief/, ...
"""

from guardrails import RULES


def prompts() -> dict[str, str]:
    """Every prompt the app sends to a model, by name: its system message."""
    import brief
    import deep_research
    import judge
    import library
    import lookups
    from agents import chief_of_staff, proposal_writer
    from agents.roles import SPECIALISTS

    return {
        **chief_of_staff.prompts(),
        **{f"specialists/{role.name}": role.system_prompt for role in SPECIALISTS},
        **brief.prompts(),
        "research/competitors": deep_research._COMPETITORS_PROMPT + RULES,
        "lookups/fred-searches": lookups._FRED_PROMPT + RULES,
        "lookups/fred-picks": lookups._PICK_PROMPT + RULES,
        **proposal_writer.prompts(),
        "documents/answer": library.ANSWERER + RULES,
        "judge/strategy": judge.JUDGE_PROMPT + RULES,
    }

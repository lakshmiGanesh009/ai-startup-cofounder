"""What the team has just done, as the streaming endpoint reports it.

Each node of the graph returns a state update; `summarize` turns one into a
short account the UI can show while the rest of the team works ("Reviewed 4
reports: approved 3, sent back Financial Planning"), with the few figures
behind it.
"""

import logging

from agents.roles import ROLES
from agents.specialist import GAP_PREFIX

logger = logging.getLogger(__name__)


def _words(text: str) -> int:
    return len(text.split())


def _names(keys: list[str]) -> str:
    """Specialists' titles as a phrase: "Marketing Strategy and Risk & Compliance"."""
    titles = [ROLES[key].title if key in ROLES else key for key in keys]
    if len(titles) <= 1:
        return "".join(titles)
    return f"{', '.join(titles[:-1])} and {titles[-1]}"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _summary(node: str, update: dict, runs: int, given: dict) -> dict:
    if node == "plan":
        assigned = list(update["assignments"])
        return {
            "summary": f"Planned the work and assigned {_names(assigned)}.",
            "objective": update["plan"].objective,
            "assigned": assigned,
        }
    if node in ROLES:
        report = update["analyses"][node]
        if report.startswith(GAP_PREFIX):
            return {"summary": "Could not write its report: the LLM call failed.", "failed": True}
        verb = "Revised" if runs > 1 else "Wrote"
        return {
            "summary": f"{verb} its report ({_words(report)} words).",
            "words": _words(report),
            "revision": runs > 1,
        }
    if node == "review":
        # The update carries every review so far; this round reviewed the reports
        # sent back (its input's revisions), or on the first round all assigned.
        reviewed = given.get("revisions") or given.get("assignments") or update["reviews"]
        reviews = {name: update["reviews"][name] for name in reviewed if name in update["reviews"]}
        # Only the reports in the update's revisions go back; once the rounds
        # are used up, a report still below the bar goes forward as it is.
        back = [name for name in update.get("revisions", {}) if name in reviews]
        short = [name for name, review in reviews.items() if not review.approved and name not in back]
        approved = len(reviews) - len(back) - len(short)
        outcome = ", ".join(
            ([f"approved {approved}"] if approved else []) + ([f"sent back {_names(back)}"] if back else [])
        )
        if short:
            falls = "falls" if len(short) == 1 else "fall"
            outcome += ("; " if outcome else "") + f"{_names(short)} still {falls} short, with no revision left"
        summary = f"Reviewed {_plural(len(reviews), 'report')}" + (f": {outcome}." if outcome else ".")
        return {
            "summary": summary,
            "reviews": {
                name: {"approved": review.approved, "score": review.score}
                for name, review in reviews.items()
            },
        }
    if node == "research":
        deep = update["deep_research"]
        found = [f"{_plural(len(deep.areas), 'area')}", f"{_plural(len(deep.companies), 'competitor')}"]
        costs = ([f"{deep.credits} Tavily credits"] if deep.credits else []) + (
            [_plural(deep.searches, "web search").replace("searchs", "searches")] if deep.searches else []
        )
        summary = f"Researched {' and '.join(found)} ({', '.join([_plural(len(deep.sources), 'source'), *costs])})"
        if deep.failed:
            summary += f"; could not research {_names(deep.failed)}"
        return {
            "summary": summary + ".",
            "areas": list(deep.areas),
            "companies": [company.name for company in deep.companies],
            "credits": deep.credits,
            "searches": deep.searches,
            "provider": deep.providers[-1] if deep.providers else None,
            "not_researched": deep.failed,
        }
    if node == "critique":
        count = len(update["conflicts"])
        summary = (
            f"Cross-checked the reports and raised {_plural(count, 'conflict')}."
            if count
            else "Cross-checked the reports: no conflicts."
        )
        return {"summary": summary, "conflicts": count}
    if node == "resolve":
        resolutions = update["resolutions"]
        revise = sorted({r.revise for r in resolutions if r.revise})
        summary = f"Settled {_plural(len(resolutions), 'conflict')}"
        summary += f"; {_names(revise)} to revise." if revise else "."
        return {"summary": summary, "decisions": len(resolutions), "revise": revise}
    if node == "synthesis":
        words = _words(update["final_strategy"])
        return {"summary": f"Wrote the launch strategy ({words} words).", "words": words}
    return {"summary": "Done."}


def summarize(node: str, update: dict, runs: int, given: dict | None = None) -> dict:
    """An account of what `node` just did, from the state update it returned
    and the state it was `given`.

    `runs` counts the node's runs in this request, so a specialist's second run
    reads as a revision. A summary is never worth failing the request over, so
    an update of an unexpected shape gets a plain one.
    """
    try:
        return _summary(node, update or {}, runs, given or {})
    except (KeyError, AttributeError, TypeError) as error:
        logger.warning("Could not summarise %s: %s", node, error)
        return {"summary": "Done."}

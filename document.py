"""Changes to a report that code makes exactly, for the founder to preview and
then accept or discard: converting the currency or the units, replacing or
redacting text, removing a passage, and the document's settings. Each returns
a Draft (the report as it would be, what changed field by field, and a
summary) and saves nothing; reports.py saves a draft the founder accepts.

A model never does this arithmetic: every figure is a number converted here,
and every amount or measurement in the text is found and rewritten by the
patterns in currency.py and units.py.
"""

import re
from collections.abc import Callable
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, Field

import currency
import units
from proposal import (
    Channel,
    CostLine,
    FinancialPlan,
    MarketSize,
    Proposal,
    YearProjection,
)
from reports import DocumentSettings, Report, ReportSection

# The figures that are money, by the model that holds them.
MONEY: dict[type[BaseModel], tuple[str, ...]] = {
    MarketSize: ("value",),
    Channel: ("monthly_budget",),
    CostLine: ("amount",),
    YearProjection: ("one_off_revenue", "fixed_costs_month", "cac"),
    FinancialPlan: ("price_per_customer_month", "variable_cost_per_customer_month"),
}

PART_NAMES = {
    "executive": "Executive summary",
    "market": "Market & marketing",
    "technical": "Technical & operations",
    "risk": "Risk & compliance",
    "financial": "Financial plan",
}
# The field of a table's row that names it, in a change's label.
ROW_NAMES = ("item", "channel", "name", "role", "stage", "metric", "description")
REDACTED = "█"


class FieldChange(BaseModel):
    path: str = Field(description='Where in the report: "proposal.market.pricing_strategy", "sections.strategy".')
    label: str = Field(description="Where, for a person: Market & marketing · Pricing strategy.")
    before: str | float | None
    after: str | float | None
    money: bool = Field(False, description="A figure in the document's currency.")


class Draft(BaseModel):
    """A report as a change would leave it, unsaved."""

    report: Report
    changes: list[FieldChange]
    summary: str
    base_version: int = Field(description="The report version the draft was made from; accepting it needs it.")


class Unchanged(ValueError):
    """The change would leave the report as it is, so there is nothing to preview."""


# ---- Walking a report's text and figures ----

def _is_choice(annotation: Any) -> bool:
    """A field with fixed values (a verdict, a level), never rewritten as text."""
    return get_origin(annotation) is Literal or any(get_origin(arg) is Literal for arg in get_args(annotation))


def _map_model(model: BaseModel, text: Callable[[str], str] | None, money: Callable[[float], float] | None) -> BaseModel:
    """`model` with `text` applied to every free-text field and `money` to every
    figure that is money, in every part, row and sub-model."""
    updates: dict[str, Any] = {}
    figures = MONEY.get(type(model), ())
    for name, info in type(model).model_fields.items():
        value = getattr(model, name)
        if isinstance(value, BaseModel):
            updates[name] = _map_model(value, text, money)
        elif isinstance(value, list):
            updates[name] = [
                _map_model(item, text, money) if isinstance(item, BaseModel)
                else text(item) if text and isinstance(item, str) else item
                for item in value
            ]
        elif isinstance(value, str) and text and not _is_choice(info.annotation):
            updates[name] = text(value)
        elif name in figures and money and isinstance(value, int | float):
            updates[name] = money(value)
    return model.model_copy(update=updates)


def map_report(report: Report, text: Callable[[str], str] | None = None,
               money: Callable[[float], float] | None = None) -> Report:
    """The report with `text` applied to its title, objective, sections and the
    proposal's text, and `money` to the proposal's figures."""
    update: dict[str, Any] = {}
    if text:
        update |= {
            "title": text(report.title),
            "objective": text(report.objective),
            "sections": [section.model_copy(update={"body": text(section.body)}) for section in report.sections],
        }
    if report.proposal:
        update["proposal"] = _map_model(report.proposal, text, money)
    return report.model_copy(update=update)


def _leaves(value: Any, path: str) -> dict[str, Any]:
    """Every text and number in a report's content, by its path."""
    if isinstance(value, BaseModel):
        found: dict[str, Any] = {}
        for name in type(value).model_fields:
            found |= _leaves(getattr(value, name), f"{path}.{name}" if path else name)
        return found
    if isinstance(value, list):
        found = {}
        for index, item in enumerate(value):
            key = item.key if isinstance(item, ReportSection) else str(index)
            found |= _leaves(item.body if isinstance(item, ReportSection) else item, f"{path}.{key}")
        return found
    return {path: value}


def _content(report: Report) -> dict[str, Any]:
    leaves = {"title": report.title, "objective": report.objective}
    leaves |= _leaves(report.sections, "sections")
    leaves |= _leaves(report.settings, "settings")
    if report.proposal:
        leaves |= _leaves(report.proposal, "proposal")
    return leaves


def _words(name: str) -> str:
    return name.replace("_", " ").capitalize()


def label(report: Report, path: str) -> str:
    """Where a change is, for a person: "Financial plan · CapEx · Contractor dev · Amount"."""
    parts = path.split(".")
    if parts[0] == "sections":
        section = next((s for s in report.sections if s.key == parts[1]), None)
        return f"Team report · {section.title if section else parts[1]}"
    if parts[0] == "settings":
        return f"Settings · {_words(parts[1])}"
    if parts[0] != "proposal":
        return _words(parts[0])
    words = [PART_NAMES.get(parts[1], parts[1])]
    node: Any = getattr(report.proposal, parts[1], None)
    for part in parts[2:]:
        if part.isdigit() and isinstance(node, list) and int(part) < len(node):
            node = node[int(part)]
            name = next((getattr(node, f) for f in ROW_NAMES if isinstance(getattr(node, f, None), str)), None)
            words.append(name if name else f"Row {int(part) + 1}")
        else:
            words.append(_words(part).replace("Capex", "CapEx").replace("Opex", "OpEx").replace("Cac", "CAC")
                         .replace("Tam", "TAM").replace("Sam", "SAM").replace("Som", "SOM").replace("Kpis", "KPIs"))
            node = getattr(node, part, None)
    return " · ".join(words)


def changes(before: Report, after: Report) -> list[FieldChange]:
    """What differs between two versions of a report, field by field."""
    old, new = _content(before), _content(after)
    paths = list(dict.fromkeys([*new, *old]))
    figures = {name for names in MONEY.values() for name in names}
    return [
        FieldChange(path=path, label=label(after if path in new else before, path),
                    before=_shown(old.get(path)), after=_shown(new.get(path)),
                    money=path.startswith("proposal.") and path.rsplit(".", 1)[-1] in figures)
        for path in paths
        if old.get(path) != new.get(path)
    ]


def _shown(value: Any) -> str | float | None:
    if value is None or isinstance(value, str | float | int) and not isinstance(value, bool):
        return value
    return str(value)


def draft(report: Report, after: Report, summary: str, allow_unchanged: bool = False) -> Draft:
    """The draft of a change; Unchanged if it changes nothing, unless allowed
    (a revision the agents returned as it was)."""
    found = changes(report, after)
    if not found and not allow_unchanged:
        raise Unchanged(summary)
    if not found:
        summary = "The team returned it unchanged; ask for the change another way."
    return Draft(report=after, changes=found, summary=summary, base_version=report.version)


# ---- The changes ----

def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def convert_currency(report: Report, to: str, rate: float, relabel: bool = False) -> Draft:
    """Every figure and every amount in the text in `to`: converted at `rate`
    (one unit of the current currency in `to`), or, with `relabel`, kept as
    they are and only shown in `to`."""
    source = report.settings.currency
    if to == source:
        raise Unchanged(f"The document is already in {to}.")
    factor = 1.0 if relabel else rate
    counted = {"text": 0, "figures": 0}

    def text(value: str) -> str:
        written, count = currency.convert_text(value, source, to, factor)
        counted["text"] += count
        return written

    def money(value: float) -> float:
        counted["figures"] += 1
        return round(value * factor, 2)

    after = map_report(report, text, money)
    after = after.model_copy(update={"settings": after.settings.model_copy(update={"currency": to})})
    names = f"{source} to {to}"
    done = (f"Relabelled {_plural(counted['figures'], 'figure')} and {_plural(counted['text'], 'amount')} "
            f"in the text from {names}, without converting them"
            if relabel else
            f"Converted {_plural(counted['figures'], 'figure')} and {_plural(counted['text'], 'amount')} in the "
            f"text from {names} at 1 {source} = {rate:g} {to}")
    return draft(report, after, done + ".")


def convert_units(report: Report, to: units.System) -> Draft:
    """Every measurement in the text in the metric or the imperial system."""
    counted = 0

    def text(value: str) -> str:
        nonlocal counted
        written, count = units.convert_units(value, to)
        counted += count
        return written

    after = map_report(report, text)
    after = after.model_copy(update={"settings": after.settings.model_copy(update={"units": to})})
    if not counted:
        raise Unchanged(f"There is no measurement in the {'imperial' if to == 'metric' else 'metric'} system to convert.")
    return draft(report, after, f"Converted {_plural(counted, 'measurement')} to the {to} system.")


def _term(find: str, match_case: bool, whole_words: bool) -> re.Pattern[str]:
    pattern = re.escape(find)
    if whole_words:
        pattern = rf"(?<!\w){pattern}(?!\w)"
    return re.compile(pattern, 0 if match_case else re.IGNORECASE)


def replace(report: Report, find: str, by: str, match_case: bool = False, whole_words: bool = True) -> Draft:
    """`find` replaced by `by` everywhere: the title, the objective, the team's
    report and the proposal (a renamed product, say)."""
    pattern = _term(find, match_case, whole_words)
    counted = 0

    def text(value: str) -> str:
        nonlocal counted
        written, count = pattern.subn(lambda _: by, value)
        counted += count
        return written

    after = map_report(report, text)
    if not counted:
        raise Unchanged(f"“{find}” does not appear in the document.")
    return draft(report, after, f"Replaced {_plural(counted, 'occurrence')} of “{find}” with “{by}”.")


def redact(report: Report, terms: list[str]) -> Draft:
    """Each of `terms` blacked out wherever it appears, whatever its case."""
    terms = [term for term in dict.fromkeys(t.strip() for t in terms) if term]
    patterns = [(_term(term, False, True), REDACTED * min(max(len(term), 4), 12)) for term in terms]
    counted = 0

    def text(value: str) -> str:
        nonlocal counted
        for pattern, bar in patterns:
            value, count = pattern.subn(bar, value)
            counted += count
        return value

    after = map_report(report, text)
    if not counted:
        raise Unchanged("None of these appears in the document.")
    return draft(report, after, f"Redacted {_plural(counted, 'occurrence')} of {_plural(len(terms), 'term')}.")


def text_at(report: Report, path: str) -> str:
    """The text of one field, by its path."""
    value = _content(report).get(path)
    if not isinstance(value, str) or path.startswith("settings."):
        raise KeyError(path)
    return value


def set_text(report: Report, path: str, value: str) -> Report:
    """The report with one text field, by its path, set to `value`."""
    parts = path.split(".")
    if parts[0] in ("title", "objective") and len(parts) == 1:
        return report.model_copy(update={parts[0]: value})
    if parts[0] == "sections" and len(parts) == 2:
        sections = [s.model_copy(update={"body": value}) if s.key == parts[1] else s for s in report.sections]
        return report.model_copy(update={"sections": sections})
    if parts[0] != "proposal" or not report.proposal:
        raise KeyError(path)
    data = report.proposal.model_dump()
    node: Any = data
    for part in parts[1:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return report.model_copy(update={"proposal": Proposal.model_validate(data)})


def remove_passage(report: Report, path: str, passage: str) -> Draft:
    """`passage` taken out of the field at `path`, with the line it stood on
    when it was a whole paragraph or list item."""
    text = text_at(report, path)
    if passage not in text:
        raise Unchanged("That passage is no longer in the document; reload it.")
    lines = text.split("\n")
    kept = [line for line in lines if line.strip().lstrip("-*0123456789. ").strip() != passage.strip()]
    written = "\n".join(kept) if len(kept) < len(lines) else text.replace(passage, "", 1)
    written = re.sub(r"\n{3,}", "\n\n", written).strip()
    return draft(report, set_text(report, path, written), f"Removed a passage from {label(report, path)}.")


def settings(report: Report, change: DocumentSettings) -> Draft:
    """New settings that need no conversion: who the document is from, and the
    sections left out. The currency and the units change by converting."""
    kept = change.model_copy(update={"currency": report.settings.currency, "units": report.settings.units})
    after = report.model_copy(update={"settings": kept})
    hidden = [s.title for s in report.sections if s.key in kept.hidden and s.key not in report.settings.hidden]
    shown = [s.title for s in report.sections if s.key in report.settings.hidden and s.key not in kept.hidden]
    said = []
    if kept.prepared_by != report.settings.prepared_by:
        said.append(f"is now prepared by {kept.prepared_by}")
    if hidden:
        said.append(f"leaves out {', '.join(hidden)}")
    if shown:
        said.append(f"shows {', '.join(shown)} again")
    return draft(report, after, f"The document {' and '.join(said) or 'keeps its settings'}.")

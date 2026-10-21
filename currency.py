"""Money in the report's currency.

Every amount in a proposal is a plain number; the currency is a setting of the
report (DocumentSettings.currency). So code, never a model, shows each amount,
converts it at a rate the founder gives, or relabels it. The PDF, its charts,
what the agents read and the checks on the figures all format money here, in
the currency `using()` sets for the work at hand.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import NamedTuple


class Currency(NamedTuple):
    code: str
    # Before the amount: "$12,000", "CHF 12,000".
    symbol: str
    name: str
    # How the text may write an amount in it, besides the symbol and the code:
    # the prefixes ("US$") and the words after the number ("dollars").
    prefixes: tuple[str, ...] = ()
    words: tuple[str, ...] = ()


# The currencies the founder can choose, with the symbols DejaVu Sans (the
# PDF's font) can draw.
CURRENCIES: dict[str, Currency] = {
    c.code: c
    for c in (
        Currency("USD", "$", "US dollar", ("US$",), ("US dollars", "dollars")),
        Currency("EUR", "€", "euro", (), ("euros",)),
        Currency("GBP", "£", "pound sterling", (), ("pounds", "pounds sterling")),
        Currency("INR", "₹", "Indian rupee", ("Rs.", "Rs"), ("rupees",)),
        Currency("JPY", "¥", "Japanese yen", ("JP¥",), ("yen",)),
        Currency("CNY", "CN¥", "Chinese yuan", ("RMB",), ("yuan", "renminbi")),
        Currency("CAD", "CA$", "Canadian dollar", ("C$",), ("Canadian dollars",)),
        Currency("AUD", "A$", "Australian dollar", ("AU$",), ("Australian dollars",)),
        Currency("NZD", "NZ$", "New Zealand dollar", (), ("New Zealand dollars",)),
        Currency("SGD", "S$", "Singapore dollar", (), ("Singapore dollars",)),
        Currency("HKD", "HK$", "Hong Kong dollar", (), ("Hong Kong dollars",)),
        Currency("CHF", "CHF ", "Swiss franc", ("Fr.",), ("Swiss francs", "francs")),
        Currency("SEK", "SEK ", "Swedish krona", (), ("kronor",)),
        Currency("NOK", "NOK ", "Norwegian krone", (), ("Norwegian kroner",)),
        Currency("DKK", "DKK ", "Danish krone", (), ("Danish kroner",)),
        Currency("PLN", "PLN ", "Polish złoty", (), ("złoty", "zloty")),
        Currency("ZAR", "R ", "South African rand", (), ("rand",)),
        Currency("BRL", "R$", "Brazilian real", (), ("reais",)),
        Currency("MXN", "MX$", "Mexican peso", (), ("Mexican pesos",)),
        Currency("AED", "AED ", "UAE dirham", (), ("dirhams",)),
        Currency("SAR", "SAR ", "Saudi riyal", (), ("riyals",)),
        Currency("KRW", "₩", "South Korean won", (), ("won",)),
    )
}

DEFAULT = "USD"

_current: ContextVar[str] = ContextVar("currency", default=DEFAULT)


@contextmanager
def using(code: str) -> Iterator[None]:
    """Format money in `code` for the work inside the block: a PDF, a prompt."""
    token = _current.set(code)
    try:
        yield
    finally:
        _current.reset(token)


def current() -> Currency:
    return CURRENCIES.get(_current.get(), CURRENCIES[DEFAULT])


def full(value: float, code: str | None = None) -> str:
    """A whole amount: $12,000, -€6,000, CHF 1,500."""
    currency = CURRENCIES.get(code, current()) if code else current()
    sign = "-" if value < 0 else ""
    return f"{sign}{currency.symbol}{abs(value):,.0f}"


def compact(value: float, code: str | None = None) -> str:
    """A short amount: $750, €12k, £1.2M."""
    currency = CURRENCIES.get(code, current()) if code else current()
    sign = "-" if value < 0 else ""
    size = abs(value)
    for unit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if size >= unit:
            number = size / unit
            text = f"{number:.0f}" if number >= 100 else f"{number:.1f}".removesuffix(".0")
            return f"{sign}{currency.symbol}{text}{suffix}"
    return f"{sign}{currency.symbol}{size:,.0f}"


# ---- Amounts in text ----

_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_SCALE = r"(?:\s?(?:thousand|million|billion|mn|bn|k|K|M|B)\b)"
_SCALES = {"thousand": 1e3, "k": 1e3, "K": 1e3, "million": 1e6, "mn": 1e6, "M": 1e6,
           "billion": 1e9, "bn": 1e9, "B": 1e9}


def _alternatives(options: list[str]) -> str:
    return "|".join(re.escape(option) for option in sorted(options, key=len, reverse=True))


def amount_pattern(code: str) -> re.Pattern[str]:
    """Amounts written in `code`: "$12,000", "US$1.2M", "€15k", "1,500 USD",
    "2 million dollars", and both ends of a range ("$10–20k", "$5 to $8")."""
    currency = CURRENCIES[code]
    before = _alternatives([currency.symbol.strip(), code, *currency.prefixes])
    after = _alternatives([code, *currency.words])
    # A "$" in "US$" or "CA$" is not this currency's own "$".
    guard = r"(?<![A-Za-z$€£¥₹₩])"
    dash = rf"\s?[–-]\s?(?:{before})?|\s+to\s+(?:{before})"
    return re.compile(
        rf"{guard}(?P<before>{before})\s?(?P<number>{_NUMBER})(?P<scale>{_SCALE})?"
        rf"(?:(?P<dash>{dash})\s?(?P<number2>{_NUMBER})(?P<scale2>{_SCALE})?)?"
        rf"|(?<![\w.,])(?P<number3>{_NUMBER})(?P<scale3>{_SCALE})?\s(?P<after>{after})\b"
    )


def _number(text: str) -> float:
    return float(text.replace(",", ""))


def _write_number(value: float, like: str, scaled: bool) -> str:
    """`value` written the way `like` was, with as many decimals; a scaled
    amount ("15k") keeps one decimal where it matters ("13.8k")."""
    decimals = len(like.split(".")[1]) if "." in like else 0
    if scaled:
        decimals = max(decimals, 1 if value < 100 else 0)
        text = f"{value:,.{decimals}f}"
        return text.removesuffix(".0") if decimals == 1 else text
    if not decimals and value < 10 and value != round(value):
        decimals = 2
    return f"{value:,.{decimals}f}"


def convert_text(text: str, source: str, target: str, rate: float) -> tuple[str, int]:
    """`text` with every amount in `source` written in `target`, multiplied by
    `rate` (1 to relabel), and how many amounts were changed."""
    pattern = amount_pattern(source)
    goal = CURRENCIES[target]
    count = 0

    def write(number: str, scale: str | None, scaled: bool) -> str:
        return _write_number(_number(number) * rate, number, scaled) + (scale or "")

    def replace(match: re.Match) -> str:
        nonlocal count
        if match["number3"]:
            count += 1
            # "1,500 USD" takes the target's code; "2 million dollars" its name.
            word = match["after"]
            named = word != source and goal.words
            return f"{write(match['number3'], match['scale3'], bool(match['scale3']))} {goal.words[0] if named else target}"
        count += 1
        if not match["number2"]:
            return f"{goal.symbol}{write(match['number'], match['scale'], bool(match['scale']))}"
        count += 1
        # In "$10–20k" the first number is in thousands too.
        first = write(match["number"], match["scale"], bool(match["scale"] or match["scale2"]))
        dash = "–" if match["dash"].strip().startswith(("–", "-")) else " to "
        return f"{goal.symbol}{first}{dash}{goal.symbol}{write(match['number2'], match['scale2'], bool(match['scale2']))}"

    return pattern.sub(replace, text), count

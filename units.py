"""Measurements in text, converted between imperial and metric by code.

Only units that cannot be mistaken for something else are converted: "5 km",
"2,000 sq ft", "150 lb", "72°F", but not "5m" (five million?) or "5G" (a
network). Each converted figure keeps about three significant digits.
"""

import re
from typing import Literal, NamedTuple

System = Literal["metric", "imperial"]


class Unit(NamedTuple):
    names: tuple[str, ...]
    # To the other system: times `factor`, plus `offset` for a scale with its
    # own zero (temperature).
    factor: float
    target: str
    offset: float = 0.0


# Longer names first, so "square feet" is not read as "feet", "fl oz" as "oz".
IMPERIAL: list[Unit] = [
    Unit(("miles per hour", "mph"), 1.609344, "km/h"),
    Unit(("square miles", "square mile", "sq mi"), 2.589988110336, "km²"),
    Unit(("square feet", "square foot", "sq ft", "sq. ft.", "sqft", "ft²"), 0.09290304, "m²"),
    Unit(("square yards", "sq yd"), 0.83612736, "m²"),
    Unit(("fluid ounces", "fl oz"), 29.5735295625, "mL"),
    Unit(("degrees Fahrenheit", "°F"), 5 / 9, "°C", -32 * 5 / 9),
    Unit(("miles", "mile", "mi"), 1.609344, "km"),
    Unit(("yards", "yard", "yd"), 0.9144, "m"),
    Unit(("feet", "foot", "ft"), 0.3048, "m"),
    Unit(("inches", "inch"), 2.54, "cm"),
    Unit(("acres", "acre"), 0.40468564224, "ha"),
    Unit(("pounds of", "lbs", "lb"), 0.45359237, "kg"),
    Unit(("ounces", "ounce", "oz"), 28.349523125, "g"),
    Unit(("gallons", "gallon", "gal"), 3.785411784, "L"),
    Unit(("short tons", "tons", "ton"), 0.90718474, "t"),
]

METRIC: list[Unit] = [
    Unit(("kilometres per hour", "kilometers per hour", "km/h", "kph"), 1 / 1.609344, "mph"),
    Unit(("square kilometres", "square kilometers", "km²", "sq km"), 1 / 2.589988110336, "sq mi"),
    Unit(("square metres", "square meters", "square metre", "square meter", "m²", "sq m"), 1 / 0.09290304, "sq ft"),
    Unit(("millilitres", "milliliters", "mL", "ml"), 1 / 29.5735295625, "fl oz"),
    Unit(("degrees Celsius", "°C"), 9 / 5, "°F", 32),
    Unit(("kilometres", "kilometers", "km"), 1 / 1.609344, "mi"),
    Unit(("centimetres", "centimeters", "cm"), 1 / 2.54, "in"),
    Unit(("metres", "meters"), 1 / 0.3048, "ft"),
    Unit(("hectares", "hectare", "ha"), 1 / 0.40468564224, "acres"),
    Unit(("kilograms", "kilogram", "kg"), 1 / 0.45359237, "lb"),
    Unit(("grams", "gram"), 1 / 28.349523125, "oz"),
    Unit(("litres", "liters", "litre", "liter"), 1 / 3.785411784, "gal"),
    Unit(("tonnes", "tonne"), 1 / 0.90718474, "short tons"),
]

_NUMBER = r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?"


def _alternatives(units: list[Unit]) -> str:
    names = sorted((name for unit in units for name in unit.names), key=len, reverse=True)
    return "|".join(re.escape(name) for name in names)


def _pattern(units: list[Unit]) -> re.Pattern[str]:
    # A unit ends at a word boundary, or right after a symbol ("°F", "m²").
    return re.compile(rf"(?<![\w.,])(?P<number>{_NUMBER})(?P<space>\s?)(?P<unit>{_alternatives(units)})(?![\w²])")


def _rate_pattern(units: list[Unit]) -> re.Pattern[str]:
    """A figure per unit: "€0.69/sqft", "20 people per acre"."""
    plain = [unit for unit in units if not unit.offset]  # never "per °F"
    return re.compile(
        rf"(?<![\w.,])(?P<number>{_NUMBER})(?P<per>\s?/\s?|\s+per\s+)(?P<unit>{_alternatives(plain)})(?![\w²])"
    )


def _write(value: float) -> str:
    """About three significant digits: 8.05, 68.0 → 68, 186, 1,609."""
    size = abs(value)
    decimals = 2 if size < 10 else 1 if size < 100 else 0
    text = f"{value:,.{decimals}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def convert_units(text: str, to: System) -> tuple[str, int]:
    """`text` with each measurement in the other system written in `to`, and
    how many were changed."""
    units = IMPERIAL if to == "metric" else METRIC
    by_name = {name.lower(): unit for unit in units for name in unit.names}
    pattern = _pattern(units)
    count = 0

    def per(match: re.Match) -> str:
        """A rate converts the other way: €0.69 a square foot is €7.43 a square metre."""
        nonlocal count
        unit = by_name[match["unit"].lower()]
        count += 1
        return f"{_write(float(match['number'].replace(',', '')) / unit.factor)}{match['per']}{unit.target}"

    text = _rate_pattern(units).sub(per, text)

    def replace(match: re.Match) -> str:
        nonlocal count
        unit = by_name[match["unit"].lower()]
        value = float(match["number"].replace(",", "")) * unit.factor + unit.offset
        count += 1
        degrees = unit.target.startswith("°")
        suffix = " of" if match["unit"] == "pounds of" else ""
        return f"{_write(value)}{'' if degrees else ' '}{unit.target}{suffix}"

    return pattern.sub(replace, text), count

"""Hand-rolled unit parsing/conversion for shopping list consolidation.

Deliberately not using `pint` — we only need ~20 units and pint is too heavy
for a Heroku dyno running alongside the rest of the app. Supports summing
volume and weight quantities and rendering the total in either the metric
or imperial unit system, per-user (see `User.units`).
"""
import re
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Set

UnitSystem = Literal["metric", "imperial"]


@dataclass
class ParsedQuantity:
    amount: float
    unit: Optional[str]
    original_text: str


UNIT_ALIASES: Dict[str, str] = {
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "cup": "cup", "cups": "cup",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "floz": "floz", "fl oz": "floz", "fluid ounce": "floz", "fluid ounces": "floz",
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
}

DIMENSIONS: Dict[str, Set[str]] = {
    "volume": {"ml", "l", "cup", "tbsp", "tsp", "floz"},
    "weight": {"g", "kg", "oz", "lb"},
}

# Conversion factors to the base unit for each dimension (ml for volume, g for weight)
_VOLUME_TO_ML = {
    "ml": 1.0,
    "l": 1000.0,
    "cup": 236.6,
    "tbsp": 14.79,
    "tsp": 4.93,
    "floz": 29.57,
}

_WEIGHT_TO_G = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.35,
    "lb": 453.6,
}

_NON_MEASUREMENT_WORDS = ("pinch", "to taste", "handful", "dash", "splash", "squeeze")

_NUM_RE = re.compile(r"^\s*(\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+)\s*(.*)$")


def _parse_number(num_str: str) -> Optional[float]:
    num_str = num_str.strip()
    if not num_str:
        return None
    if " " in num_str:
        whole, _, frac = num_str.partition(" ")
        try:
            whole_val = float(whole)
            num, denom = frac.split("/")
            return whole_val + (float(num) / float(denom))
        except (ValueError, ZeroDivisionError):
            return None
    if "/" in num_str:
        try:
            num, denom = num_str.split("/")
            return float(num) / float(denom)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(num_str)
    except ValueError:
        return None


def parse_quantity(text: str) -> Optional[ParsedQuantity]:
    """Parse a free-text quantity like "200 g", "1/2 cup", "1 1/2 cups", "2".

    Returns None for non-numeric amounts like "to taste" or "pinch".
    """
    if not text:
        return None

    stripped = text.strip()
    if not stripped:
        return None

    lower = stripped.lower()
    if any(word in lower for word in _NON_MEASUREMENT_WORDS):
        return None

    match = _NUM_RE.match(stripped)
    if not match:
        return None

    num_str, rest = match.groups()
    amount = _parse_number(num_str)
    if amount is None:
        return None

    rest = rest.strip().lower()
    unit: Optional[str] = None
    if rest:
        unit = UNIT_ALIASES.get(rest, rest)

    return ParsedQuantity(amount=amount, unit=unit, original_text=stripped)


def _format_number(value: float) -> str:
    value = round(value, 2)
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_volume(total_ml: float, unit_system: UnitSystem) -> str:
    if unit_system == "imperial":
        cup_ml = _VOLUME_TO_ML["cup"]
        floz_ml = _VOLUME_TO_ML["floz"]
        tbsp_ml = _VOLUME_TO_ML["tbsp"]
        tsp_ml = _VOLUME_TO_ML["tsp"]

        if total_ml >= cup_ml:
            return f"{_format_number(total_ml / cup_ml)} cup"
        if total_ml >= floz_ml:
            return f"{_format_number(total_ml / floz_ml)} floz"
        if total_ml >= tbsp_ml:
            return f"{_format_number(total_ml / tbsp_ml)} tbsp"
        return f"{_format_number(total_ml / tsp_ml)} tsp"

    if total_ml >= 1000:
        return f"{_format_number(total_ml / 1000)} l"
    return f"{_format_number(total_ml)} ml"


def _format_weight(total_g: float, unit_system: UnitSystem) -> str:
    if unit_system == "imperial":
        oz_g = _WEIGHT_TO_G["oz"]
        lb_g = _WEIGHT_TO_G["lb"]
        if total_g >= 16 * oz_g:
            return f"{_format_number(total_g / lb_g)} lb"
        return f"{_format_number(total_g / oz_g)} oz"

    if total_g >= 1000:
        return f"{_format_number(total_g / 1000)} kg"
    return f"{_format_number(total_g)} g"


def sum_quantities(quantities: List[str], unit_system: UnitSystem) -> str:
    """Sum a list of free-text quantities, converting compatible units and
    rendering the total for the given unit system.

    Incompatible/unparseable amounts are joined onto the result with " + "
    using their original text.
    """
    parsed: List[ParsedQuantity] = []
    unparsed: List[str] = []

    for q in quantities:
        pq = parse_quantity(q)
        if pq is None:
            unparsed.append(q)
        else:
            parsed.append(pq)

    volume_total_ml = 0.0
    weight_total_g = 0.0
    has_volume = False
    has_weight = False
    incompatible: List[str] = []

    for pq in parsed:
        if pq.unit in _VOLUME_TO_ML:
            volume_total_ml += pq.amount * _VOLUME_TO_ML[pq.unit]
            has_volume = True
        elif pq.unit in _WEIGHT_TO_G:
            weight_total_g += pq.amount * _WEIGHT_TO_G[pq.unit]
            has_weight = True
        else:
            incompatible.append(pq.original_text)

    results: List[str] = []
    if has_volume:
        results.append(_format_volume(volume_total_ml, unit_system))
    if has_weight:
        results.append(_format_weight(weight_total_g, unit_system))
    results.extend(incompatible)
    results.extend(unparsed)

    if not results:
        return ""
    if len(results) == 1:
        return results[0]
    return " + ".join(results)

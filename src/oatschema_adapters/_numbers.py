# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import json
import math
import re
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation
from typing import Any, NoReturn

from oatschema_adapters._options import shorten

MAX_ITEMS = 100_000
MAX_KEY = 1024
_MAX_JSON_DEPTH = 64
_MAX_JSON_TOKENS = 4_000_000
_NUMBER = re.compile(r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?")
_MAX_NUMBER_TEXT = 1100
_EXACT = Context(prec=4000, traps=[])


def _is_held_exactly(text: str, value: float) -> bool:
    written = Decimal(text)
    if not written:
        return True
    held = Decimal(value)
    if held == written or Decimal(repr(value)) == written:
        return True
    digits = written.as_tuple().digits
    significant = len(digits) - (len(digits) - len("".join(map(str, digits)).rstrip("0")))
    return Context(prec=significant, rounding=ROUND_HALF_EVEN, traps=[]).plus(held) == written


def parse_number(text: str) -> float:
    """Return the number written in ``text``, as a float.

    The text must be a plain decimal number that a double holds. ``nan``, ``inf``, ``1e400``, ``1e-400`` and
    ``1.00000000000000001`` have no such value without rounding, so they are refused, as is anything else that isn't
    a number. A double written to any number of digits, such as ``0.10000000000000001``, reads back as itself.

    Raises:
        ValueError: ``text`` is not such a number.
    """
    stripped = text.strip()
    if len(stripped) > _MAX_NUMBER_TEXT or not _NUMBER.fullmatch(stripped):
        raise ValueError(f"not a number: {shorten(text)}")
    value = float(stripped)
    try:
        held = value not in (float("inf"), float("-inf")) and _is_held_exactly(stripped, value)
    except InvalidOperation:
        held = False
    if not held:
        raise ValueError(f"a double can't hold this number without rounding it: {shorten(text)}")
    return value


def decimal_number(value: Decimal) -> float:
    """Return an exactly computed ``value`` as a float, as ``parse_number`` does for its text.

    Raises:
        ValueError: A double can't hold ``value`` without rounding it.
    """
    return parse_number(format(value, "f"))


def _nearest(value: Decimal) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("the result is too large for a double")
    return number


def difference(high: str, low: str) -> float:
    """Return ``high - low``, two numbers ``parse_number`` accepts, computed exactly, as the nearest double.

    Raises:
        ValueError: Either isn't a number, or the result is too large for a double.
    """
    parse_number(high)
    parse_number(low)
    return _nearest(_EXACT.subtract(Decimal(high.strip()), Decimal(low.strip())))


def percentage(text: str) -> float:
    """Return ``text``, a number ``parse_number`` accepts, divided by 100, computed exactly, as the nearest double.

    Raises:
        ValueError: ``text`` isn't a number.
    """
    parse_number(text)
    return _nearest(_EXACT.divide(Decimal(text.strip()), Decimal(100)))


def seconds_from(whole_seconds: int, fraction: str) -> float:
    """Return ``whole_seconds`` plus ``fraction``, a number ``parse_number`` accepts, computed exactly.

    Raises:
        ValueError: ``fraction`` isn't a number, or a double can't hold the result without rounding it.
    """
    parse_number(fraction)
    return decimal_number(_EXACT.add(Decimal(whole_seconds), Decimal(fraction.strip())))


def milliseconds_to_seconds(milliseconds: int) -> float:
    """Return ``milliseconds`` in seconds, computed exactly.

    Raises:
        ValueError: A double can't hold the result without rounding it.
    """
    return decimal_number(_EXACT.divide(Decimal(milliseconds), Decimal(1000)))


def _refuse_constant(name: str) -> NoReturn:
    raise ValueError(f"{name} is not a JSON number")


def _checked_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("a JSON object has the same key twice")
    if any(len(key) > MAX_KEY for key in result):
        raise ValueError(f"a JSON object has a key longer than {MAX_KEY} characters")
    return result


def _check_depth(value: Any) -> None:
    level = [value]
    for _ in range(_MAX_JSON_DEPTH):
        level = [
            child
            for item in level
            if isinstance(item, (dict, list))
            for child in (item.values() if isinstance(item, dict) else item)
            if isinstance(child, (dict, list))
        ]
        if not level:
            return
    raise ValueError(f"the JSON is nested more than {_MAX_JSON_DEPTH} levels deep")


def _token_count(text: str | bytes) -> int:
    if isinstance(text, str):
        return text.count(",") + text.count("[") + text.count("{")
    return text.count(b",") + text.count(b"[") + text.count(b"{")


def load_json(text: str | bytes) -> Any:
    """Return the value of a JSON document, with its numbers exact.

    Raises:
        ValueError: ``text`` isn't JSON, has ``NaN`` or ``Infinity``, repeats a key in an object, has a key over
            1024 characters, nests more than 64 levels deep, has more than 4,000,000 commas and opening brackets,
            or has a number that ``parse_number`` refuses.
    """
    if _token_count(text) > _MAX_JSON_TOKENS:
        raise ValueError(f"the JSON has more than {_MAX_JSON_TOKENS} commas and opening brackets")
    try:
        value = json.loads(
            text,
            parse_float=parse_number,
            parse_constant=_refuse_constant,
            object_pairs_hook=_checked_object,
        )
    except RecursionError:
        message = f"the JSON is nested more than {_MAX_JSON_DEPTH} levels deep"
    except UnicodeDecodeError as error:
        message = f"the JSON is not valid text at byte {error.start}"
    except json.JSONDecodeError as error:
        message = f"not valid JSON: {error.msg} at line {error.lineno}, column {error.colno}"
    else:
        _check_depth(value)
        return value
    raise ValueError(message)

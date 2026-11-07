# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import math

from oatschema_adapters._numbers import seconds_from
from oatschema_adapters._options import shorten


def split_milliseconds(seconds: float) -> tuple[int, int, int, int]:
    """Return ``(hours, minutes, seconds, milliseconds)`` for ``seconds``, rounded to the nearest millisecond.

    Raises:
        ValueError: ``seconds`` is negative or not finite.
    """
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"a time must be a finite number of seconds, at least 0, not {seconds!r}")
    total = int(f"{seconds:.3f}".replace(".", ""))
    hours, rest = divmod(total, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return hours, minutes, secs, millis


def clock(seconds: float) -> str:
    """Return ``seconds`` as ``HH:MM:SS.mmm``. Hours past 99 are written in full."""
    hours, minutes, secs, millis = split_milliseconds(seconds)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def parse_clock(text: str) -> float:
    """Return the seconds in ``[[HH:]MM:]SS[.mmm]``.

    Raises:
        ValueError: ``text`` isn't a time, or is one a double can't hold without rounding it.
    """
    parts = text.strip().split(":")
    if (
        len(parts) > 3
        or not all(parts)
        or not all(part.isascii() and part.isdigit() for part in parts[:-1])
        or parts[-1].lstrip()[:1] in ("+", "-")
    ):
        raise ValueError(f"not a time: {shorten(text)}")
    try:
        minutes = 0
        for part in parts[:-1]:
            minutes = minutes * 60 + int(part)
        seconds = seconds_from(minutes * 60, parts[-1])
    except ValueError:
        raise ValueError(f"not a time: {shorten(text)}") from None
    if seconds < 0:
        raise ValueError(f"not a time: {shorten(text)}")
    return seconds

# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import math


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
        ValueError: ``text`` isn't a time.
    """
    parts = text.strip().split(":")
    if len(parts) > 3 or not all(parts):
        raise ValueError(f"not a time: {text!r}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"not a time: {text!r}")
    return seconds

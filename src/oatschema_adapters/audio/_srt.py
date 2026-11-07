# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import datetime
import re
from typing import Any, Literal

import srt

from oatschema_adapters._numbers import MAX_ITEMS, milliseconds_to_seconds
from oatschema_adapters._options import checked
from oatschema_adapters._parsed import ParsedRecord
from oatschema_adapters._validation import check_record, finish_parse

_SPEAKER = re.compile(r"([^:\n]+):(?: +|$)")
_DELIMITER = "[,.:，．。：]"
_TIME = f"([0-9]+){_DELIMITER}([0-9]+){_DELIMITER}([0-9]+)(?:{_DELIMITER}([0-9]*))?"
_TIMING = re.compile(f"{_TIME} *-[ -] *> *{_TIME}")
_INDEX = re.compile(r"-?[0-9]+(?:\.[0-9]*)?\s*")
_TIME_START = re.compile(f"[0-9]+{_DELIMITER}[0-9]+{_DELIMITER}[0-9]+")
_MAX_FRACTION_DIGITS = 3


def _seconds(hours: str, minutes: str, seconds: str, milliseconds: str | None) -> float:
    if milliseconds and len(milliseconds) > _MAX_FRACTION_DIGITS:
        raise ValueError("more than three digits of a second")
    total = (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * 1000 + int(milliseconds or "0")
    return milliseconds_to_seconds(total)


def _times(timing: re.Match[str], number: int) -> tuple[float, float]:
    groups = timing.groups()
    try:
        return _seconds(*groups[:4]), _seconds(*groups[4:])
    except ValueError:
        raise ValueError(f"Failed to parse SRT content: the time on line {number} is out of range") from None


def _index_position(lines: list[str]) -> int | None:
    position = len(lines) - 1
    while position >= 0 and not lines[position].strip():
        position -= 1
    return position if position >= 1 and _INDEX.fullmatch(lines[position]) else None


def _starts_a_subtitle(lines: list[str]) -> bool:
    return _index_position(lines) is not None or (len(lines) >= 2 and lines[-1] == "")


def _without_index(lines: list[str]) -> list[str]:
    position = _index_position(lines)
    return lines if position is None else lines[:position]


def _read_subtitles(content: str) -> list[tuple[float, float, str]]:
    subtitles: list[tuple[float, float, str]] = []
    start = end = 0.0
    lines: list[str] | None = None
    indexed = False
    for number, line in enumerate(content.removeprefix("\ufeff").replace("\r\n", "\n").split("\n"), start=1):
        if lines is None:
            stripped = line.strip()
            if not stripped:
                continue
            timing = _TIMING.match(line if indexed else line.lstrip()) if "\r" not in line else None
            if timing:
                start, end = _times(timing, number)
                lines = []
            elif indexed or not _INDEX.fullmatch(line.lstrip()):
                raise ValueError(f"Failed to parse SRT content: unexpected text on line {number}")
            else:
                indexed = True
            continue
        timing = _TIMING.match(line) if "\r" not in line else None
        if not timing and _TIME_START.match(line) and _starts_a_subtitle(lines):
            raise ValueError(f"Failed to parse SRT content: a bad timing on line {number}")
        if timing and _starts_a_subtitle(lines):
            subtitles.append((start, end, "\n".join(_without_index(lines)).rstrip("\n")))
            if len(subtitles) >= MAX_ITEMS:
                raise ValueError(f"Failed to parse SRT content: more than {MAX_ITEMS} subtitles")
            start, end = _times(timing, number)
            lines = []
        else:
            lines.append(line)
    if lines is not None:
        subtitles.append((start, end, "\n".join(lines).rstrip("\n")))
    elif indexed:
        raise ValueError("Failed to parse SRT content: an index with no subtitle")
    return subtitles


@checked
def to_srt(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
    include_speakers: bool = False,
) -> str:
    """Convert an ``audio-transcription`` record to SubRip (SRT) subtitles, one per segment.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.9.0"``. Defaults to the newest.
        include_speakers: Start each subtitle with its speaker's name, as ``Name: text``.

    Raises:
        ValueError: The record has no segments.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "audio-transcription", validate=validate, version=schema_version)

    segments = record.get("segments", [])
    if not segments:
        raise ValueError("The provided record does not contain any 'segments'.")

    subtitles = []
    for index, segment in enumerate(segments, start=1):
        content = segment["text"].strip()
        if include_speakers:
            speaker = segment.get("speaker")
            if speaker and "name" in speaker:
                content = f"{speaker['name']}: {content}"
        subtitles.append(
            srt.Subtitle(
                index=index,
                start=datetime.timedelta(seconds=segment["start_time"]),
                end=datetime.timedelta(seconds=segment["end_time"]),
                content=content,
            )
        )

    return str(srt.compose(subtitles))


@checked
def from_srt(
    srt_content: str,
    *,
    producer: str = "srt-adapter",
    validate: bool = True,
    schema_version: str | None = None,
    on_bad_number: Literal["drop", "raise"] = "drop",
    include_speakers: bool = False,
) -> ParsedRecord:
    """Parse SubRip (SRT) subtitles into an ``audio-transcription`` record, with one segment per subtitle.

    SRT has nowhere to hold a speaker's id, so with ``include_speakers`` the id is the name. A name containing ``: ``
    is split there.

    Args:
        srt_content: The SRT text.
        producer: The record's ``producer``.
        validate: Check the record's numbers and validate it before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.
        on_bad_number: What ``oatschema.check_numbers`` does with a bad number in an optional property: ``"drop"``
            removes it and reports it in the result's ``dropped``, and ``"raise"`` rejects the record.
        include_speakers: Read a ``Name: `` at the start of a subtitle, as ``to_srt`` writes it, as the segment's
            speaker. It's off by default because ordinary text can start that way.

    Raises:
        ValueError: The content isn't valid SRT, has more than 100,000 subtitles, or has a bad timing, a time with more than three
            digits of a second, or one that a double can't hold without rounding it.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    segments = []
    texts = []
    for start, end, content in _read_subtitles(srt_content):
        text = content.replace("\n", " ").strip()
        segment: dict[str, Any] = {"text": text, "start_time": start, "end_time": end}
        match = _SPEAKER.match(text) if include_speakers else None
        if match:
            name = match.group(1).strip()
            segment["text"] = text = text[match.end() :]
            segment["speaker"] = {"id": name, "name": name}
        segments.append(segment)
        texts.append(text)

    record = {"producer": producer, "text": " ".join(texts), "segments": segments}
    return finish_parse(
        record, "audio-transcription", validate=validate, version=schema_version, on_bad_number=on_bad_number
    )

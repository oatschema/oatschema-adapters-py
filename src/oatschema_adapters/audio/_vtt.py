# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import html
import re
from typing import Any, Literal

import webvtt

from oatschema_adapters._numbers import MAX_ITEMS
from oatschema_adapters._options import checked, shorten
from oatschema_adapters._parsed import ParsedRecord
from oatschema_adapters._validation import check_record, finish_parse
from oatschema_adapters.audio._time import clock, parse_clock

_COMMENT = re.compile(r"(?:NOTE|STYLE|REGION)(?:[ \t]|$)")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_STAMP = r"(?:[0-9]+:)?[0-9]{1,2}:[0-9]{1,2}\.[0-9]{1,3}"
_TIMING = re.compile(rf"\s*{_STAMP}\s*-->\s*{_STAMP}(?:\s.*)?")


def _timing_lines(content: str) -> int:
    lines = _LINE_BREAK.split(content.removeprefix("\ufeff"))
    timings = 0
    block: list[str] = []
    for number, line in enumerate([*lines, ""]):
        if line.strip():
            block.append(line)
            continue
        if block and not _COMMENT.match(block[0]):
            is_header = block[0].startswith("WEBVTT")
            found = 0
            for text in block[1:] if is_header else block:
                if _TIMING.fullmatch(text):
                    found += 1
                elif "-->" in text:
                    raise ValueError(f"Failed to parse WebVTT content: a bad timing before line {number + 1}")
            if not found and not is_header:
                raise ValueError(f"Failed to parse WebVTT content: the block before line {number + 1} has no timing")
            timings += found
        block = []
    return timings


def _cue_text(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return html.escape("\n".join(lines), quote=False)


def _voice(name: str) -> str:
    return html.escape(" ".join(name.split()), quote=False)


@checked
def to_vtt(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
    include_speakers: bool = False,
) -> str:
    """Convert an ``audio-transcription`` record to WebVTT captions, one per segment.

    Times are rounded to the nearest millisecond. ``&``, ``<`` and ``>`` in text and speaker names are written as
    character references, and blank lines in text are removed, so no text can end a caption or start another.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.9.0"``. Defaults to the newest.
        include_speakers: Mark each caption with its speaker's name, as a ``<v Name>`` voice span.

    Raises:
        ValueError: The record has no segments.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "audio-transcription", validate=validate, version=schema_version)

    segments = record.get("segments", [])
    if not segments:
        raise ValueError("The provided record does not contain any 'segments'.")

    vtt = webvtt.WebVTT()
    for segment in segments:
        caption = webvtt.Caption(
            start=clock(segment["start_time"]),
            end=clock(segment["end_time"]),
            text=_cue_text(segment["text"]),
        )
        if include_speakers:
            speaker = segment.get("speaker")
            if speaker and "name" in speaker:
                caption.text = f"<v {_voice(speaker['name'])}>{caption.text}"
        vtt.captions.append(caption)

    return str(vtt.content)


@checked
def from_vtt(
    vtt_content: str,
    *,
    producer: str = "vtt-adapter",
    validate: bool = True,
    schema_version: str | None = None,
    on_bad_number: Literal["drop", "raise"] = "drop",
) -> ParsedRecord:
    """Parse WebVTT captions into an ``audio-transcription`` record, with one segment per caption.

    A caption's voice span (``<v Name>``) becomes the segment's speaker. WebVTT has nowhere to hold a speaker's id,
    so the id is the name. Character references such as ``&amp;`` are decoded.

    Args:
        vtt_content: The WebVTT text.
        producer: The record's ``producer``.
        validate: Check the record's numbers and validate it before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.
        on_bad_number: What ``oatschema.check_numbers`` does with a bad number in an optional property: ``"drop"``
            removes it and reports it in the result's ``dropped``, and ``"raise"`` rejects the record.

    Raises:
        ValueError: The content isn't valid WebVTT, has more than 100,000 captions, has a timing it can't read, or
            has a block with no timing, other than the header and ``NOTE``, ``STYLE`` and ``REGION`` blocks.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    timings = _timing_lines(vtt_content)
    if timings > MAX_ITEMS:
        raise ValueError(f"Failed to parse WebVTT content: more than {MAX_ITEMS} captions")

    problem = None
    try:
        vtt = webvtt.from_string(vtt_content)
    except Exception as error:
        problem = shorten(str(error), 200)
    if problem:
        raise ValueError(f"Failed to parse WebVTT content: {problem}")

    if len(vtt.captions) != timings:
        raise ValueError("Failed to parse WebVTT content: its captions don't match its timing lines")

    segments = []
    texts = []
    for caption in vtt.captions:
        text = html.unescape(caption.text.replace("\n", " ").strip())
        segment: dict[str, Any] = {
            "text": text,
            "start_time": parse_clock(caption.start),
            "end_time": parse_clock(caption.end),
        }
        voice = getattr(caption, "voice", None)
        if voice:
            name = html.unescape(voice.strip())
            segment["speaker"] = {"id": name, "name": name}
        segments.append(segment)
        texts.append(text)

    record = {"producer": producer, "text": " ".join(texts), "segments": segments}
    return finish_parse(
        record, "audio-transcription", validate=validate, version=schema_version, on_bad_number=on_bad_number
    )

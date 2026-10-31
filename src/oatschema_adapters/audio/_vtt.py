# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import html
from typing import Any

import webvtt

from oatschema_adapters._options import checked
from oatschema_adapters._validation import check_record, validate_record
from oatschema_adapters.audio._time import clock, parse_clock


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
        schema_version: The schema version to validate against, such as ``"0.8.0"``. Defaults to the newest.
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
) -> dict[str, Any]:
    """Parse WebVTT captions into an ``audio-transcription`` record, with one segment per caption.

    A caption's voice span (``<v Name>``) becomes the segment's speaker. Character references such as ``&amp;`` are
    decoded.

    Args:
        vtt_content: The WebVTT text.
        producer: The record's ``producer``.
        validate: Validate the record before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.

    Raises:
        ValueError: The content isn't valid WebVTT.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    try:
        vtt = webvtt.from_string(vtt_content)
    except Exception as error:
        raise ValueError(f"Failed to parse WebVTT content: {error}") from error

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
    if validate:
        validate_record(record, "audio-transcription", version=schema_version)
    return record

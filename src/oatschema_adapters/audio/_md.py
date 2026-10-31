# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import re
from typing import Any

from oatschema_adapters._frontmatter import frontmatter
from oatschema_adapters._options import checked
from oatschema_adapters._validation import check_record, validate_record
from oatschema_adapters.audio._time import parse_clock, split_milliseconds

_FRONTMATTER_KEYS = ("producer", "language", "duration", "score_explanation", "track_id")
_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
_SEGMENT = re.compile(r"^\*\*\[([\d:.]+)\s*-\s*([\d:.]+)\]\*\*(?:\s*\*\*([^:]+):\*\*)?\s+(.*)", re.IGNORECASE)
_EVENTS = re.compile(r"^\*\[(.*)\]\*$")


def _format_time(seconds: float, *, include_milliseconds: bool) -> str:
    if include_milliseconds:
        hours, minutes, secs, millis = split_milliseconds(seconds)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
        return f"{minutes:02d}:{secs:02d}.{millis:03d}"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
    return f"{int(m):02d}:{int(s):02d}"


@checked
def to_md(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
    include_timestamps: bool = True,
    include_milliseconds: bool = False,
    include_speakers: bool = False,
    include_frontmatter: bool = True,
    low_confidence_threshold: float = 0.80,
) -> str:
    """Convert an ``audio-transcription`` record to Markdown, with one paragraph per segment.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.8.0"``. Defaults to the newest.
        include_timestamps: Start each paragraph with the segment's start and end time.
        include_milliseconds: Show milliseconds in the times, rounded to the nearest millisecond.
        include_speakers: Show each segment's speaker name.
        include_frontmatter: Start with YAML frontmatter holding the record's producer, language, duration,
            score explanation, track id and attributes.
        low_confidence_threshold: Mark segments whose score is below this as low-confidence quotes.

    Raises:
        ValueError: The record has no text and no segments.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "audio-transcription", validate=validate, version=schema_version)

    output = []
    if include_frontmatter:
        header = frontmatter(record, _FRONTMATTER_KEYS)
        if header is not None:
            output.append(header)

    segments = record.get("segments", [])
    if not segments:
        text = record.get("text", "").strip()
        if not text:
            raise ValueError("The provided record contains no 'text' or 'segments'.")
        output.append("# Transcription")
        output.append(text)
        return "\n\n".join(output)

    output.append("# Transcription")

    for segment in segments:
        line_parts = []
        if include_timestamps:
            start = _format_time(segment["start_time"], include_milliseconds=include_milliseconds)
            end = _format_time(segment["end_time"], include_milliseconds=include_milliseconds)
            line_parts.append(f"**[{start} - {end}]**")
        if include_speakers:
            speaker_name = segment.get("speaker", {}).get("name")
            if speaker_name:
                line_parts.append(f"**{speaker_name}:**")

        prefix = " ".join(line_parts)
        text = segment.get("text", "").strip()
        score = segment.get("score")
        events = segment.get("events", [])

        if events:
            output.append(f"> *[{', '.join(events)}]*")
        if not text:
            continue

        line = f"{prefix} {text}" if prefix else text
        if score is not None and score < low_confidence_threshold:
            output.append(f"> ⚠️ **Low Confidence Read ({score:.2f})**:\n> {line}")
        else:
            output.append(line)

    return "\n\n".join(output)


@checked
def from_md(
    md_content: str,
    *,
    producer: str = "md-adapter",
    validate: bool = True,
    schema_version: str | None = None,
) -> dict[str, Any]:
    """Parse Markdown written by ``to_md`` back into an ``audio-transcription`` record.

    Markdown loses information, so this reads only the layout ``to_md`` writes. Event lines (``> *[music]*``) become
    the ``events`` of the segment that follows them.

    Args:
        md_content: The Markdown text.
        producer: The record's ``producer``.
        validate: Validate the record before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.

    Raises:
        ValueError: The content is empty.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    if not md_content.strip():
        raise ValueError("Provided Markdown content is empty.")

    content = _FRONTMATTER.sub("", md_content.replace("\r\n", "\n"), count=1).strip()

    segments: list[dict[str, Any]] = []
    texts = []
    pending_events: list[str] = []

    def add(segment: dict[str, Any]) -> None:
        if pending_events:
            segment["events"] = list(pending_events)
            pending_events.clear()
        segments.append(segment)

    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("> ⚠️"):
            continue
        line = re.sub(r"^>\s*", "", line).strip()

        event_match = _EVENTS.match(line)
        if event_match:
            pending_events.extend(event.strip() for event in event_match.group(1).split(","))
            continue

        match = _SEGMENT.match(line)
        if match:
            start, end, speaker, text = match.groups()
            segment: dict[str, Any] = {
                "start_time": parse_clock(start),
                "end_time": parse_clock(end),
                "text": text.strip(),
            }
            if speaker:
                segment["speaker"] = {"id": speaker.strip(), "name": speaker.strip()}
            add(segment)
            texts.append(text.strip())
        else:
            text = line.replace("**", "").strip()
            add({"start_time": 0.0, "end_time": 0.0, "text": text})
            texts.append(text)

    if pending_events:
        segments.append({"start_time": 0.0, "end_time": 0.0, "text": "", "events": list(pending_events)})

    record = {"producer": producer, "text": " ".join(t for t in texts if t), "segments": segments}
    if validate:
        validate_record(record, "audio-transcription", version=schema_version)
    return record

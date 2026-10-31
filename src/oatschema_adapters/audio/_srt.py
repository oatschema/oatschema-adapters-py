# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import datetime
from typing import Any

import srt

from oatschema_adapters._options import checked
from oatschema_adapters._validation import check_record, validate_record


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
        schema_version: The schema version to validate against, such as ``"0.8.0"``. Defaults to the newest.
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
) -> dict[str, Any]:
    """Parse SubRip (SRT) subtitles into an ``audio-transcription`` record, with one segment per subtitle.

    Args:
        srt_content: The SRT text.
        producer: The record's ``producer``.
        validate: Validate the record before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.

    Raises:
        ValueError: The content isn't valid SRT.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    try:
        subtitles = list(srt.parse(srt_content))
    except srt.SRTParseError as error:
        raise ValueError(f"Failed to parse SRT content: {error}") from error

    segments = []
    texts = []
    for subtitle in subtitles:
        text = subtitle.content.replace("\n", " ").strip()
        segments.append(
            {"text": text, "start_time": subtitle.start.total_seconds(), "end_time": subtitle.end.total_seconds()}
        )
        texts.append(text)

    record = {"producer": producer, "text": " ".join(texts), "segments": segments}
    if validate:
        validate_record(record, "audio-transcription", version=schema_version)
    return record

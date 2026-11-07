# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Literal

from oatschema_adapters import _tsv
from oatschema_adapters._numbers import parse_number
from oatschema_adapters._options import checked, shorten
from oatschema_adapters._parsed import ParsedRecord
from oatschema_adapters._validation import check_record, finish_parse

_COLUMNS = ("start_time", "end_time", "text", "speaker", "speaker_id")


@checked
def to_tsv(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
    include_speakers: bool = False,
) -> str:
    """Convert an ``audio-transcription`` record to a tab-separated table, one row per segment.

    The columns are ``start_time``, ``end_time`` and ``text``, then ``speaker`` (the speaker's name) if
    ``include_speakers`` is true, and ``speaker_id`` if a speaker's id differs from its name. A cell that a
    spreadsheet would run as a formula starts with ``'``; ``from_tsv`` removes it. Times are written to the
    millisecond. Excel keeps only 15 significant digits of a number, so opening and saving the table there can change
    a long one.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.9.0"``. Defaults to the newest.
        include_speakers: Add a ``speaker`` column.

    Raises:
        ValueError: The record has no segments.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "audio-transcription", validate=validate, version=schema_version)

    segments = record.get("segments", [])
    if not segments:
        raise ValueError("The provided record does not contain any 'segments'.")

    header = ["start_time", "end_time", "text"]
    speakers = [segment.get("speaker") or {} for segment in segments]
    include_ids = include_speakers and any(speaker and speaker.get("id") != speaker.get("name") for speaker in speakers)
    if include_speakers:
        header.append("speaker")
    if include_ids:
        header.append("speaker_id")

    rows: list[list[object]] = []
    for segment, speaker in zip(segments, speakers, strict=True):
        row: list[object] = [
            f"{segment['start_time']:.3f}",
            f"{segment['end_time']:.3f}",
            segment["text"].replace("\t", " ").strip(),
        ]
        if include_speakers:
            row.append(speaker.get("name", ""))
        if include_ids:
            row.append(speaker.get("id", ""))
        rows.append(row)

    return _tsv.write(header, rows)


@checked
def from_tsv(
    tsv_content: str,
    *,
    producer: str = "tsv-adapter",
    validate: bool = True,
    schema_version: str | None = None,
    on_bad_number: Literal["drop", "raise"] = "drop",
) -> ParsedRecord:
    """Parse a tab-separated table into an ``audio-transcription`` record, one segment per row.

    The table needs ``start_time`` and ``text`` columns, and may have ``end_time``, ``speaker`` and ``speaker_id``.
    With no ``speaker_id``, a speaker's name is also used as its id. A leading ``'`` that ``to_tsv`` added to stop a
    formula running is removed.

    Args:
        tsv_content: The table.
        producer: The record's ``producer``.
        validate: Check the record's numbers and validate it before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.
        on_bad_number: What ``oatschema.check_numbers`` does with a bad number in an optional property: ``"drop"``
            removes it and reports it in the result's ``dropped``, and ``"raise"`` rejects the record.

    Raises:
        ValueError: The content is empty, lacks a required column, or has a time that isn't a number.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    header, rows = _tsv.read(tsv_content, _COLUMNS)
    if "start_time" not in header or "text" not in header:
        raise ValueError("TSV must contain at least 'start_time' and 'text' columns.")

    segments = []
    texts = []
    for row in rows:
        text = row["text"].strip()
        try:
            start = parse_number(row["start_time"])
            end = parse_number(row["end_time"]) if row.get("end_time") else start
        except ValueError as error:
            raise ValueError(f"TSV times must be numbers: {shorten(str(error), 200)}") from None
        segment: dict[str, Any] = {"start_time": start, "end_time": end, "text": text}
        name = (row.get("speaker") or "").strip()
        speaker_id = (row.get("speaker_id") or "").strip() or name
        if speaker_id:
            segment["speaker"] = {"id": speaker_id, "name": name} if name else {"id": speaker_id}
        segments.append(segment)
        texts.append(text)

    record = {"producer": producer, "text": " ".join(texts), "segments": segments}
    return finish_parse(
        record, "audio-transcription", validate=validate, version=schema_version, on_bad_number=on_bad_number
    )

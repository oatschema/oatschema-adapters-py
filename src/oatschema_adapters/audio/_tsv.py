# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from oatschema_adapters import _tsv
from oatschema_adapters._options import checked
from oatschema_adapters._validation import check_record, validate_record


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
    ``include_speakers`` is true. A cell that a spreadsheet would run as a formula starts with ``'``;
    ``from_tsv`` removes it.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.8.0"``. Defaults to the newest.
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
    if include_speakers:
        header.append("speaker")

    rows: list[list[object]] = []
    for segment in segments:
        row: list[object] = [
            f"{segment['start_time']:.3f}",
            f"{segment['end_time']:.3f}",
            segment["text"].replace("\t", " ").strip(),
        ]
        if include_speakers:
            row.append((segment.get("speaker") or {}).get("name", ""))
        rows.append(row)

    return _tsv.write(header, rows)


@checked
def from_tsv(
    tsv_content: str,
    *,
    producer: str = "tsv-adapter",
    validate: bool = True,
    schema_version: str | None = None,
) -> dict[str, Any]:
    """Parse a tab-separated table into an ``audio-transcription`` record, one segment per row.

    The table needs ``start_time`` and ``text`` columns, and may have ``end_time`` and ``speaker``. A speaker's name
    is also used as its id. A leading ``'`` that ``to_tsv`` added to stop a formula running is removed.

    Args:
        tsv_content: The table.
        producer: The record's ``producer``.
        validate: Validate the record before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.

    Raises:
        ValueError: The content is empty, lacks a required column, or has a time that isn't a number.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    header, rows = _tsv.read(tsv_content)
    if "start_time" not in header or "text" not in header:
        raise ValueError("TSV must contain at least 'start_time' and 'text' columns.")

    segments = []
    texts = []
    for row in rows:
        text = row["text"].strip()
        try:
            start = float(row["start_time"])
            end = float(row["end_time"]) if row.get("end_time") else start
        except ValueError as error:
            raise ValueError(f"TSV times must be numbers: {error}") from None
        segment: dict[str, Any] = {"start_time": start, "end_time": end, "text": text}
        speaker = (row.get("speaker") or "").strip()
        if speaker:
            segment["speaker"] = {"id": speaker, "name": speaker}
        segments.append(segment)
        texts.append(text)

    record = {"producer": producer, "text": " ".join(texts), "segments": segments}
    if validate:
        validate_record(record, "audio-transcription", version=schema_version)
    return record

# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from oatschema_adapters._options import checked
from oatschema_adapters._validation import check_record, validate_record


@checked
def to_txt(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
) -> str:
    """Return the text of an ``audio-transcription`` record: its ``text``, or else its segments' text joined.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.8.0"``. Defaults to the newest.

    Raises:
        ValueError: The record has no text and no segments.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "audio-transcription", validate=validate, version=schema_version)

    text = record.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    segments = record.get("segments", [])
    if not segments:
        raise ValueError("The provided record contains no 'text' or 'segments'.")

    return " ".join(segment["text"].strip() for segment in segments)


@checked
def from_txt(
    txt_content: str,
    *,
    producer: str = "txt-adapter",
    validate: bool = True,
    schema_version: str | None = None,
) -> dict[str, Any]:
    """Wrap plain text in an ``audio-transcription`` record, as its ``text``.

    Args:
        txt_content: The text.
        producer: The record's ``producer``.
        validate: Validate the record before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.

    Raises:
        ValueError: The text is empty.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    if not txt_content.strip():
        raise ValueError("Provided text content is empty.")

    record = {"producer": producer, "text": txt_content.strip()}
    if validate:
        validate_record(record, "audio-transcription", version=schema_version)
    return record

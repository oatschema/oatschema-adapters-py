# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from oatschema_adapters._options import checked
from oatschema_adapters._validation import check_record, validate_record
from oatschema_adapters.document._layout import (
    DEFAULT_COLUMN_JUMP,
    DEFAULT_LINE_TOLERANCE,
    DEFAULT_PARAGRAPH_MARGIN,
    extract_spatial_pages,
)


@checked
def to_txt(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
    strict: bool = False,
    line_tolerance: float = DEFAULT_LINE_TOLERANCE,
    paragraph_margin: float = DEFAULT_PARAGRAPH_MARGIN,
    column_jump: float = DEFAULT_COLUMN_JUMP,
    scale: float | None = None,
) -> str:
    """Convert a ``document-extraction`` record to plain text, in paragraphs, with a divider between pages.

    Blocks are joined into lines and paragraphs by their vertical position, in the record's order. The distances
    below are in thousandths of the page height, or in the record's unit for a ``px`` or ``pt`` record with no
    page height.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.8.0"``. Defaults to the newest.
        strict: Keep each line of a paragraph on its own line, and don't join hyphenated words.
        line_tolerance: The vertical distance within which blocks are on the same line.
        paragraph_margin: The vertical gap that starts a new paragraph.
        column_jump: The upward jump (negative) that starts a new paragraph, as at the top of a new column.
        scale: Multiply the three distances by this instead of the scale derived from the record's unit.

    Raises:
        ValueError: The record has no blocks.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "document-extraction", validate=validate, version=schema_version)

    if not record.get("blocks"):
        raise ValueError("The provided record contains no 'blocks'.")

    pages = extract_spatial_pages(
        record,
        strict=strict,
        line_tolerance=line_tolerance,
        paragraph_margin=paragraph_margin,
        column_jump=column_jump,
        scale=scale,
    )
    output = []
    for i, (page_num, paragraphs) in enumerate(pages):
        if i > 0:
            output.append(f"--- Page {page_num} ---")
        for para in paragraphs:
            text = para.get("text", "").strip()
            if text:
                output.append(text)

    return "\n\n".join(output)


@checked
def from_txt(
    txt_content: str,
    *,
    producer: str = "txt-adapter",
    validate: bool = True,
    schema_version: str | None = None,
) -> dict[str, Any]:
    """Wrap plain text in a ``document-extraction`` record, as a single text block.

    Args:
        txt_content: The text.
        producer: The record's ``producer``.
        validate: Validate the record before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.

    Raises:
        ValueError: The text is empty.
        oatschema.ValidationError: The record doesn't conform to the schema, for example because the text is longer
            than a block allows.
    """
    if not txt_content.strip():
        raise ValueError("Provided text content is empty.")

    record = {
        "producer": producer,
        "extraction_type": "text",
        "blocks": [{"block_type": "text", "text": txt_content.strip()}],
    }
    if validate:
        validate_record(record, "document-extraction", version=schema_version)
    return record

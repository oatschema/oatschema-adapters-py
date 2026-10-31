# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Literal

from oatschema_adapters import _tsv
from oatschema_adapters._options import checked
from oatschema_adapters._validation import check_record, validate_record

_HEADER = ["page_number", "block_type", "x", "y", "width", "height", "text"]
_TEXT_TYPES = ("text", "line")


@checked
def to_tsv(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
) -> str:
    """Convert a ``document-extraction`` record to a tab-separated table, one row per block.

    The columns are ``page_number``, ``block_type``, the box's ``x``, ``y``, ``width`` and ``height``, and ``text``.
    Blocks with only a polygon or multi-polygon have no box, so ``from_tsv`` can't read them back into valid blocks.
    A cell that a spreadsheet would run as a formula
    starts with ``'``; ``from_tsv`` removes it.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.8.0"``. Defaults to the newest.

    Raises:
        ValueError: The record has no blocks.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "document-extraction", validate=validate, version=schema_version)

    blocks = record.get("blocks", [])
    if not blocks:
        raise ValueError("The provided record contains no 'blocks'.")

    rows: list[list[object]] = []
    for block in blocks:
        box = block.get("box", {})
        rows.append(
            [
                block.get("page_number", ""),
                block.get("block_type", "text"),
                box.get("x", ""),
                box.get("y", ""),
                box.get("width", ""),
                box.get("height", ""),
                block.get("text", ""),
            ]
        )
    return _tsv.write(_HEADER, rows)


@checked
def from_tsv(
    tsv_content: str,
    *,
    producer: str = "tsv-adapter",
    validate: bool = True,
    schema_version: str | None = None,
    unit: Literal["px", "pt", "normalized", "per_mille"] = "px",
) -> dict[str, Any]:
    """Parse a tab-separated table into a ``document-extraction`` record, one block per row.

    The table needs a ``text`` column, and may have ``page_number``, ``block_type``, ``x``, ``y``, ``width`` and
    ``height``. An empty ``text`` cell is an empty text for ``text`` and ``line`` blocks, and no text for other
    blocks. A leading ``'`` that ``to_tsv`` added to stop a formula running is removed.

    Args:
        tsv_content: The table.
        producer: The record's ``producer``.
        validate: Validate the record before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.
        unit: The unit of the coordinates.

    Raises:
        ValueError: The content is empty or has no ``text`` column.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    header, rows = _tsv.read(tsv_content)
    if "text" not in header:
        raise ValueError("TSV must contain at least a 'text' column.")

    blocks = []
    for row in rows:
        block_type = row.get("block_type") or "text"
        block: dict[str, Any] = {"block_type": block_type}
        text = row.get("text", "")
        if text or block_type in _TEXT_TYPES:
            block["text"] = text

        page = row.get("page_number", "")
        if page.isascii() and page.isdigit():
            block["page_number"] = int(page)

        box = {}
        for dim in ("x", "y", "width", "height"):
            value = row.get(dim)
            if value:
                try:
                    box[dim] = float(value)
                except ValueError:
                    pass
        if box:
            block["box"] = box

        blocks.append(block)

    record = {"producer": producer, "extraction_type": "mixed", "unit": unit, "blocks": blocks}
    if validate:
        validate_record(record, "document-extraction", version=schema_version)
    return record

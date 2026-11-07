# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import json
from typing import Any, Literal

from oatschema_adapters import _tsv
from oatschema_adapters._numbers import load_json, parse_number
from oatschema_adapters._options import checked, shorten
from oatschema_adapters._parsed import ParsedRecord
from oatschema_adapters._validation import check_record, finish_parse
from oatschema_adapters.document._layout import _get_bounding_box

_HEADER = ["page_number", "block_type", "x", "y", "width", "height", "text"]
_POLYGON = "polygon"
_TEXT_TYPES = ("text", "line")


def _pairs(points: list[dict[str, Any]]) -> list[list[Any]]:
    return [[point["x"], point["y"]] for point in points]


def _geometry(block: dict[str, Any]) -> dict[str, Any]:
    if "multi_polygon" in block and (block.get("block_type") == "multi_polygon" or "polygon" not in block):
        return {"multi_polygon": block["multi_polygon"]}
    if "polygon" in block:
        return {"polygon": block["polygon"]}
    return {}


def _polygon_cell(block: dict[str, Any]) -> str:
    geometry = _geometry(block)
    try:
        if "polygon" in geometry:
            cell: list[Any] = _pairs(geometry["polygon"])
        elif "multi_polygon" in geometry:
            cell = [_pairs(polygon) for polygon in geometry["multi_polygon"]]
        else:
            return ""
    except (KeyError, TypeError):
        return ""
    return json.dumps(cell, separators=(",", ":"))


def _bounding_box(geometry: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return _get_bounding_box(geometry)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _exported_box(block: dict[str, Any]) -> dict[str, Any]:
    if "box" in block:
        box: dict[str, Any] = block["box"]
        return box
    return _bounding_box(_geometry(block)) or {}


def _is_pair(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(number, (int, float)) and not isinstance(number, bool) for number in value)
    )


def _read_points(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(_is_pair(pair) for pair in value):
        raise ValueError("A TSV polygon must be a JSON list of [x, y] pairs, or a list of such lists.")
    return [{"x": x, "y": y} for x, y in value]


def _read_geometry(cell: str) -> dict[str, Any]:
    value = load_json(cell)
    if isinstance(value, list) and value and isinstance(value[0], list) and value[0] and isinstance(value[0][0], list):
        return {"multi_polygon": [_read_points(polygon) for polygon in value]}
    return {"polygon": _read_points(value)}


@checked
def to_tsv(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
) -> str:
    """Convert a ``document-extraction`` record to a tab-separated table, one row per block.

    The columns are ``page_number``, ``block_type``, the box's ``x``, ``y``, ``width`` and ``height``, and ``text``.
    If any block has a polygon or multi-polygon, there is a last ``polygon`` column of compact JSON: ``[[x,y],...]``,
    or one level deeper for a multi-polygon. The box columns of such a block with no box hold its bounding box. A
    block with both a polygon and a multi-polygon keeps the multi-polygon if its ``block_type`` is
    ``multi_polygon``, and the polygon otherwise. A cell that a spreadsheet would run as a
    formula starts with ``'``; ``from_tsv`` removes it.

    Excel keeps only 15 significant digits of a number and at most 32,767 characters in a cell, so opening and saving
    the table there can change a long number or cut a large polygon. The table holds no ``id``, ``line_number``,
    ``score`` or ``attributes``.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.9.0"``. Defaults to the newest.

    Raises:
        ValueError: The record has no blocks.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "document-extraction", validate=validate, version=schema_version)

    blocks = record.get("blocks", [])
    if not blocks:
        raise ValueError("The provided record contains no 'blocks'.")

    polygons = [_polygon_cell(block) for block in blocks]
    include_polygons = any(polygons)

    rows: list[list[object]] = []
    for block, polygon in zip(blocks, polygons, strict=True):
        box = _exported_box(block)
        row: list[object] = [
            block.get("page_number", ""),
            block.get("block_type", "text"),
            box.get("x", ""),
            box.get("y", ""),
            box.get("width", ""),
            box.get("height", ""),
            block.get("text", ""),
        ]
        if include_polygons:
            row.append(polygon)
        rows.append(row)
    return _tsv.write([*_HEADER, _POLYGON] if include_polygons else _HEADER, rows)


@checked
def from_tsv(
    tsv_content: str,
    *,
    producer: str = "tsv-adapter",
    validate: bool = True,
    schema_version: str | None = None,
    unit: Literal["px", "pt", "normalized", "per_mille"] = "px",
    on_bad_number: Literal["drop", "raise"] = "drop",
) -> ParsedRecord:
    """Parse a tab-separated table into a ``document-extraction`` record, one block per row.

    The table needs a ``text`` column, and may have ``page_number``, ``block_type``, ``x``, ``y``, ``width``,
    ``height`` and ``polygon``. An empty ``text`` cell is an empty text for ``text`` and ``line`` blocks, and no text
    for other blocks. A leading ``'`` that ``to_tsv`` added to stop a formula running is removed. A block with a
    polygon gets a box only if the box columns differ from the polygon's bounding box.

    Args:
        tsv_content: The table.
        producer: The record's ``producer``.
        validate: Check the record's numbers and validate it before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.
        unit: The unit of the coordinates.
        on_bad_number: What ``oatschema.check_numbers`` does with a bad number in an optional property: ``"drop"``
            removes it and reports it in the result's ``dropped``, and ``"raise"`` rejects the record.

    Raises:
        ValueError: The content is empty or has no ``text`` column, or a page number, box or polygon cell isn't a
            usable number or polygon.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    header, rows = _tsv.read(tsv_content, (*_HEADER, _POLYGON))
    if "text" not in header:
        raise ValueError("TSV must contain at least a 'text' column.")

    blocks = []
    for row in rows:
        block_type = row.get("block_type") or "text"
        block: dict[str, Any] = {"block_type": block_type}
        text = row.get("text", "")
        if text or block_type in _TEXT_TYPES:
            block["text"] = text

        page = row.get("page_number", "").strip()
        if page:
            if not (page.isascii() and page.isdigit()):
                raise ValueError(f"A TSV page number must be a whole number, not {shorten(page)}.")
            block["page_number"] = int(page)

        box = {}
        for dim in ("x", "y", "width", "height"):
            value = row.get(dim)
            if value:
                box[dim] = parse_number(value)

        polygon = row.get(_POLYGON)
        geometry = _read_geometry(polygon) if polygon else {}
        if box and box != _bounding_box(geometry):
            block["box"] = box
        block.update(geometry)

        blocks.append(block)

    record = {"producer": producer, "extraction_type": "mixed", "unit": unit, "blocks": blocks}
    return finish_parse(
        record, "document-extraction", validate=validate, version=schema_version, on_bad_number=on_bad_number
    )

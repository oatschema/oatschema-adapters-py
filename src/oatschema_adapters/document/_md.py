# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from oatschema_adapters._frontmatter import frontmatter
from oatschema_adapters._options import checked
from oatschema_adapters._validation import check_record
from oatschema_adapters.document._layout import (
    DEFAULT_COLUMN_JUMP,
    DEFAULT_LINE_TOLERANCE,
    DEFAULT_PARAGRAPH_MARGIN,
    extract_spatial_pages,
)

_FRONTMATTER_KEYS = ("producer", "extraction_type", "unit", "score_explanation")


@checked
def to_md(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
    strict: bool = False,
    include_frontmatter: bool = True,
    low_confidence_threshold: float = 0.80,
    line_tolerance: float = DEFAULT_LINE_TOLERANCE,
    paragraph_margin: float = DEFAULT_PARAGRAPH_MARGIN,
    column_jump: float = DEFAULT_COLUMN_JUMP,
    scale: float | None = None,
) -> str:
    """Convert a ``document-extraction`` record to Markdown, with a section per page.

    Blocks are joined into paragraphs as for ``to_txt``. A ``visual_class`` attribute of ``title`` or ``h1``,
    ``h2``, or ``h3`` or ``heading`` makes a paragraph a heading. Blocks with no text are shown as placeholders
    with their coordinates.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.8.0"``. Defaults to the newest.
        strict: Keep each line of a paragraph on its own line, and don't join hyphenated words.
        include_frontmatter: Start with YAML frontmatter holding the record's producer, extraction type, unit,
            score explanation and attributes.
        low_confidence_threshold: Mark paragraphs whose lowest score is below this as low-confidence quotes.
        line_tolerance: As for ``to_txt``.
        paragraph_margin: As for ``to_txt``.
        column_jump: As for ``to_txt``.
        scale: As for ``to_txt``.

    Raises:
        ValueError: The record has no blocks.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "document-extraction", validate=validate, version=schema_version)

    if not record.get("blocks"):
        raise ValueError("The provided record contains no 'blocks'.")

    output = []
    if include_frontmatter:
        header = frontmatter(record, _FRONTMATTER_KEYS)
        if header is not None:
            output.append(header)

    pages = extract_spatial_pages(
        record,
        strict=strict,
        line_tolerance=line_tolerance,
        paragraph_margin=paragraph_margin,
        column_jump=column_jump,
        scale=scale,
    )

    for page_num, paragraphs in pages:
        output.append(f"## Page {page_num}")

        for para in paragraphs:
            text = para.get("text", "").strip()
            b_type = para.get("block_type", "text")
            attrs = para.get("attributes", {})
            score = para.get("score")

            if not text and b_type != "text":
                box = para.get("box")
                if box:
                    coords = (
                        f"x:{round(box['x'])}, y:{round(box['y'])}, w:{round(box['width'])}, h:{round(box['height'])}"
                    )
                    output.append(f"> *[{str(b_type).capitalize()} at {coords}]*")
                continue

            if not text:
                continue

            visual_class = str(attrs.get("visual_class", "")).lower()
            if visual_class in ("title", "h1"):
                text = f"# {text}"
            elif visual_class == "h2":
                text = f"## {text}"
            elif visual_class in ("h3", "heading"):
                text = f"### {text}"

            if score is not None and score < low_confidence_threshold:
                text = f"> ⚠️ **Low Confidence Read ({score:.2f})**:\n> {text}"

            output.append(text)

    return "\n\n".join(output)

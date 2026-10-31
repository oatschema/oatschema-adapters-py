# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import html
import os
import re
from typing import Any, Literal

from oatschema_adapters._options import checked
from oatschema_adapters._validation import check_record
from oatschema_adapters.document._layout import (
    DEFAULT_COLUMN_JUMP,
    DEFAULT_LINE_TOLERANCE,
    DEFAULT_PARAGRAPH_MARGIN,
    extract_spatial_pages,
    get_page_dim,
    xy_cut,
)
from oatschema_adapters.document._render import format_css_coords, render_tree
from oatschema_adapters.document._styles import CORE_CSS, THEMES

_STYLE_END_TAG = re.compile(r"</(?=style)", re.IGNORECASE)


def _read_stylesheet(path: str | os.PathLike[str]) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return _STYLE_END_TAG.sub(r"<\\/", f.read())


def _resolve_theme_css(style: str, style_path: str | os.PathLike[str] | None) -> str:
    if style_path is not None:
        if style != "default":
            raise ValueError("Pass either 'style' or 'style_path', not both.")
        return _read_stylesheet(style_path)

    theme_css = THEMES.get(style)
    if theme_css is None:
        raise ValueError(
            f"Unknown style {style!r}. Use one of the themes 'default', 'dark' or 'none', "
            "or pass a stylesheet file as 'style_path'."
        )
    return theme_css


def _footer_div(footer: str) -> str:
    return f'  <div class="document-footer">\n    {html.escape(str(footer))}\n  </div>'


@checked
def to_html(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
    strict: bool = False,
    layout: Literal["col", "grid", "wireframe"] = "col",
    style: Literal["default", "dark", "none"] | str = "default",
    style_path: str | os.PathLike[str] | None = None,
    footer: str | None = None,
    fragment: bool = False,
    gap_x: float = -1.0,
    gap_y: float = -1.0,
    line_tolerance: float = DEFAULT_LINE_TOLERANCE,
    paragraph_margin: float = DEFAULT_PARAGRAPH_MARGIN,
    column_jump: float = DEFAULT_COLUMN_JUMP,
    scale: float | None = None,
) -> str:
    """Convert a ``document-extraction`` record to HTML.

    Every value from the record is escaped, whether or not it was validated, so untrusted records are safe to
    render with ``validate=False``.

    Args:
        record: The record to render.
        validate: Validate the record before rendering it.
        schema_version: The schema version to validate against, such as ``"0.8.0"``. Defaults to the newest.
        strict: Keep each line of a paragraph on its own line.
        layout: ``"col"`` (a single column), ``"grid"`` (rows and columns inferred from the block coordinates) or
            ``"wireframe"`` (each block drawn at its coordinates).
        style: The theme: ``"default"``, ``"dark"`` or ``"none"``. Any other value raises ``ValueError``; pass a
            stylesheet as ``style_path``.
        style_path: A CSS file to use in place of the theme. Its contents are embedded in the page.
        footer: Text shown at the bottom of the page. It is escaped, so any HTML in it is shown as text.
        fragment: Return only the document markup, without ``<html>``, ``<head>`` or ``<body>``. ``style`` and
            ``style_path`` are then ignored.
        gap_x: For the ``grid`` layout, the smallest horizontal gap that separates two columns.
        gap_y: For the ``grid`` layout, the smallest vertical gap that separates two rows.
        line_tolerance: As for ``to_txt``.
        paragraph_margin: As for ``to_txt``.
        column_jump: As for ``to_txt``.
        scale: As for ``to_txt``.

    Raises:
        ValueError: ``style`` isn't a theme, or both ``style`` and ``style_path`` are given.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "document-extraction", validate=validate, version=schema_version)

    unit = record.get("unit", "px")
    spatial_pages = extract_spatial_pages(
        record,
        strict=strict,
        line_tolerance=line_tolerance,
        paragraph_margin=paragraph_margin,
        column_jump=column_jump,
        scale=scale,
    )

    html_out = []

    if not fragment:
        theme_css = _resolve_theme_css(style, style_path)
        html_out.extend(
            [
                "<!DOCTYPE html>",
                '<html lang="en">',
                "<head>",
                '  <meta charset="utf-8"/>',
                "  <title>Document Extraction</title>",
                "  <style>",
                CORE_CSS,
                theme_css,
                "  </style>",
                "</head>",
                "<body>",
            ]
        )

    if not spatial_pages:
        html_out.append(
            '  <div class="page-container page-flow"><p class="block-text"><em>No content extracted from this document.</em></p></div>'
        )
        if footer:
            html_out.append(_footer_div(footer))
        if not fragment:
            html_out.extend(["</body>", "</html>"])
        return "\n".join(html_out)

    for i, (page_num, paragraphs) in enumerate(spatial_pages):
        if i > 0:
            html_out.append(f'  <div class="page-divider">Page {html.escape(str(page_num))}</div>')

        pw = get_page_dim(record, page_num, "page_width") or 850.0
        ph = get_page_dim(record, page_num, "page_height") or 1100.0

        if layout == "wireframe":
            html_out.append(
                f'  <div class="page-container page-wireframe" style="width: {pw}px; height: {ph}px; max-width: 100%;">'
            )
        else:
            html_out.append('  <div class="page-container page-flow">')

        if layout == "grid":
            html_out.append(render_tree(xy_cut(paragraphs, gap_y=gap_y, gap_x=gap_x)))
        elif layout == "col":
            html_out.append('<div class="layout-y">')
            for para in paragraphs:
                text = para.get("text", "")
                b_type = para.get("block_type", "text")
                if text:
                    html_out.append(f'  <p class="block-text">{html.escape(text)}</p>')
                else:
                    html_out.append(f'  <div class="figure-placeholder">[{html.escape(str(b_type))}]</div>')
            html_out.append("</div>")
        else:
            for para in paragraphs:
                box = para.get("box")
                text = para.get("text", "")
                if box:
                    style_str = format_css_coords(box, unit)
                    html_out.append(
                        f'  <div class="wireframe-box" style="{style_str}" title="{html.escape(text)}">{html.escape(text)}</div>'
                    )

        html_out.append("  </div>")

    if footer:
        html_out.append(_footer_div(footer))
    if not fragment:
        html_out.extend(["</body>", "</html>"])
    return "\n".join(html_out)

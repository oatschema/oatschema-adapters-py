# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

import pytest

from oatschema_adapters.document._layout import (
    _get_bounding_box,
    _get_scale_factor,
    _union_boxes,
    extract_spatial_pages,
    get_page_dim,
    xy_cut,
)


def test_get_scale_factor() -> None:
    """Test that the helper scales thresholds based on document units."""

    assert _get_scale_factor({"unit": "normalized"}) == 0.001

    assert _get_scale_factor({"unit": "px", "page_height": [{"value": 850}]}) == 0.85
    assert _get_scale_factor({"unit": "pt", "page_height": [{"value": 500}]}) == 0.5

    assert _get_scale_factor({"unit": "px", "page_height": 1100}) == 1.1

    assert _get_scale_factor({}) == 1.0
    assert _get_scale_factor({"unit": "mm"}) == 1.0


def test_extract_pages_basic(valid_document_record_1: dict[str, Any]) -> None:
    """Test standard spatial extraction with a valid Open Schema record."""
    pages = extract_spatial_pages(valid_document_record_1)

    assert len(pages) == 2
    assert pages[0][0] == 1

    page_1_paragraphs = pages[0][1]
    assert len(page_1_paragraphs) == 2

    assert page_1_paragraphs[0]["text"] == "Annual Report Summary"
    assert "The first column of text begins here" in page_1_paragraphs[1]["text"]


def test_extract_pages_no_text(
    valid_document_record_2: dict[str, Any], invalid_document_missing_text: dict[str, Any]
) -> None:
    """Ensure extraction gracefully ignores blocks without text strings."""

    assert len(extract_spatial_pages(invalid_document_missing_text)) == 0


def test_extract_pages_strict_mode_and_hyphens() -> None:
    """Test that hyphenated words are joined in semantic mode, but split in strict mode."""
    record = {
        "blocks": [
            {"text": "This is a docu-", "box": {"x": 0, "y": 10, "width": 10, "height": 10}, "page_number": 1},
            {"text": "ment.", "box": {"x": 0, "y": 18, "width": 10, "height": 10}, "page_number": 1},
        ]
    }

    non_strict_pages = extract_spatial_pages(record, strict=False)
    assert non_strict_pages[0][1][0]["text"] == "This is a document."

    strict_pages = extract_spatial_pages(record, strict=True)
    assert strict_pages[0][1][0]["text"] == "This is a docu-\nment."


def test_extract_pages_column_jump_and_paragraph_margin() -> None:
    """Test spatial grouping logic (line breaks, paragraph margins, and negative column jumps)."""
    record = {
        "blocks": [
            {"text": "Paragraph 1, Line 1", "box": {"x": 0, "y": 10, "width": 10, "height": 10}, "page_number": 1},
            {"text": "Paragraph 1, Line 2", "box": {"x": 0, "y": 12, "width": 10, "height": 10}, "page_number": 1},
            {"text": "Paragraph 2, Line 1", "box": {"x": 0, "y": 50, "width": 10, "height": 10}, "page_number": 1},
            {"text": "Column 2, Line 1", "box": {"x": 50, "y": 10, "width": 10, "height": 10}, "page_number": 1},
        ]
    }
    pages = extract_spatial_pages(record)
    paragraphs = pages[0][1]

    assert len(paragraphs) == 3
    assert paragraphs[0]["text"] == "Paragraph 1, Line 1 Paragraph 1, Line 2"
    assert paragraphs[1]["text"] == "Paragraph 2, Line 1"
    assert paragraphs[2]["text"] == "Column 2, Line 1"


def test_extract_pages_explicit_scale() -> None:
    """Test that an explicitly provided scale overrides the schema unit scaling."""
    record = {
        "blocks": [
            {"text": "Block 1", "box": {"x": 0, "y": 10, "width": 10, "height": 10}, "page_number": 1},
            {"text": "Block 2", "box": {"x": 0, "y": 50, "width": 10, "height": 10}, "page_number": 1},
        ]
    }

    pages = extract_spatial_pages(record, scale=3.0)

    assert len(pages) == 1
    assert len(pages[0][1]) == 1
    assert pages[0][1][0]["text"] == "Block 1 Block 2"


def test_get_scale_factor_pagination() -> None:
    """Test the scale factor fallback and explicit page matching logic."""
    record = {"unit": "px", "page_height": [{"value": 850, "pages": [1, 2]}, {"value": 1200, "pages": [3]}]}

    assert _get_scale_factor(record, page_num=1) == 0.85

    assert _get_scale_factor(record, page_num=3) == 1.2

    assert _get_scale_factor(record, page_num=4) == 0.85


def test_get_bounding_box() -> None:
    """Test extracting strict floating-point bounding boxes from mixed geometry schemas."""

    assert _get_bounding_box({"box": {"x": 10, "y": 20, "width": 100, "height": 50}}) == {
        "x": 10.0,
        "y": 20.0,
        "width": 100.0,
        "height": 50.0,
    }

    poly_block = {"polygon": [{"x": 10, "y": 10}, {"x": 20, "y": 10}, {"x": 20, "y": 20}, {"x": 10, "y": 20}]}
    assert _get_bounding_box(poly_block) == {"x": 10.0, "y": 10.0, "width": 10.0, "height": 10.0}

    mpoly_block = {"multi_polygon": [[{"x": 5, "y": 5}, {"x": 15, "y": 15}], [{"x": 20, "y": 20}, {"x": 30, "y": 30}]]}
    assert _get_bounding_box(mpoly_block) == {"x": 5.0, "y": 5.0, "width": 25.0, "height": 25.0}

    assert _get_bounding_box({"text": "I have no coordinates"}) is None


def test_union_boxes() -> None:
    """Test calculating the bounding box union of multiple boxes, including None values."""
    boxes: list[dict[str, float] | None] = [
        {"x": 10, "y": 10, "width": 10, "height": 10},
        None,
        {"x": 25, "y": 25, "width": 5, "height": 5},
    ]

    assert _union_boxes(boxes) == {"x": 10, "y": 10, "width": 20, "height": 20}

    assert _union_boxes([]) is None
    assert _union_boxes([None, None]) is None


def test_get_page_dim() -> None:
    """Test safe extraction of page dimensions with fallbacks."""
    record_int = {"page_width": 800}
    assert get_page_dim(record_int, 1, "page_width") == 800.0

    record_list = {"page_width": [{"value": 850, "pages": [1]}, {"value": 900, "pages": [2]}]}
    assert get_page_dim(record_list, 2, "page_width") == 900.0
    assert get_page_dim(record_list, 3, "page_width") == 850.0

    assert get_page_dim({}, 1, "page_width") is None


def test_extract_spatial_pages() -> None:
    """Test that extract_spatial_pages preserves geometry and handles non-text elements."""
    record = {
        "blocks": [
            {"text": "Line 1-", "box": {"x": 0, "y": 0, "width": 100, "height": 10}, "page_number": 1},
            {"text": "Line 2", "box": {"x": 0, "y": 12, "width": 100, "height": 10}, "page_number": 1},
            {"text": "Para 2", "box": {"x": 0, "y": 50, "width": 100, "height": 10}, "page_number": 1},
            {
                "block_type": "image",
                "box": {"x": 0, "y": 100, "width": 50, "height": 50},
                "page_number": 1,
            },
            {"text": "Page 2 text", "box": {"x": 0, "y": 10, "width": 100, "height": 10}, "page_number": 2},
        ]
    }

    pages = extract_spatial_pages(record, strict=False)
    assert len(pages) == 2

    page1_paras = pages[0][1]
    assert len(page1_paras) == 3

    assert page1_paras[0]["text"] == "Line 1Line 2"
    assert page1_paras[0]["box"] == {"x": 0.0, "y": 0.0, "width": 100.0, "height": 22.0}

    assert page1_paras[1]["text"] == "Para 2"

    assert page1_paras[2]["block_type"] == "image"
    assert page1_paras[2]["text"] == ""
    assert page1_paras[2]["box"] == {"x": 0.0, "y": 100.0, "width": 50.0, "height": 50.0}

    pages_strict = extract_spatial_pages(record, strict=True)
    assert pages_strict[0][1][0]["text"] == "Line 1-\nLine 2"


def test_xy_cut() -> None:
    """Test the recursive layout tree algorithm."""

    assert xy_cut([]) == {"type": "empty"}

    node = {"block_type": "text", "text": "Hello", "box": {"x": 0, "y": 0, "width": 10, "height": 10}}
    leaf_tree = xy_cut([node])
    assert leaf_tree["type"] == "leaf"
    assert leaf_tree["box"] == node["box"]

    n1 = {"box": {"x": 0, "y": 0, "width": 100, "height": 10}}
    n2 = {"box": {"x": 0, "y": 20, "width": 100, "height": 10}}
    y_tree = xy_cut([n1, n2])
    assert y_tree["type"] == "y-cut"
    assert len(y_tree["children"]) == 2

    n3 = {"box": {"x": 0, "y": 0, "width": 40, "height": 10}}
    n4 = {"box": {"x": 50, "y": 0, "width": 40, "height": 10}}
    x_tree = xy_cut([n3, n4])
    assert x_tree["type"] == "x-cut"
    assert len(x_tree["children"]) == 2

    n5 = {"box": {"x": 0, "y": 0, "width": 100, "height": 100}}
    n6 = {"box": {"x": 10, "y": 10, "width": 20, "height": 20}}
    c_tree = xy_cut([n5, n6])
    assert c_tree["type"] == "cluster"
    assert len(c_tree["children"]) == 2


def test_extract_spatial_pages_strict_and_missing_boxes() -> None:
    """Test strict line breaks, standard space joining, and blocks missing bounding boxes."""
    record = {
        "blocks": [
            {"text": "I am floating in the void", "page_number": 1},
            {"text": "Hello", "box": {"x": 0, "y": 10, "width": 10, "height": 10}, "page_number": 1},
            {"text": "world", "box": {"x": 0, "y": 20, "width": 10, "height": 10}, "page_number": 1},
        ]
    }

    pages_semantic = extract_spatial_pages(record, strict=False)
    paras_semantic = pages_semantic[0][1]
    assert paras_semantic[0]["text"] == "I am floating in the void"
    assert paras_semantic[0]["box"] is None
    assert paras_semantic[1]["text"] == "Hello world"

    pages_strict = extract_spatial_pages(record, strict=True)
    paras_strict = pages_strict[0][1]
    assert paras_strict[1]["text"] == "Hello\nworld"


def test_xy_cut_missing_box() -> None:
    """Test that the xy_cut algorithm safely groups nodes that lack bounding boxes."""
    nodes: list[dict[str, Any]] = [
        {"box": {"x": 0, "y": 0, "width": 100, "height": 10}},
        {"text": "Invisible node"},
        {"box": {"x": 0, "y": 50, "width": 100, "height": 10}},
    ]

    tree = xy_cut(nodes)

    assert tree["type"] == "y-cut"
    assert len(tree["children"]) == 2


def test_extract_spatial_pages_scores_and_attrs() -> None:
    """Ensure scores and attributes are properly propagated to the stitched lines."""
    record = {
        "blocks": [
            {
                "text": "High confidence text",
                "box": {"x": 0, "y": 0, "width": 10, "height": 10},
                "score": 0.99,
                "attributes": {"font_weight": "bold"},
            }
        ]
    }
    pages = extract_spatial_pages(record)
    para = pages[0][1][0]

    assert para["score"] == 0.99
    assert para["attributes"] == {"font_weight": "bold"}

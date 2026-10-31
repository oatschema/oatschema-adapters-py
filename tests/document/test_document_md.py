# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import pytest

from oatschema_adapters.document._md import to_md


def test_to_md_rich_rag_features() -> None:
    """Test all LLM-optimized enrichments and hit 100% coverage branches."""
    record = {
        "producer": "test-runner",
        "extraction_type": "mixed",
        "unit": "px",
        "score_explanation": "OCR Confidence",
        "attributes": {"doc_type": "invoice", "tags": ["finance", "2026"]},
        "blocks": [
            {"text": "Invoice", "block_type": "text", "page_number": 1, "attributes": {"visual_class": "title"}},
            {"text": "Summary", "block_type": "text", "page_number": 1, "attributes": {"visual_class": "h2"}},
            {"text": "Items", "block_type": "text", "page_number": 1, "attributes": {"visual_class": "heading"}},
            {"text": "Blurry", "block_type": "text", "page_number": 1, "score": 0.50},
            {"block_type": "image", "box": {"x": 10, "y": 20, "width": 100, "height": 100}, "page_number": 1},
        ],
    }

    result = to_md(record, validate=False)
    assert "producer: test-runner" in result
    assert "score_explanation: OCR Confidence" in result
    assert 'doc_type: "invoice"' in result
    assert "# Invoice" in result
    assert "## Summary" in result
    assert "### Items" in result
    assert "> ⚠️ **Low Confidence Read (0.50)**" in result

    no_fm = to_md(record, validate=False, include_frontmatter=False)
    assert "---" not in no_fm


def test_to_md_empty() -> None:
    """Ensure egress fails gracefully if blocks are missing."""
    with pytest.raises(ValueError):
        to_md({"extraction_type": "text", "blocks": []}, validate=False)


def test_to_md_validation_and_skips() -> None:
    """Test explicit validation and the skipping of empty text nodes."""
    record = {
        "producer": "test",
        "extraction_type": "mixed",
        "unit": "px",
        "blocks": [
            {
                "block_type": "text",
                "text": "Valid text",
                "page_number": 1,
                "box": {"x": 0, "y": 0, "width": 10, "height": 10},
            },
            {"block_type": "text", "text": "   ", "page_number": 1},
            {
                "block_type": "multi_polygon",
                "page_number": 1,
                "multi_polygon": [[{"x": 10, "y": 10}, {"x": 20, "y": 10}, {"x": 15, "y": 20}]],
            },
        ],
    }

    result = to_md(record, validate=True)

    assert "Valid text" in result
    assert "> *[Multi_polygon at x:10, y:10, w:10, h:10]*" in result
    assert "Valid text\n\n> *[Multi_polygon" in result

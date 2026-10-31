# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

import pytest
from oatschema import ValidationError as JsonSchemaValidationError

from oatschema_adapters.document._tsv import from_tsv, to_tsv

VALID_TSV = """page_number\tblock_type\tx\ty\twidth\theight\ttext
1\ttext\t10.5\t20.0\t100\t50\tHello world
2\tbox\t\t\t\t\tJust some text
3\t\tbad_x\t\t\t\tText with bad x
"""


def test_to_tsv_conversion(valid_document_record_1: dict[str, Any]) -> None:
    """Test standard egress from Open Schema to TSV string."""
    result = to_tsv(valid_document_record_1, validate=False)

    assert "page_number\tblock_type\tx\ty\twidth\theight\ttext" in result
    assert "1\ttext\t\t\t\t\tAnnual Report Summary" in result
    assert "1\tbox\t50\t120\t250\t400\tThe first column" in result


def test_from_tsv_conversion() -> None:
    """Test standard ingress from TSV string to Open Schema record."""
    record = from_tsv(VALID_TSV, producer="test-runner", validate=False)

    assert record["producer"] == "test-runner"
    assert len(record["blocks"]) == 3

    assert record["blocks"][0]["page_number"] == 1
    assert record["blocks"][0]["block_type"] == "text"
    assert record["blocks"][0]["text"] == "Hello world"
    assert record["blocks"][0]["box"] == {"x": 10.5, "y": 20.0, "width": 100.0, "height": 50.0}

    assert record["blocks"][1]["page_number"] == 2
    assert record["blocks"][1]["block_type"] == "box"
    assert record["blocks"][1]["text"] == "Just some text"
    assert "box" not in record["blocks"][1]

    assert record["blocks"][2]["text"] == "Text with bad x"
    assert "box" not in record["blocks"][2]


def test_to_tsv_empty() -> None:
    """Ensure egress fails gracefully if 'blocks' are missing."""
    with pytest.raises(ValueError, match="contains no 'blocks'"):
        to_tsv({"extraction_type": "text"}, validate=False)


def test_from_tsv_empty() -> None:
    """Ensure ingress fails gracefully on empty TSV string."""
    with pytest.raises(ValueError, match="Provided TSV content is empty"):
        from_tsv("   \n  ", validate=False)


def test_from_tsv_missing_text_col() -> None:
    """Ensure ingress fails if the required text column is missing."""
    with pytest.raises(ValueError, match="TSV must contain at least a 'text' column"):
        from_tsv("page_number\tx\n1\t50", validate=False)


def test_validation_success_with_defaults(valid_document_record_1: dict[str, Any]) -> None:
    """Verify that auto-validation passes with valid data."""
    try:
        valid_schema_tsv = "page_number\tblock_type\ttext\n1\ttext\tHello"
        from_tsv(valid_schema_tsv, validate=True)
        to_tsv(valid_document_record_1, validate=True)
    except Exception as e:
        pytest.fail(f"Validation failed unexpectedly: {e}")


def test_validation_failure_on_invalid_data(invalid_document_bad_norm: dict[str, Any]) -> None:
    """Verify that validation correctly catches schema violations."""
    with pytest.raises(JsonSchemaValidationError):
        to_tsv(invalid_document_bad_norm, validate=True)

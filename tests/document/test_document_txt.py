# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

import pytest
from oatschema import ValidationError as JsonSchemaValidationError

from oatschema_adapters.document._txt import from_txt, to_txt

VALID_TXT = "This is a simple text document.\n\nIt has two paragraphs."


def test_to_txt_conversion(valid_document_record_1: dict[str, Any]) -> None:
    """Test standard egress from Open Schema to plain text."""
    result = to_txt(valid_document_record_1, validate=False)
    assert "--- Page 2 ---" in result
    assert "Annual Report Summary" in result
    assert "The first column of text begins here" in result


def test_from_txt_conversion() -> None:
    """Test standard ingress from text string to Open Schema record."""
    record = from_txt(VALID_TXT, producer="test-runner", validate=False)
    assert record["producer"] == "test-runner"
    assert record["extraction_type"] == "text"
    assert len(record["blocks"]) == 1
    assert record["blocks"][0]["text"] == VALID_TXT


def test_to_txt_empty() -> None:
    """Ensure egress fails gracefully if 'blocks' are missing."""
    with pytest.raises(ValueError, match="contains no 'blocks'"):
        to_txt({"extraction_type": "text"}, validate=False)


def test_from_txt_empty() -> None:
    """Ensure ingress fails gracefully on empty text."""
    with pytest.raises(ValueError, match="Provided text content is empty"):
        from_txt("   \n  ", validate=False)


def test_validation_success_with_defaults(valid_document_record_1: dict[str, Any]) -> None:
    """Verify that auto-validation passes with a valid record and string."""
    try:
        from_txt(VALID_TXT, validate=True)
        to_txt(valid_document_record_1, validate=True)
    except Exception as e:
        pytest.fail(f"Validation failed unexpectedly: {e}")


def test_validation_failure_on_invalid_data(invalid_document_bad_norm: dict[str, Any]) -> None:
    """Verify that validation correctly catches schema violations."""
    with pytest.raises(JsonSchemaValidationError):
        to_txt(invalid_document_bad_norm, validate=True)

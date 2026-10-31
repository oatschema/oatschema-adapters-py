# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

import pytest
from oatschema import ValidationError as JsonSchemaValidationError

from oatschema_adapters.audio._txt import from_txt, to_txt

VALID_TXT = "Welcome back! Today, my guest is the renowned chef, Jean-Pierre. Thank you, it's a pleasure. You know, the secret is simple, c'est une question de respect pour le produit. It's all about respecting the product."


def test_to_txt_conversion(valid_audio_record: dict[str, Any]) -> None:
    """Test standard egress from Open Schema to plain text."""
    result = to_txt(valid_audio_record, validate=False)
    assert result.startswith("Welcome back! Today, my guest is the renowned chef")
    assert result.endswith("respecting the product.")


def test_to_txt_fallback(valid_audio_record: dict[str, Any]) -> None:
    """Test egress correctly falls back to joining segments if the top-level 'text' field is absent."""
    record_no_text = valid_audio_record.copy()
    del record_no_text["text"]

    result = to_txt(record_no_text, validate=False)
    assert "Welcome back!" in result
    assert "[laughter]" in result


def test_from_txt_conversion() -> None:
    """Test standard ingress from text string to Open Schema record."""
    record = from_txt(VALID_TXT, producer="test-runner", validate=False)

    assert record["producer"] == "test-runner"
    assert record["text"] == VALID_TXT
    assert "segments" not in record


def test_to_txt_empty(invalid_audio_record_2: dict[str, Any]) -> None:
    """Ensure egress fails gracefully if neither text nor segments exist."""
    with pytest.raises(ValueError, match="contains no 'text' or 'segments'"):
        to_txt(invalid_audio_record_2, validate=False)


def test_from_txt_empty() -> None:
    """Ensure ingress fails gracefully on empty text."""
    with pytest.raises(ValueError, match="Provided text content is empty"):
        from_txt("   \n  ", validate=False)


def test_validation_success_with_defaults(valid_audio_record: dict[str, Any]) -> None:
    """Verify that auto-validation passes with a valid record and string."""
    try:
        from_txt(VALID_TXT, validate=True)
        to_txt(valid_audio_record, validate=True)
    except Exception as e:
        pytest.fail(f"Validation failed unexpectedly: {e}")


def test_validation_failure_on_invalid_data(invalid_audio_record_1: dict[str, Any]) -> None:
    """Verify that validation correctly catches schema violations."""
    with pytest.raises(JsonSchemaValidationError):
        to_txt(invalid_audio_record_1, validate=True)

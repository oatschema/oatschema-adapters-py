# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

import pytest
import srt
from oatschema import ValidationError as JsonSchemaValidationError

from oatschema_adapters.audio._srt import from_srt, to_srt

VALID_SRT = """1
00:00:00,500 --> 00:00:04,750
Welcome back! Today, my guest is the renowned chef, Jean-Pierre.

2
00:00:05,100 --> 00:00:08,250
Thank you, it's a pleasure. You know, the secret is simple,

3
00:00:08,250 --> 00:00:10,900
c'est une question de respect pour le produit.

4
00:00:11,000 --> 00:00:11,800
[laughter]

5
00:00:12,000 --> 00:00:14,500
It's all about respecting the product.
"""


def test_to_srt_conversion(valid_audio_record: dict[str, Any]) -> None:
    """Test standard egress from Open Schema to SRT string."""
    result = to_srt(valid_audio_record, validate=False)

    assert "Welcome back!" in result
    assert "00:00:05,100 --> 00:00:08,250" in result
    assert len(list(srt.parse(result))) == 5


def test_from_srt_conversion() -> None:
    """Test standard ingress from SRT string to Open Schema record."""
    record = from_srt(VALID_SRT, producer="test-runner", validate=False)

    assert record["producer"] == "test-runner"
    assert "Welcome back!" in record["text"]
    assert len(record["segments"]) == 5
    assert record["segments"][0]["start_time"] == 0.5
    assert record["segments"][4]["end_time"] == 14.5


def test_validation_success_with_defaults(valid_audio_record: dict[str, Any]) -> None:
    """Verify that auto-validation passes with a valid record and default version."""
    try:
        from_srt(VALID_SRT, validate=True)
        to_srt(valid_audio_record, validate=True)
    except Exception as e:
        pytest.fail(f"Validation failed unexpectedly: {e}")


def test_validation_failure_on_invalid_data(invalid_audio_record_1: dict[str, Any]) -> None:
    """Verify that validation correctly catches schema violations."""
    with pytest.raises(JsonSchemaValidationError):
        to_srt(invalid_audio_record_1, validate=True)


def test_versioned_validation() -> None:
    """Verify we can explicitly target a schema version."""
    result = from_srt(VALID_SRT, validate=True, schema_version="0.4.0")
    assert "Welcome back!" in result["segments"][0]["text"]


def test_from_srt_parse_error() -> None:
    """Ensure malformed SRT content raises a ValueError."""
    bad_srt = "This is not an SRT file at all."
    with pytest.raises(ValueError, match="Failed to parse SRT content"):
        from_srt(bad_srt)


def test_to_srt_missing_segments(invalid_audio_record_2: dict[str, Any]) -> None:
    """Ensure egress fails gracefully if the record is missing segments."""
    with pytest.raises(ValueError, match="does not contain any 'segments'"):
        to_srt(invalid_audio_record_2, validate=False)


def test_to_srt_with_speakers(valid_audio_record: dict[str, Any]) -> None:
    """Ensure that the `include_speakers` flag prepends the speaker name."""
    valid_audio_record["segments"][0]["speaker"] = {"name": "Jean-Pierre", "id": "jp"}

    srt_out = to_srt(valid_audio_record, validate=False, include_speakers=True)

    assert "Jean-Pierre: Welcome back!" in srt_out

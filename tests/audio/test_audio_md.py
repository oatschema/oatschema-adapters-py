# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

import pytest
from oatschema import ValidationError as JsonSchemaValidationError

from oatschema_adapters.audio._md import _format_time, from_md, to_md
from oatschema_adapters.audio._time import parse_clock as _parse_time

VALID_MD = """---
producer: test-runner
---


**[00:00 - 00:04]** Welcome back! Today, my guest is the renowned chef, Jean-Pierre.

> *[applause, cheer]*

**[00:05 - 00:08]** Thank you, it's a pleasure. You know, the secret is simple,

> ⚠️ **Low Confidence Read (0.45)**:
> **[00:08 - 00:10]** c'est une question de respect pour le produit.

**[00:11 - 00:11]** [laughter]

**[00:12 - 00:14]** It's all about respecting the product.
"""


def test_time_helpers() -> None:
    """Test the internal time formatting and parsing utilities."""
    assert _format_time(65.123, include_milliseconds=True) == "01:05.123"
    assert _format_time(3665.123, include_milliseconds=True) == "01:01:05.123"

    assert _format_time(65.123, include_milliseconds=False) == "01:05"
    assert _format_time(3665.123, include_milliseconds=False) == "01:01:05"

    assert _parse_time("01:05.123") == 65.123
    assert _parse_time("01:01:05.123") == 3665.123
    assert _parse_time("65.123") == 65.123


def test_to_md_rich_rag_features() -> None:
    """Test all LLM-optimized enrichments: Frontmatter, Events, and Warnings."""
    record = {
        "producer": "test-runner",
        "language": "eng",
        "duration": 120.5,
        "track_id": "CH1",
        "attributes": {"domain": "medical"},
        "segments": [
            {"start_time": 0.0, "end_time": 5.0, "text": "Normal text.", "events": ["door closes", "footsteps"]},
            {
                "start_time": 5.0,
                "end_time": 10.0,
                "text": "Mumbled words",
                "score": 0.45,
                "speaker": {"id": "1", "name": "Dr. Smith"},
            },
            {"start_time": 10.0, "end_time": 15.0, "text": "", "events": ["silence"]},
        ],
    }

    res = to_md(record, validate=False, include_speakers=True)

    assert "language: eng" in res
    assert 'domain: "medical"' in res
    assert "> *[door closes, footsteps]*" in res
    assert "> ⚠️ **Low Confidence Read (0.45)**:\n> **[00:05 - 00:10]** **Dr. Smith:** Mumbled words" in res
    assert "> *[silence]*" in res

    no_fm = to_md(record, validate=False, include_frontmatter=False, include_timestamps=False, include_speakers=False)
    assert "---" not in no_fm
    assert "> ⚠️ **Low Confidence Read (0.45)**:\n> Mumbled words" in no_fm


def test_to_md_no_segments(valid_audio_record: dict[str, Any]) -> None:
    """Test egress gracefully handles records with text but no segments, respecting frontmatter."""
    record = valid_audio_record.copy()
    del record["segments"]

    record["producer"] = "test-runner"

    result = to_md(record, validate=False)
    assert "---" in result
    assert "producer: test-runner" in result
    assert "# Transcription" in result
    assert "Welcome back!" in result
    assert "**[" not in result


def test_from_md_conversion() -> None:
    """Test ingress from Markdown string to Open Schema record, validating blockquote stripping."""
    record = from_md(VALID_MD, producer="test-runner", validate=False)

    assert record["producer"] == "test-runner"
    assert len(record["segments"]) == 5

    assert record["segments"][0]["start_time"] == 0.0
    assert record["segments"][0]["end_time"] == 4.0
    assert record["segments"][0]["text"] == "Welcome back! Today, my guest is the renowned chef, Jean-Pierre."
    assert "events" not in record["segments"][0]

    assert record["segments"][1]["events"] == ["applause", "cheer"]
    assert record["segments"][1]["start_time"] == 5.0
    assert record["segments"][1]["text"].startswith("Thank you")

    assert record["segments"][2]["text"] == "c'est une question de respect pour le produit."


def test_from_md_with_speakers() -> None:
    """Test ingress parsing handles speaker names correctly."""
    md_with_speakers = "# Transcription\n\n**[00:00 - 00:05]** **Maria:** Hello!"
    record = from_md(md_with_speakers, validate=False)

    assert record["segments"][0]["speaker"]["name"] == "Maria"
    assert record["segments"][0]["text"] == "Hello!"


def test_from_md_plain_text() -> None:
    """Test ingress gracefully handles lines without strict timestamp formatting."""
    md_plain = "# Transcription\n\nJust some random text without timestamps."
    record = from_md(md_plain, validate=False)

    assert record["segments"][0]["start_time"] == 0.0
    assert record["segments"][0]["end_time"] == 0.0
    assert record["segments"][0]["text"] == "Just some random text without timestamps."


def test_to_md_empty(invalid_audio_record_2: dict[str, Any]) -> None:
    """Ensure egress fails gracefully if neither text nor segments exist."""
    with pytest.raises(ValueError, match="contains no 'text' or 'segments'"):
        to_md(invalid_audio_record_2, validate=False)


def test_from_md_empty() -> None:
    """Ensure ingress fails gracefully on empty text."""
    with pytest.raises(ValueError, match="Provided Markdown content is empty"):
        from_md("   \n  ", validate=False)


def test_validation_success_with_defaults(valid_audio_record: dict[str, Any]) -> None:
    """Verify that auto-validation passes with valid data."""
    try:
        from_md(VALID_MD, validate=True)
        to_md(valid_audio_record, validate=True)
    except Exception as e:
        pytest.fail(f"Validation failed unexpectedly: {e}")


def test_validation_failure_on_invalid_data(invalid_audio_record_1: dict[str, Any]) -> None:
    """Verify that validation correctly catches schema violations."""
    with pytest.raises(JsonSchemaValidationError):
        to_md(invalid_audio_record_1, validate=True)

# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from typing import Any

import pytest

DATA = Path(__file__).resolve().parent / "data"


def load(name: str) -> dict[str, Any]:
    """Return the fixture ``tests/data/<name>.json``."""
    record: dict[str, Any] = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))
    return record


@pytest.fixture
def valid_audio_record() -> dict[str, Any]:
    return load("audio-transcription-1")


@pytest.fixture
def invalid_audio_record_1() -> dict[str, Any]:
    return load("invalid-audio-transcription-invalid-segment")


@pytest.fixture
def invalid_audio_record_2() -> dict[str, Any]:
    return load("invalid-audio-transcription-missing-content")


@pytest.fixture
def valid_document_record_1() -> dict[str, Any]:
    return load("document-extraction-1")


@pytest.fixture
def valid_document_record_2() -> dict[str, Any]:
    return load("document-extraction-2")


@pytest.fixture
def invalid_document_missing_text() -> dict[str, Any]:
    return load("invalid-document-extraction-bad-missing-text")


@pytest.fixture
def invalid_document_bad_norm() -> dict[str, Any]:
    return load("invalid-document-extraction-bad-multipolygon-norm")

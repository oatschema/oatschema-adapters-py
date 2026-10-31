# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

"""The export cases compared with dorsalhub-adapters 0.4.3's output. Standard library only."""

from typing import Any

AUDIO_FIXTURES = [
    "audio-transcription-1",
    "audio-transcription-2",
    "audio-transcription-formulas",
    "audio-transcription-legacy-ids",
    "audio-transcription-text-only",
]
DOCUMENT_FIXTURES = [
    "document-extraction-1",
    "document-extraction-2",
    "document-extraction-3",
    "document-extraction-formulas",
    "document-extraction-hostile",
    "document-extraction-normalized",
    "document-extraction-per-mille",
    "document-extraction-text-only",
]

AUDIO_OPTIONS: dict[str, list[dict[str, Any]]] = {
    "srt": [{}, {"include_speakers": True}],
    "vtt": [{}, {"include_speakers": True}],
    "md": [
        {},
        {"include_speakers": True, "include_milliseconds": True},
        {"include_timestamps": False, "include_frontmatter": False},
        {"low_confidence_threshold": 0.99},
    ],
    "txt": [{}],
    "tsv": [{}, {"include_speakers": True}],
}
DOCUMENT_OPTIONS: dict[str, list[dict[str, Any]]] = {
    "txt": [{}, {"strict": True}],
    "md": [{}, {"include_frontmatter": False}, {"strict": True, "low_confidence_threshold": 0.99}],
    "tsv": [{}],
    "hocr": [{}],
    "html": [
        {},
        {"layout": "grid"},
        {"layout": "wireframe"},
        {"layout": "col", "style": "dark"},
        {"layout": "grid", "style": "none"},
        {"layout": "wireframe", "fragment": True},
        {"footer": 'Made with <b>care</b> & "quotes"', "fragment": True},
        {"layout": "grid", "gap_x": 5, "gap_y": 5},
        {"line_tolerance": 3, "strict": True},
    ],
}
PARSE_FORMATS = {
    "audio-transcription": ["srt", "vtt", "md", "txt", "tsv"],
    "document-extraction": ["txt", "tsv", "hocr"],
}
EXTENSIONS = {"srt": "srt", "vtt": "vtt", "md": "md", "txt": "txt", "tsv": "tsv", "hocr": "hocr.html", "html": "html"}


def export_cases() -> list[tuple[str, str, str, str, dict[str, Any]]]:
    """Return ``(case_id, schema, format, fixture, options)`` for every export case."""
    cases = []
    for schema, fixtures, table in (
        ("audio-transcription", AUDIO_FIXTURES, AUDIO_OPTIONS),
        ("document-extraction", DOCUMENT_FIXTURES, DOCUMENT_OPTIONS),
    ):
        for fixture in fixtures:
            for fmt, option_sets in table.items():
                for index, options in enumerate(option_sets):
                    cases.append((f"{fixture}.{fmt}.{index}", schema, fmt, fixture, options))
    return cases

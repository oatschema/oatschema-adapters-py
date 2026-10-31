# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

"""Every export and parse matches the recorded dorsalhub-adapters 0.4.3 output, except for the fixes listed here."""

import json
from pathlib import Path
from typing import Any

import pytest

import oatschema_adapters
from golden_cases import EXTENSIONS, PARSE_FORMATS, export_cases

DATA = Path(__file__).resolve().parent / "data"
EXPECTED = DATA / "expected"
INDEX: dict[str, Any] = json.loads((EXPECTED / "index.json").read_text(encoding="utf-8"))

SUBSTITUTIONS = [
    ("/* Dorsal" + "Hub Light Theme */", "/* Light Theme */"),
    ("/* Dorsal" + "Hub Dark Theme */", "/* Dark Theme */"),
    ('content="dorsal' + '-adapters"', 'content="oatschema-adapters"'),
]

FRONTMATTER = "frontmatter values that YAML would misread are quoted"
MD_PARSE = "from_md reads millisecond times, and gives events to the segment that follows them"
VTT_ROUNDING = "times round to the millisecond, so 59.9996 s is 00:01:00.000, not the invalid 00:00:60.000"
GRID_GAPS = "gap_x and gap_y work, instead of raising TypeError"
TSV_FORMULAS = "cells a spreadsheet would run as formulas start with an apostrophe"
TSV_EMPTY_CELL = "a last row ending in an empty cell parses"
TSV_TEXT = "an empty text cell gives no text to a block that doesn't need one, instead of '' or None"
HOCR_UNITS = "normalized and per_mille coordinates are scaled to the page"
HOCR_NO_LINES = "content with no ocr_line text raises ValueError instead of returning no blocks"

CHANGED = {
    "audio-transcription-1.md.0": FRONTMATTER,
    "audio-transcription-1.md.0.parsed": MD_PARSE,
    "audio-transcription-1.md.1": FRONTMATTER,
    "audio-transcription-1.md.1.parsed": MD_PARSE,
    "audio-transcription-1.md.2.parsed": MD_PARSE,
    "audio-transcription-1.md.3": FRONTMATTER,
    "audio-transcription-1.md.3.parsed": MD_PARSE,
    "audio-transcription-2.vtt.0": VTT_ROUNDING,
    "audio-transcription-2.vtt.0.parsed": VTT_ROUNDING,
    "audio-transcription-2.vtt.1": VTT_ROUNDING,
    "audio-transcription-2.vtt.1.parsed": VTT_ROUNDING,
    "audio-transcription-2.md.0": FRONTMATTER,
    "audio-transcription-2.md.0.parsed": MD_PARSE,
    "audio-transcription-2.md.1": FRONTMATTER,
    "audio-transcription-2.md.1.parsed": MD_PARSE,
    "audio-transcription-2.md.2.parsed": MD_PARSE,
    "audio-transcription-2.md.3": FRONTMATTER,
    "audio-transcription-2.md.3.parsed": MD_PARSE,
    "audio-transcription-formulas.md.0": FRONTMATTER,
    "audio-transcription-formulas.md.1": FRONTMATTER,
    "audio-transcription-formulas.md.1.parsed": MD_PARSE,
    "audio-transcription-formulas.md.3": FRONTMATTER,
    "audio-transcription-formulas.tsv.0": TSV_FORMULAS,
    "audio-transcription-formulas.tsv.1": TSV_FORMULAS,
    "audio-transcription-formulas.tsv.1.parsed": TSV_EMPTY_CELL,
    "audio-transcription-legacy-ids.md.0.parsed": MD_PARSE,
    "audio-transcription-legacy-ids.md.1.parsed": MD_PARSE,
    "audio-transcription-legacy-ids.md.2.parsed": MD_PARSE,
    "audio-transcription-legacy-ids.md.3.parsed": MD_PARSE,
    "document-extraction-1.html.7": GRID_GAPS,
    "document-extraction-2.tsv.0.parsed": TSV_TEXT,
    "document-extraction-2.hocr.0.parsed": HOCR_NO_LINES,
    "document-extraction-2.html.7": GRID_GAPS,
    "document-extraction-3.md.0": FRONTMATTER,
    "document-extraction-3.md.2": FRONTMATTER,
    "document-extraction-3.tsv.0.parsed": TSV_TEXT,
    "document-extraction-3.html.7": GRID_GAPS,
    "document-extraction-formulas.tsv.0": TSV_FORMULAS,
    "document-extraction-formulas.tsv.0.parsed": TSV_FORMULAS,
    "document-extraction-formulas.html.7": GRID_GAPS,
    "document-extraction-hostile.md.0": FRONTMATTER,
    "document-extraction-hostile.md.2": FRONTMATTER,
    "document-extraction-hostile.tsv.0.parsed": TSV_TEXT,
    "document-extraction-hostile.html.7": GRID_GAPS,
    "document-extraction-normalized.hocr.0": HOCR_UNITS,
    "document-extraction-normalized.hocr.0.parsed": HOCR_UNITS,
    "document-extraction-normalized.html.7": GRID_GAPS,
    "document-extraction-per-mille.html.7": GRID_GAPS,
    "document-extraction-text-only.html.7": GRID_GAPS,
}


RAISES_NOW = {"document-extraction-2.hocr.0.parsed": "ValueError"}


def _normalise(text: str) -> str:
    for old, new in SUBSTITUTIONS:
        text = text.replace(old, new)
    return text


def _results() -> dict[str, tuple[str | None, str | None]]:
    results: dict[str, tuple[str | None, str | None]] = {}
    for case_id, schema, fmt, fixture, options in export_cases():
        record = json.loads((DATA / f"{fixture}.json").read_text(encoding="utf-8"))
        adapter = oatschema_adapters.get_adapter(schema, fmt)
        try:
            output = adapter.export(record, validate=False, **options)
        except Exception as error:
            results[case_id] = (None, type(error).__name__)
            continue
        results[case_id] = (output, None)
        if fmt in PARSE_FORMATS[schema]:
            try:
                parsed = adapter.parse(output, validate=False)
            except Exception as error:
                results[f"{case_id}.parsed"] = (None, type(error).__name__)
                continue
            text = json.dumps(parsed, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            results[f"{case_id}.parsed"] = (text, None)
    return results


RESULTS = _results()


def _expected(case_id: str) -> str | None:
    if INDEX.get(case_id, {"error": "missing"})["error"]:
        return None
    if case_id.endswith(".parsed"):
        path = EXPECTED / f"{case_id}.json"
    else:
        fmt = case_id.split(".")[-2]
        path = EXPECTED / f"{case_id}.{EXTENSIONS[fmt]}"
    return _normalise(path.read_bytes().decode("utf-8"))


@pytest.mark.parametrize("case_id", sorted(RESULTS))
def test_output_matches_0_4_3_except_listed_fixes(case_id: str) -> None:
    output, error = RESULTS[case_id]
    recorded = INDEX.get(case_id)
    expected = _expected(case_id)
    if case_id in CHANGED:
        assert error == RAISES_NOW.get(case_id), CHANGED[case_id]
        assert output != expected, CHANGED[case_id]
        return
    assert recorded is not None, f"{case_id} was not recorded"
    if recorded["error"]:
        assert error == recorded["error"]
    else:
        assert error is None
        assert output == expected


def test_every_listed_change_is_a_case() -> None:
    assert set(CHANGED) <= set(RESULTS)


def test_every_recorded_case_is_checked() -> None:
    assert set(INDEX) <= set(RESULTS)

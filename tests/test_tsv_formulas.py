# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import csv
import io
import itertools
from typing import Any

import pytest

from conftest import load
from oatschema_adapters import _tsv, get_adapter

TRIGGERS = ["=", "+", "-", "@", "\t", "\r"]
AUDIO = get_adapter("audio-transcription", "tsv")
DOCUMENT = get_adapter("document-extraction", "tsv")


def _cells(table: str) -> list[str]:
    return [cell for row in csv.reader(io.StringIO(table, newline=""), delimiter="\t") for cell in row]


def _is_number(cell: str) -> bool:
    try:
        float(cell)
    except ValueError:
        return False
    return True


def _runs_as_formula(cell: str) -> bool:
    return cell.startswith(tuple(TRIGGERS)) and not _is_number(cell)


@pytest.mark.parametrize("trigger", TRIGGERS)
def test_each_trigger_is_neutralised(trigger: str) -> None:
    cell = f"{trigger}HYPERLINK(1)"
    assert _tsv.neutralise(cell) == f"'{cell}"
    assert _tsv.restore(_tsv.neutralise(cell)) == cell


@pytest.mark.parametrize("cell", ["-5", "-12.5", "+3", "-1e3", "-.5", "1", "0.000", ""])
def test_numbers_and_empty_cells_are_left_alone(cell: str) -> None:
    assert _tsv.neutralise(cell) == cell


@pytest.mark.parametrize("cell", ["plain", "'Tis", "a=b", " =1", "'", "''", "'x=", "#tag", "-"])
def test_other_cells_are_left_alone_unless_they_start_with_a_trigger(cell: str) -> None:
    expected = "'-" if cell == "-" else cell
    assert _tsv.neutralise(cell) == expected


def test_neutralise_accepts_numbers_and_none() -> None:
    assert _tsv.neutralise(3) == "3"
    assert _tsv.neutralise(-2.5) == "-2.5"
    assert _tsv.neutralise(None) == ""


@pytest.mark.parametrize(
    "cell",
    [
        "".join(parts)
        for size in range(1, 4)
        for parts in itertools.product(["'", "=", "-", "x", "1", "\t"], repeat=size)
    ],
)
def test_restore_undoes_neutralise(cell: str) -> None:
    written = _tsv.neutralise(cell)
    assert not _runs_as_formula(written)
    assert _tsv.restore(written) == cell


def _hostile_audio() -> dict[str, Any]:
    return load("audio-transcription-formulas")


def _hostile_document() -> dict[str, Any]:
    record = load("document-extraction-formulas")
    record["blocks"][0]["block_type"] = "=cmd|'/C calc'!A0"
    record["blocks"][1]["page_number"] = "@SUM(1)"
    record["blocks"][2]["box"] = {"x": "=1+1", "y": "+2", "width": "-cmd", "height": "@x"}
    return record


@pytest.mark.parametrize("validate", [True, False])
@pytest.mark.parametrize("include_speakers", [True, False])
def test_no_audio_cell_runs_as_a_formula(validate: bool, include_speakers: bool) -> None:
    table = AUDIO.export(_hostile_audio(), validate=validate, include_speakers=include_speakers)
    assert not [cell for cell in _cells(table) if _runs_as_formula(cell)]
    assert "'=HYPERLINK" in table


def test_no_document_cell_runs_as_a_formula_validated() -> None:
    table = DOCUMENT.export(load("document-extraction-formulas"))
    assert not [cell for cell in _cells(table) if _runs_as_formula(cell)]


def test_no_document_cell_runs_as_a_formula_unvalidated() -> None:
    table = DOCUMENT.export(_hostile_document(), validate=False)
    cells = _cells(table)
    assert not [cell for cell in cells if _runs_as_formula(cell)]
    assert {"'=cmd|'/C calc'!A0", "'@SUM(1)", "'=1+1", "'-cmd", "'@x"} <= set(cells)


def test_negative_numbers_stay_numbers() -> None:
    table = DOCUMENT.export(load("document-extraction-formulas"))
    assert "\t-12.5\r\n" in table


def _carried(block: dict[str, Any]) -> dict[str, Any]:
    kept: dict[str, Any] = {key: block[key] for key in ("block_type", "text", "page_number", "box") if key in block}
    if block["block_type"] not in ("text", "line") and not kept.get("text"):
        kept.pop("text", None)
    return kept


@pytest.mark.parametrize(
    "fixture",
    [
        "document-extraction-formulas",
        "document-extraction-3",
        "document-extraction-per-mille",
        "document-extraction-text-only",
    ],
)
def test_document_round_trip(fixture: str) -> None:
    record = load(fixture)
    parsed = DOCUMENT.parse(DOCUMENT.export(record), unit=record.get("unit", "px"))
    assert parsed["blocks"] == [_carried(block) for block in record["blocks"]]
    assert parsed["unit"] == record.get("unit", "px")


def test_document_round_trip_with_an_empty_last_cell() -> None:
    record = load("document-extraction-formulas")
    table = DOCUMENT.export(record)
    assert table.endswith("2\tbox\t0\t0\t50\t50\t\r\n")
    assert DOCUMENT.parse(table)["blocks"][-1] == {
        "block_type": "box",
        "page_number": 2,
        "box": {"x": 0.0, "y": 0.0, "width": 50.0, "height": 50.0},
    }


def test_document_round_trip_unvalidated() -> None:
    record = _hostile_document()
    parsed = DOCUMENT.parse(DOCUMENT.export(record, validate=False), validate=False)
    assert parsed["blocks"][0]["block_type"] == "=cmd|'/C calc'!A0"
    assert "page_number" not in parsed["blocks"][1]
    assert [block.get("text") for block in parsed["blocks"][:8]] == [b["text"] for b in record["blocks"][:8]]


@pytest.mark.parametrize("include_speakers", [True, False])
def test_audio_round_trip(include_speakers: bool) -> None:
    record = _hostile_audio()
    parsed = AUDIO.parse(AUDIO.export(record, include_speakers=include_speakers))
    expected = []
    for segment in record["segments"]:
        kept: dict[str, Any] = {key: segment[key] for key in ("start_time", "end_time", "text")}
        name = segment.get("speaker", {}).get("name")
        if include_speakers and name:
            kept["speaker"] = {"id": name, "name": name}
        expected.append(kept)
    assert parsed["segments"] == expected
    assert parsed["text"] == " ".join(segment["text"] for segment in record["segments"])


def test_audio_round_trip_with_an_empty_last_cell() -> None:
    record = _hostile_audio()
    table = AUDIO.export(record, include_speakers=True)
    assert table.endswith("plain = fine\t\r\n")
    last = AUDIO.parse(table)["segments"][-1]
    assert last == {"start_time": 7.0, "end_time": 8.0, "text": "plain = fine"}


def test_tsv_parsers_ignore_surrounding_blank_lines() -> None:
    table = "\r\n\nstart_time\tend_time\ttext\tspeaker\r\n1.000\t2.000\thi\t\r\n\r\n\n"
    assert AUDIO.parse(table)["segments"] == [{"start_time": 1.0, "end_time": 2.0, "text": "hi"}]


@pytest.mark.parametrize("content", ["", " \r\n\t\n"])
def test_empty_tables_raise(content: str) -> None:
    with pytest.raises(ValueError, match="Provided TSV content is empty."):
        AUDIO.parse(content)
    with pytest.raises(ValueError, match="Provided TSV content is empty."):
        DOCUMENT.parse(content)


def test_audio_times_must_be_numbers() -> None:
    with pytest.raises(ValueError, match="TSV times must be numbers"):
        AUDIO.parse("start_time\tend_time\ttext\r\nsoon\t2\thi\r\n")


def test_audio_missing_end_time_uses_start_time() -> None:
    parsed = AUDIO.parse("start_time\ttext\r\n1.5\thi\r\n")
    assert parsed["segments"] == [{"start_time": 1.5, "end_time": 1.5, "text": "hi"}]

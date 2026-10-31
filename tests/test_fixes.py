# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

"""The defects fixed since dorsalhub-adapters 0.4.3."""

import copy
import re
from typing import Any

import pytest
import srt
import webvtt
import yaml

from conftest import load
from oatschema_adapters import get_adapter
from oatschema_adapters._frontmatter import scalar
from oatschema_adapters.audio._time import clock, parse_clock, split_milliseconds


def _bboxes(hocr: str) -> list[tuple[int, ...]]:
    return [tuple(map(int, match)) for match in re.findall(r'title="bbox (\d+) (\d+) (\d+) (\d+)', hocr)]


@pytest.mark.parametrize(
    ("unit", "box", "page", "expected"),
    [
        ("normalized", {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.25}, (600, 800), (60, 160, 360, 360)),
        ("normalized", {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.25}, None, (100, 200, 600, 450)),
        ("per_mille", {"x": 100, "y": 200, "width": 500, "height": 250}, (600, 800), (60, 160, 360, 360)),
        ("per_mille", {"x": 100, "y": 200, "width": 500, "height": 250}, None, (100, 200, 600, 450)),
        ("px", {"x": 10.7, "y": 20.2, "width": 30, "height": 40}, (600, 800), (10, 20, 40, 60)),
        ("pt", {"x": 10, "y": 20, "width": 30, "height": 40}, (612, 792), (10, 20, 40, 60)),
    ],
)
def test_hocr_scales_relative_units_to_the_page(
    unit: str, box: dict[str, float], page: tuple[int, int] | None, expected: tuple[int, ...]
) -> None:
    record: dict[str, Any] = {"unit": unit, "blocks": [{"block_type": "box", "text": "t", "box": box}]}
    if page:
        record["page_width"], record["page_height"] = page
    hocr = get_adapter("document-extraction", "hocr").export(record)
    width, height = page or (1000, 1000)
    assert _bboxes(hocr) == [(0, 0, width, height), expected]


def test_hocr_scales_polygons_per_page() -> None:
    record = {
        "unit": "normalized",
        "page_width": [{"value": 100, "pages": [1]}, {"value": 200, "pages": [2]}],
        "page_height": 50,
        "blocks": [
            {"block_type": "polygon", "text": "a", "page_number": 1, "polygon": [{"x": 0.5, "y": 0.5}] * 3},
            {"block_type": "multi_polygon", "text": "b", "page_number": 2, "multi_polygon": [[{"x": 0.5, "y": 1}] * 3]},
        ],
    }
    adapter = get_adapter("document-extraction", "hocr")
    hocr = adapter.export(record)
    assert _bboxes(hocr) == [(0, 0, 100, 50), (50, 25, 50, 25), (0, 0, 200, 50), (100, 50, 100, 50)]
    parsed = adapter.parse(hocr)
    assert parsed["blocks"][0]["polygon"] == [{"x": 50.0, "y": 25.0}] * 3
    assert parsed["blocks"][1]["multi_polygon"] == [[{"x": 100.0, "y": 50.0}] * 3]


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00.000"),
        (59.9996, "00:01:00.000"),
        (59.9994, "00:00:59.999"),
        (3599.9996, "01:00:00.000"),
        (8.2255, "00:00:08.226"),
        (1.0005, "00:00:01.000"),
        (360000.5, "100:00:00.500"),
    ],
)
def test_clock_rounds_to_the_millisecond_before_splitting(seconds: float, expected: str) -> None:
    assert clock(seconds) == expected
    assert f"{seconds % 60:06.3f}"[-3:] == expected[-3:] or expected.endswith("00.000")


@pytest.mark.parametrize("seconds", [-0.5, float("nan"), float("inf")])
def test_clock_rejects_impossible_times(seconds: float) -> None:
    with pytest.raises(ValueError, match="a time must be a finite number of seconds"):
        split_milliseconds(seconds)


@pytest.mark.parametrize("text", ["", "1:2:3:4", "a:b", "-1", "::", "nan"])
def test_parse_clock_rejects_non_times(text: str) -> None:
    with pytest.raises(ValueError):
        parse_clock(text)


def test_vtt_near_a_minute_is_valid_webvtt() -> None:
    record = load("audio-transcription-2")
    output = get_adapter("audio-transcription", "vtt").export(record)
    assert "00:01:00.000 --> 00:01:01.000" in output
    assert "01:00:00.000 --> 01:00:00.250" in output
    captions = webvtt.from_string(output).captions
    assert {"00:01:00.000", "01:00:00.000"} <= {caption.start for caption in captions}


def test_srt_near_a_minute_is_valid_srt() -> None:
    output = get_adapter("audio-transcription", "srt").export(load("audio-transcription-2"))
    assert "00:00:59,999 --> 00:01:01,000" in output
    assert [s.start.total_seconds() for s in srt.parse(output)][:1] == [59.999]


def test_markdown_milliseconds_round_and_parse_back() -> None:
    adapter = get_adapter("audio-transcription", "md")
    output = adapter.export(load("audio-transcription-2"), include_milliseconds=True)
    assert "**[01:00.000 - 01:01.000]**" in output
    assert "**[01:00:00.000 - 01:00:00.250]**" in output
    segments = adapter.parse(output)["segments"]
    assert [segment["start_time"] for segment in segments] == [60.0, 3600.0, 3725.25]
    assert segments[1]["events"] == ["applause", "music"]


def test_markdown_events_belong_to_their_segment() -> None:
    adapter = get_adapter("audio-transcription", "md")
    parsed = adapter.parse(adapter.export(load("audio-transcription-1")))
    assert [segment.get("events") for segment in parsed["segments"]] == [["music"], None, None, ["laughter"], None]
    assert all(segment["end_time"] > 0 for segment in parsed["segments"])


def test_markdown_trailing_events_become_an_event_segment() -> None:
    parsed = get_adapter("audio-transcription", "md").parse("# Transcription\n\n**[00:01 - 00:02]** Hi\n\n> *[music]*")
    assert parsed["segments"][-1] == {"start_time": 0.0, "end_time": 0.0, "text": "", "events": ["music"]}


def test_hocr_attributes_are_strings_with_their_case() -> None:
    hocr = '<div class="ocr_page"><span class="ocr_line" data-myKey="42" data-Flag=\'true\' data-list="[1, 2]">T</span></div>'
    attributes = get_adapter("document-extraction", "hocr").parse(hocr)["blocks"][0]["attributes"]
    assert attributes == {"hocr_class": "ocr_line", "myKey": "42", "Flag": "true", "list": "[1, 2]"}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("<html><body><p>Not hOCR</p></body></html>", "The content has no hOCR elements"),
        ("plain text", "The content has no hOCR elements"),
        ('<div class="ocr_page" title="bbox 0 0 10 10"></div>', "no 'ocr_line' elements with text"),
        ('<div class="ocr_page"><span class="ocrx_word">w</span></div>', "no 'ocr_line' elements with text"),
        ('<div class="ocr_page"><span class="ocr_line">  </span></div>', "no 'ocr_line' elements with text"),
    ],
)
def test_from_hocr_rejects_content_without_blocks(content: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        get_adapter("document-extraction", "hocr").parse(content, validate=False)


def test_from_hocr_target_class() -> None:
    hocr = '<div class="ocr_page"><span class="ocr_line"><span class="ocrx_word">a</span> <span class="ocrx_word">b</span></span></div>'
    parsed = get_adapter("document-extraction", "hocr").parse(hocr, target_class="ocrx_word")
    assert [block["text"] for block in parsed["blocks"]] == ["a", "b"]


def _boxes(*boxes: tuple[int, int, int, int]) -> dict[str, Any]:
    return {
        "unit": "px",
        "blocks": [
            {"block_type": "text", "text": f"b{i}", "box": {"x": x, "y": y, "width": w, "height": h}}
            for i, (x, y, w, h) in enumerate(boxes)
        ],
    }


def test_grid_gap_x_is_used() -> None:
    adapter = get_adapter("document-extraction", "html")
    side_by_side = _boxes((0, 0, 100, 50), (500, 30, 100, 50))
    assert "layout-x" in adapter.export(side_by_side, layout="grid", fragment=True)
    assert "layout-x" not in adapter.export(side_by_side, layout="grid", fragment=True, gap_x=1000)


def test_grid_gap_y_is_used() -> None:
    adapter = get_adapter("document-extraction", "html")
    stacked = _boxes((0, 0, 100, 10), (0, 40, 100, 10))
    assert "layout-y" in adapter.export(stacked, layout="grid", fragment=True)
    assert "layout-y" not in adapter.export(stacked, layout="grid", fragment=True, gap_y=1000)


@pytest.mark.parametrize("fragment", [True, False])
def test_invalid_layout_raises_even_without_pages(fragment: bool) -> None:
    with pytest.raises(ValueError, match="option 'layout' must be"):
        get_adapter("document-extraction", "html").export({"blocks": []}, layout="columns", fragment=fragment)


def test_document_from_tsv_unit() -> None:
    adapter = get_adapter("document-extraction", "tsv")
    table = adapter.export(load("document-extraction-per-mille"))
    assert adapter.parse(table)["unit"] == "px"
    assert adapter.parse(table, unit="per_mille")["unit"] == "per_mille"
    with pytest.raises(ValueError, match="option 'unit' must be 'px' or 'pt' or 'normalized' or 'per_mille'"):
        adapter.parse(table, unit="cm")


def test_to_hocr_does_not_change_its_input() -> None:
    record = load("document-extraction-hostile")
    original = copy.deepcopy(record)
    get_adapter("document-extraction", "hocr").export(record)
    assert record == original


@pytest.mark.parametrize(
    "value",
    [
        "plain",
        "Jean-Pierre",
        "café au lait",
        "large-v3 (beam 5)",
        "a: b",
        "x # y",
        "#tag",
        "- item",
        "1",
        "1.5",
        "1e3",
        "0x1F",
        "2026-10-31",
        "12:30",
        "yes",
        "No",
        "TRUE",
        "null",
        "~",
        "",
        " padded ",
        "line\nbreak",
        "tab\there",
        "'quoted'",
        '"double"',
        "{a: 1}",
        "[1]",
        "*alias",
        "&anchor",
        "!tag",
        "|",
        ">",
        "%directive",
        "@at",
        "`tick`",
        "back\\slash",
        "\u2028",
        "=",
        "<<",
        ".inf",
        "-.NaN",
        "bell\x07",
    ],
)
def test_frontmatter_scalars_read_back_as_written(value: str) -> None:
    assert yaml.safe_load(f"key: {scalar(value)}") == {"key": value}


@pytest.mark.parametrize("value", [3, 2.5, 0, True, False, None])
def test_frontmatter_non_string_scalars(value: Any) -> None:
    assert yaml.safe_load(f"key: {scalar(value)}") == {"key": value}


@pytest.mark.parametrize(
    ("schema", "fixture"),
    [
        ("audio-transcription", "audio-transcription-2"),
        ("audio-transcription", "audio-transcription-formulas"),
        ("document-extraction", "document-extraction-3"),
        ("document-extraction", "document-extraction-hostile"),
    ],
)
def test_frontmatter_reads_back_as_the_record(schema: str, fixture: str) -> None:
    record = load(fixture)
    output = get_adapter(schema, "md").export(record)
    header = yaml.safe_load(output.split("---\n")[1])
    keys = ("producer", "language", "duration", "score_explanation", "track_id", "extraction_type", "unit")
    assert {key: header[key] for key in keys if key in header} == {key: record[key] for key in keys if key in record}
    assert header.get("attributes") == record.get("attributes")


def test_from_hocr_reads_text_after_void_elements() -> None:
    hocr = '<div class="ocr_page"><span class="ocr_line">foo<br>bar<img src="x">baz</span></div>'
    assert get_adapter("document-extraction", "hocr").parse(hocr)["blocks"][0]["text"] == "foo barbaz"


def test_unicode_digits_are_not_numbers_in_tsv() -> None:
    from oatschema_adapters._tsv import neutralise

    assert neutralise("-\u0661\u0662") == "'-\u0661\u0662"


VTT_TEXTS = [
    "AT&T <3 <b>bold</b> & more",
    "a --> b",
    "first\n\n00:00:09.000 --> 00:00:10.000\ninjected",
    "one\n  \n\ntwo",
    "&amp; stays literal",
]


@pytest.mark.parametrize("text", VTT_TEXTS)
def test_vtt_text_cannot_end_or_add_a_caption(text: str) -> None:
    adapter = get_adapter("audio-transcription", "vtt")
    record = {
        "segments": [
            {"text": text, "start_time": 1.0, "end_time": 2.0, "speaker": {"id": "s", "name": "A & <B>\n-->"}},
            {"text": "after", "start_time": 3.0, "end_time": 4.0},
        ]
    }
    output = adapter.export(record, include_speakers=True)
    assert output.count("-->") == 2
    assert "\n\n\n" not in output
    captions = webvtt.from_string(output).captions
    assert len(captions) == 2
    parsed = adapter.parse(output)
    assert [segment["text"] for segment in parsed["segments"]] == [" ".join(text.split()), "after"]
    assert parsed["segments"][0]["speaker"] == {"id": "A & <B> -->", "name": "A & <B> -->"}

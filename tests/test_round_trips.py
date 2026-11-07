# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import random
from typing import Any

import oatschema
import pytest
import srt

from conftest import load
from oatschema_adapters import _tsv, get_adapter, list_formats
from oatschema_adapters.audio._srt import _read_subtitles
from oatschema_adapters.audio import from_srt, from_tsv, from_vtt, to_srt, to_tsv, to_vtt
from oatschema_adapters.document import from_tsv as from_document_tsv
from oatschema_adapters.document import to_md, to_tsv as to_document_tsv

TRIANGLE = [{"x": 0.5, "y": 1}, {"x": 100.25, "y": 2}, {"x": 3, "y": 1e-7}]
SQUARE = [{"x": 10, "y": 10}, {"x": 20, "y": 10}, {"x": 20, "y": 20}, {"x": 10, "y": 20}]
MAX = 9007199254740991


def _document(**block: Any) -> dict[str, Any]:
    return {"extraction_type": "mixed", "unit": "px", "blocks": [block]}


@pytest.mark.parametrize(
    "block",
    [
        {"block_type": "polygon", "polygon": TRIANGLE},
        {"block_type": "polygon", "polygon": TRIANGLE, "text": "=SUM(A1)"},
        {"block_type": "multi_polygon", "multi_polygon": [TRIANGLE, SQUARE]},
        {"block_type": "multi_polygon", "multi_polygon": [TRIANGLE]},
        {"block_type": "line", "polygon": TRIANGLE, "text": "a line"},
        {
            "block_type": "text",
            "text": "both",
            "polygon": TRIANGLE,
            "box": {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0},
        },
        {"block_type": "polygon", "polygon": [{"x": MAX, "y": MAX}] * 3},
    ],
)
@pytest.mark.parametrize("version", ["0.5.0", "0.8.0", oatschema.SCHEMA_VERSION])
def test_polygons_round_trip_through_tsv(block: dict[str, Any], version: str) -> None:
    record = _document(**block)
    table = to_document_tsv(record, schema_version=version)
    assert table.splitlines()[0].endswith("\ttext\tpolygon")
    parsed = from_document_tsv(table, schema_version=version)
    assert parsed["blocks"] == [block]
    assert parsed["unit"] == "px"


def test_polygons_round_trip_at_the_oldest_version() -> None:
    block = {"block_type": "polygon", "polygon": TRIANGLE, "text": "t"}
    table = to_document_tsv(_document(**block), schema_version="0.4.0")
    assert from_document_tsv(table, schema_version="0.4.0")["blocks"] == [block]


def test_the_polygon_column_appears_only_when_needed() -> None:
    plain = _document(block_type="text", text="hi")
    assert to_document_tsv(plain).splitlines()[0] == "page_number\tblock_type\tx\ty\twidth\theight\ttext"
    mixed = {
        "extraction_type": "mixed",
        "unit": "px",
        "blocks": [{"block_type": "text", "text": "hi"}, {"block_type": "polygon", "polygon": TRIANGLE}],
    }
    assert from_document_tsv(to_document_tsv(mixed))["blocks"] == mixed["blocks"]


def test_box_columns_hold_the_bounding_box_of_a_polygon() -> None:
    table = to_document_tsv(_document(block_type="polygon", polygon=SQUARE))
    row = table.splitlines()[1].split("\t")
    assert row[2:6] == ["10.0", "10.0", "10.0", "10.0"]
    assert row[7] == "[[10,10],[20,10],[20,20],[10,20]]"


def test_a_polygon_cell_survives_neutralising_and_is_not_quoted() -> None:
    cell = "[[1,2],[3,4],[5,6]]"
    assert _tsv.neutralise(cell) == cell
    table = to_document_tsv(
        _document(block_type="polygon", polygon=[{"x": 1, "y": 2}, {"x": 3, "y": 4}, {"x": 5, "y": 6}])
    )
    assert cell in table


def test_the_largest_multi_polygon_round_trips_at_its_full_precision() -> None:
    point = {"x": 1234567.0000000002, "y": 7654321.000000001}
    block = {"block_type": "multi_polygon", "multi_polygon": [[point] * 1000] * 100}
    table = to_document_tsv(_document(**block))
    assert len(table) > 131072
    assert from_document_tsv(table)["blocks"] == [block]


def test_polygon_tsv_of_invalid_geometry_still_exports_unvalidated() -> None:
    table = to_document_tsv(_document(block_type="polygon", polygon=[{"x": 1}]), validate=False)
    assert "polygon" not in table.splitlines()[0]


def test_old_tables_without_a_polygon_column_still_parse() -> None:
    table = "page_number\tblock_type\tx\ty\twidth\theight\ttext\n1\tbox\t1\t2\t3\t4\thi\n"
    assert from_document_tsv(table)["blocks"][0]["box"] == {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}


def _speakers() -> dict[str, Any]:
    return {
        "segments": [
            {"text": "Hello: there", "start_time": 0.5, "end_time": 1.0, "speaker": {"id": "s1", "name": "Maria"}},
            {"text": "No speaker", "start_time": 1.0, "end_time": 2.0},
            {"text": "Same", "start_time": 2.0, "end_time": 3.0, "speaker": {"id": "Jean", "name": "Jean"}},
        ]
    }


def test_from_srt_reads_speakers_only_when_asked() -> None:
    subtitles = to_srt(_speakers(), include_speakers=True)
    plain = from_srt(subtitles)
    assert plain["segments"][0]["text"] == "Maria: Hello: there"
    assert "speaker" not in plain["segments"][0]
    with_speakers = from_srt(subtitles, include_speakers=True)
    first, _, third = with_speakers["segments"]
    assert first["text"] == "Hello: there"
    assert first["speaker"] == {"id": "Maria", "name": "Maria"}
    assert third["speaker"] == {"id": "Jean", "name": "Jean"}
    assert with_speakers["text"] == "Hello: there No speaker Same"


def test_from_srt_keeps_a_time_like_prefix_as_text_when_its_not_a_speaker() -> None:
    parsed = from_srt("1\n00:00:01,000 --> 00:00:02,000\n12:30 is late\n", include_speakers=True)
    assert parsed["segments"][0]["text"] == "12:30 is late"
    assert "speaker" not in parsed["segments"][0]


def test_tsv_keeps_speaker_ids_that_differ_from_names() -> None:
    table = to_tsv(_speakers(), include_speakers=True)
    assert table.splitlines()[0] == "start_time\tend_time\ttext\tspeaker\tspeaker_id"
    parsed = from_tsv(table)
    assert parsed["segments"][0]["speaker"] == {"id": "s1", "name": "Maria"}
    assert "speaker" not in parsed["segments"][1]
    assert parsed["segments"][2]["speaker"] == {"id": "Jean", "name": "Jean"}


def test_tsv_has_no_speaker_id_column_when_ids_are_names() -> None:
    record = {"segments": [{"text": "a", "start_time": 0, "end_time": 1, "speaker": {"id": "A", "name": "A"}}]}
    assert to_tsv(record, include_speakers=True).splitlines()[0] == "start_time\tend_time\ttext\tspeaker"
    assert from_tsv(to_tsv(record, include_speakers=True))["segments"][0]["speaker"] == {"id": "A", "name": "A"}


def test_tsv_keeps_a_speaker_with_an_id_and_no_name() -> None:
    record = {"segments": [{"text": "a", "start_time": 0, "end_time": 1, "speaker": {"id": "0"}}]}
    assert from_tsv(to_tsv(record, include_speakers=True))["segments"][0]["speaker"] == {"id": "0"}


def test_vtt_speakers_round_trip_with_the_name_as_the_id() -> None:
    parsed = from_vtt(to_vtt(_speakers(), include_speakers=True))
    assert parsed["segments"][0]["speaker"] == {"id": "Maria", "name": "Maria"}


def test_audio_markdown_keeps_its_frontmatter() -> None:
    adapter = get_adapter("audio-transcription", "md")
    record = load("audio-transcription-2")
    parsed = adapter.parse(adapter.export(record))
    for key in ("producer", "language", "duration", "score_explanation", "track_id", "attributes"):
        assert parsed[key] == record[key], key
    oatschema.validate(parsed, "audio-transcription")


def test_audio_markdown_producer_option_wins_over_frontmatter() -> None:
    adapter = get_adapter("audio-transcription", "md")
    content = adapter.export({"text": "hi", "producer": "written"})
    assert adapter.parse(content)["producer"] == "written"
    assert adapter.parse(content, producer="mine")["producer"] == "mine"
    assert adapter.parse("no frontmatter")["producer"] == "md-adapter"


def test_markdown_of_no_blocks_matches_html() -> None:
    record = {"producer": "p", "extraction_type": "text", "blocks": []}
    assert "No content extracted from this document." in to_md(record)
    assert "No content extracted from this document." in get_adapter("document-extraction", "html").export(record)
    for fmt in ("txt", "tsv", "hocr"):
        with pytest.raises(ValueError, match="no 'blocks'"):
            get_adapter("document-extraction", fmt).export(record)


@pytest.mark.parametrize("version", oatschema.available_versions())
@pytest.mark.parametrize(
    ("schema", "fixture"),
    [("audio-transcription", "audio-transcription-1"), ("document-extraction", "document-extraction-3")],
)
def test_validating_at_a_records_version_never_changes_its_bytes(schema: str, fixture: str, version: str) -> None:
    record = load(fixture)
    if not oatschema.is_valid(record, schema, version):  # type: ignore[arg-type]
        pytest.skip("not valid at this version")
    for fmt, _ in list_formats(schema):
        adapter = get_adapter(schema, fmt)
        assert adapter.export(record, schema_version=version) == adapter.export(record, validate=False)


def test_srt_parser_reads_what_the_srt_library_writes() -> None:
    content = (
        "\ufeff\n1\r\n00:00:01,000 --> 00:00:02,500 X1:10\r\nfirst\r\nline\r\n\r\n"
        "2\n00:00:03.000 --> 00:00:04.000\n\ninside a blank\n\n\n"
        "00:00:05,000 --> 00:00:06,000\nno index\n3\n00:00:07,000 --> 00:00:08,000\nno blank before\n"
    )
    assert _read_subtitles(content) == [
        (1.0, 2.5, "first\nline"),
        (3.0, 4.0, "\ninside a blank"),
        (5.0, 6.0, "no index"),
        (7.0, 8.0, "no blank before"),
    ]


def test_arrows_in_subtitle_text_are_still_text() -> None:
    parsed = from_srt("1\n00:00:01,000 --> 00:00:02,000\nA --> B\nA1 --> B2\n1 --> 2\nnan --> inf\n")
    assert parsed["segments"][0]["text"] == "A --> B A1 --> B2 1 --> 2 nan --> inf"


T1 = "00:00:01,000 --> 00:00:02,000"
T2 = "00:00:03,000 --> 00:00:04,000"
SRT_CASES = [
    f"{T1}\n1984\n\n{T2}\nb\n",
    f"1\n{T1}\n42\n\n\n{T2}\nb\n",
    f"1\n{T1}\n00:00:05,000 --> 00:00:06,000 hello\n",
    f"1\n{T1}\nline\n{T2}\nb\n",
    f"1\n{T1}\nline\n2\n{T2}\nb\n",
    f"1\n{T1}\n\n2\n{T2}\nb\n",
    f"1\n{T1}\n2\n{T2}\nb\n",
    f"1\n{T1}\n\n{T2}\nb\n",
    f"1\n{T1}\n\n\n{T2}\nb\n",
    f"1\n{T1}\nx\n42\n\n{T2}\nb\n",
    f"1\n{T1}\nx\n\n 2\n{T2}\nb\n",
    f"1\n{T1}\nx\n  \n{T2}\nb\n",
    f"1\n{T1} X1:10\nx\n\n2.5\n00:00:03.000 - > 00:00:04.000\nb",
    f"\n\n {T1}\nx\n",
    f"\ufeff1\r\n{T1}\r\nx\r\n\r\n2\r\n{T2}\r\ny\r\n",
    "00：00：01，000 --> 00.00.02.500\nx\n",
    "00:00:01 --> 00:00:02\nx\n",
    "",
    "\n \n",
]


def _library(content: str) -> list[tuple[float, float, str]]:
    return [
        (item.start.total_seconds(), item.end.total_seconds(), item.content.replace("\n", " ").strip())
        for item in srt.parse(content)
    ]


def _ours(content: str) -> list[tuple[float, float, str]]:
    return [(start, end, text.replace("\n", " ").strip()) for start, end, text in _read_subtitles(content)]


@pytest.mark.parametrize("content", SRT_CASES)
def test_the_srt_reader_matches_the_library(content: str) -> None:
    assert _ours(content) == _library(content)


def test_the_srt_reader_matches_the_library_on_generated_files() -> None:
    generator = random.Random(11)
    pieces = [
        T1,
        T2,
        f"{T1} tail",
        "1",
        "22",
        "2.5",
        "-3",
        "x",
        "text here",
        "1984",
        "",
        "",
        " ",
        "1 ",
        "a --> b",
        "00:00:0x,000 --> 1",
        "1:2:3 words",
        f"{T1}\r",
    ]
    for _ in range(20_000):
        content = "\n".join(generator.choices(pieces, k=generator.randint(0, 9)))
        try:
            expected = _library(content)
        except srt.SRTParseError:
            with pytest.raises(ValueError):
                _read_subtitles(content)
            continue
        assert _ours(content) == expected, repr(content)

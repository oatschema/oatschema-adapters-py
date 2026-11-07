# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import csv
import gzip
import io
import json
import random
import re
import time
import tracemalloc
from pathlib import Path
from typing import Any

import oatschema
import pytest

from oatschema_adapters import ParsedRecord, get_adapter

AUDIO = "audio-transcription"
DOCUMENT = "document-extraction"
LONG = "z" * 200_000
LIMIT = 1200


MALFORMED = [
    (AUDIO, "tsv", f"start_time\ttext\n{LONG}\thi\n"),
    (AUDIO, "tsv", f"start_time\tend_time\ttext\n1\t{LONG}\thi\n"),
    (AUDIO, "vtt", LONG),
    (AUDIO, "srt", f"1\n{LONG}\n"),
    (AUDIO, "srt", "1\n99999999999999999:00:00,000 --> 99999999999999999:00:01,000\nhi\n"),
    (AUDIO, "md", "**[" + "1" * 200_000 + " - 2]** hi"),
    (AUDIO, "md", "**[1.2.3 - 2]** hi"),
    (AUDIO, "md", "**[1:" + "1" * 400 + " - 2]** hi"),
    (AUDIO, "md", "---\nduration: " + "1" * 5000 + "\n---\n\nhi"),
    (AUDIO, "json", LONG),
    (AUDIO, "json", "[" * 200_000),
    (AUDIO, "json", f'["{LONG}"]'),
    (DOCUMENT, "tsv", f"x\ty\twidth\theight\ttext\n{LONG}\t0\t1\t1\thi\n"),
    (DOCUMENT, "tsv", "page_number\ttext\n1.5\thi\n"),
    (DOCUMENT, "tsv", "page_number\ttext\n" + "1" * 200_000 + ".5\thi\n"),
    (DOCUMENT, "tsv", "page_number\ttext\n" + "9" * 5000 + "\thi\n"),
    (DOCUMENT, "tsv", f"polygon\ttext\n{LONG}\thi\n"),
    (DOCUMENT, "tsv", "polygon\ttext\n" + "[" * 200_000 + "\thi\n"),
    (DOCUMENT, "tsv", "polygon\ttext\n[[1,2],[3,4,5]]\thi\n"),
    (DOCUMENT, "tsv", "polygon\ttext\n1\thi\n"),
    (DOCUMENT, "tsv", 'text\n"' + "z" * (17 * 1024 * 1024) + '"\n'),
    (DOCUMENT, "tsv", "\t".join(["text"] * 300) + "\nhi\n"),
    (DOCUMENT, "tsv", "text\t" + "x\tx\ty\twidth\theight\n" + "hi\t1e400\t5\t0\t1\t1\n"),
    (AUDIO, "tsv", "start_time\tstart_time\ttext\nnan\t1\thi\n"),
    (AUDIO, "json", '{"' + "K" * 5000 + '": 1}'),
    (AUDIO, "json", "[" * 1000 + "]" * 1000),
    (AUDIO, "md", "---\nduration: 5\nduration: 7\n---\n\nhi"),
    (AUDIO, "md", "---\nattributes:\n  a: 1\n  a: 2\n---\n\nhi"),
    (AUDIO, "md", "**[nan - inf]** hi"),
    (AUDIO, "md", "**[1e400 - 2]** hi"),
    (AUDIO, "vtt", "WEBVTT\n\nnan --> inf\nbad\n\n00:03.000 --> 00:04.000\ngood\n"),
    (AUDIO, "vtt", "WEBVTT\n\n99999:01.000 --> 00:02.000\nbad\n"),
    (AUDIO, "srt", "1\nnan --> inf\nbad\n"),
    (AUDIO, "srt", "1\n"),
    (AUDIO, "srt", "1\n00:00:01,000 --> 00:00:02,000\ngood\n\n2\n00:00:0x,000 --> 00:00:03,000\nbad\n"),
    (AUDIO, "srt", "1\n00:00:01,000 --> 00:00:02,000\ngood\n\n00:00:03,000 -> 00:00:04,000\nbad\n"),
    (AUDIO, "vtt", "WEBVTT\n\n00:01.000 --> 00:02.000\na\n00:03.000 --> 00:04.000\nb\n\nnan --> inf\nbad\n"),
    (AUDIO, "vtt", "WEBVTT\n\nnan --> inf\nbad\n\nNOTE\n00:01.000 --> 00:02.000\nx\n"),
    (AUDIO, "vtt", "WEBVTT\n\nnan --> inf\nbad\n\nSTYLE\n00:01.000 --> 00:02.000\nx\n"),
    (AUDIO, "vtt", "WEBVTT\n00:01.000 --> 00:02.000\nx\n\nnan --> inf\nbad\n"),
    (AUDIO, "srt", "1\n1.5\n00:00:01,000 --> 00:00:02,000\nbad\n"),
    (AUDIO, "srt", "00:00:01,1234567 --> 00:00:02,000\nbad\n"),
    (AUDIO, "vtt", "WEBVTT\n\n00:01.000 -> 00:02.000\nlost\n\n00:03.000 --> 00:04.000\nb\n"),
    (AUDIO, "vtt", "WEBVTT\n\nNOTES\n00:01.000 --> 00:02.000\nx\n\nnan --> inf\nbad\n"),
    (AUDIO, "vtt", f"WEBVTT\n\n{LONG}\n"),
    (AUDIO, "srt", "1\n23999999975:59:59,123 --> 23999999975:59:59,999\nhi\n"),
    (DOCUMENT, "tsv", "page_number\ttext\n1,000\thi\n"),
    (DOCUMENT, "hocr", '<span class="ocr_line" title="bbox 1 2 3">hi</span>'),
    (DOCUMENT, "hocr", '<span class="ocr_line" title="bbox 1 2 3 4 5">hi</span>'),
    (DOCUMENT, "hocr", '<span class="ocr_line" title="x_wconf 50 60">hi</span>'),
    (DOCUMENT, "hocr", '<span class="ocr_line" title="x_wconf 50; x_wconf 60">hi</span>'),
    (DOCUMENT, "hocr", '<span class="ocr_line" title="bbox 1 2 3 4; bbox 5 6 7 8">hi</span>'),
    (DOCUMENT, "hocr", '<span class="ocr_line" title="bbox -1.7e308 0 1.7e308 1">hi</span>'),
    (
        DOCUMENT,
        "hocr",
        '<div class="ocr_page" id="page_1" title="bbox 0 0 10 10"><span class="ocr_line">a</span></div>'
        '<div class="ocr_page" id="page_1" title="bbox 0 0 99 99"><span class="ocr_line">b</span></div>',
    ),
    (DOCUMENT, "hocr", f'<span class="ocr_line" title="bbox {LONG} 0 1 1">hi</span>'),
    (DOCUMENT, "hocr", f"""<span class="ocr_line" data-polygon='{LONG}'>hi</span>"""),
    (DOCUMENT, "hocr", '<div class="ocr_page" id="p' + "9" * 5000 + '"><span class="ocr_line">hi</span></div>'),
    (DOCUMENT, "hocr", "<div>" * 5000),
    (DOCUMENT, "hocr", '<span class="ocr_line">' * 200 + "x" * 100_000 + "</span>" * 200),
    (DOCUMENT, "json", "[1]"),
]


def _chain_is_bounded(error: BaseException | None) -> bool:
    while error is not None:
        if any(len(str(value)) > LIMIT for value in vars(error).values()) or len(str(error)) > LIMIT:
            return False
        error = error.__cause__ or error.__context__
    return True


@pytest.mark.parametrize(("schema", "fmt", "content"), MALFORMED)
@pytest.mark.parametrize("validate", [True, False])
def test_malformed_content_fails_with_a_bounded_value_error(
    schema: str, fmt: str, content: str, validate: bool
) -> None:
    with pytest.raises(ValueError) as caught:
        get_adapter(schema, fmt).parse(content, validate=validate)
    assert _chain_is_bounded(caught.value)


def test_over_long_values_fail_validation_without_quoting_them() -> None:
    with pytest.raises(oatschema.ValidationError) as caught:
        get_adapter(AUDIO, "tsv").parse(f"start_time\ttext\n1\t{LONG[:100_000]}\n")
    assert _chain_is_bounded(caught.value)


def test_a_wide_header_cant_multiply_short_rows() -> None:
    header = "\t".join(f"c{i}" for i in range(200_000))
    with pytest.raises(ValueError, match="at most 256 cells in a row"):
        get_adapter(DOCUMENT, "tsv").parse(f"text\t{header}\n" + "hi\n" * 200_000)


def test_rows_longer_than_the_header_are_cut() -> None:
    assert get_adapter(DOCUMENT, "tsv").parse("text\nhi\t" + "\t".join("x" * 255) + "\n")["blocks"][0]["text"] == "hi"


@pytest.mark.parametrize("separator", ["\t", '\t""'])
def test_a_wide_data_row_is_refused_before_it_is_split(separator: str) -> None:
    content = "start_time\ttext\n1\thi\n" + "ab" + (separator + "ab") * 3_000_000 + "\n"
    tracemalloc.start()
    try:
        with pytest.raises(ValueError, match="at most 256 cells in a row"):
            get_adapter(AUDIO, "tsv").parse(content)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 4 * len(content)


def test_tabs_and_line_breaks_inside_a_quoted_cell_dont_count_as_cells() -> None:
    from oatschema_adapters import _tsv

    text = "a" + "\tb" * 1000 + "\n" + "\tc" * 1000
    assert _tsv.read(f'text\n"{text}"\n', ["text"])[1] == [{"text": text}]


def test_the_row_width_check_agrees_with_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    from oatschema_adapters import _tsv

    monkeypatch.setattr(_tsv, "_RECORD", re.compile(_tsv._RECORD.pattern.replace("{0,255}", "{0,2}")))
    rnd = random.Random(7)
    for _ in range(20_000):
        content = "".join(rnd.choice('a\t\t"\r\n ') for _ in range(rnd.randint(1, 24))).strip("\r\n")
        if not content.strip():
            continue
        try:
            rows = list(csv.reader(io.StringIO(content, newline=""), delimiter="\t"))
        except csv.Error:
            continue
        expected = max((len(row) for row in rows), default=0) > 3
        assert _tsv._has_a_wide_row(content) == expected, repr(content)


def test_parsing_a_table_leaves_the_csv_field_limit_alone() -> None:
    before = csv.field_size_limit()
    get_adapter(AUDIO, "tsv").parse("start_time\ttext\n1\thi\n")
    assert csv.field_size_limit() == before


def test_hocr_depth_is_capped_before_it_costs_time() -> None:
    deep = '<div class="ocr_page">' + '<span class="ocr_carea">aaaaaaaaaa' * 100_000 + "</span>" * 100_000 + "</div>"
    started = time.monotonic()
    with pytest.raises(ValueError, match="more than 100,000 elements open"):
        get_adapter(DOCUMENT, "hocr").parse(deep)
    assert time.monotonic() - started < 30


@pytest.mark.parametrize(
    "content", ["**[" + "a - " * 500_000, "**[" + "a - " * 500_000 + "]*", "**[" + " - " * 500_000 + "]"]
)
def test_markdown_takes_linear_time_on_hostile_lines(content: str) -> None:
    started = time.monotonic()
    get_adapter(AUDIO, "md").parse(content, validate=False)
    assert time.monotonic() - started < 30


def test_hocr_paragraphs_without_end_tags_are_read() -> None:
    lines = "".join(
        f"<p class='ocr_par'><span class='ocr_line' title='bbox 0 {i} 10 {i + 1}'>w{i}</span>" for i in range(300)
    )
    content = f"<div class='ocr_page' title='bbox 0 0 100 400'>{lines}</div>"
    assert len(get_adapter(DOCUMENT, "hocr").parse(content)["blocks"]) == 300


def test_hocr_end_tags_cant_search_many_open_elements_many_times() -> None:
    content = "<b>" * 40_000 + "<p>" * 40_000 + "</b>" * 40_000
    started = time.monotonic()
    with pytest.raises(ValueError, match="too many elements open"):
        get_adapter(DOCUMENT, "hocr").parse(content)
    assert time.monotonic() - started < 30


def test_a_gzip_bomb_stops_at_the_cap_and_doesnt_decompress_it_all(tmp_path: Path) -> None:
    path = tmp_path / "bomb.txt.gz"
    with gzip.open(path, "wb", compresslevel=9) as f:
        for _ in range(64):
            f.write(b"\0" * (16 * 1024 * 1024))
    assert path.stat().st_size < 2 * 1024 * 1024
    tracemalloc.start()
    with pytest.raises(ValueError, match="larger than max_size") as caught:
        get_adapter(AUDIO, "txt").parse_file(path, max_size=1024 * 1024)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert peak < 16 * 1024 * 1024
    assert _chain_is_bounded(caught.value)


def test_many_gzip_members_count_towards_one_cap(tmp_path: Path) -> None:
    path = tmp_path / "members.txt.gz"
    path.write_bytes(gzip.compress(b"a" * 1000) * 100)
    with pytest.raises(ValueError, match="larger than max_size"):
        get_adapter(AUDIO, "txt").parse_file(path, max_size=50_000)
    assert len(get_adapter(AUDIO, "txt").parse_file(path, max_size=100_000)["text"]) == 100_000


def test_exactly_the_cap_is_allowed(tmp_path: Path) -> None:
    path = tmp_path / "exact.txt"
    path.write_bytes(b"a" * 100)
    assert get_adapter(AUDIO, "txt").parse_file(path, max_size=100)["text"] == "a" * 100
    with pytest.raises(ValueError, match="larger than max_size"):
        get_adapter(AUDIO, "txt").parse_file(path, max_size=99)


@pytest.mark.parametrize(
    "data",
    [b"", b"plain text", gzip.compress(b"hello")[:-4], gzip.compress(b"hello")[:12], gzip.compress(b"hi") + b"junk"],
)
def test_bad_gzip_is_a_short_value_error(tmp_path: Path, data: bytes) -> None:
    path = tmp_path / "bad.txt.gz"
    path.write_bytes(data)
    if data == b"":
        with pytest.raises(ValueError, match="empty"):
            get_adapter(AUDIO, "txt").parse_file(path)
        return
    with pytest.raises(ValueError, match="not valid gzip") as caught:
        get_adapter(AUDIO, "txt").parse_file(path)
    assert _chain_is_bounded(caught.value)


@pytest.mark.parametrize("name", ["bad.txt", "bad.txt.gz"])
def test_bad_utf8_is_a_short_value_error(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    data = b"ok" * 100_000 + b"\xff"
    path.write_bytes(gzip.compress(data) if name.endswith(".gz") else data)
    with pytest.raises(ValueError, match="not valid UTF-8") as caught:
        get_adapter(AUDIO, "txt").parse_file(path)
    assert not isinstance(caught.value, UnicodeError)
    assert _chain_is_bounded(caught.value)


def test_a_missing_file_stays_an_os_error(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        get_adapter(AUDIO, "txt").parse_file(tmp_path / "missing.txt.gz")


def test_the_cap_applies_to_file_objects(tmp_path: Path) -> None:
    path = tmp_path / "plain.txt"
    path.write_text("a" * 100, encoding="utf-8")
    with open(path, encoding="utf-8") as fp, pytest.raises(ValueError, match="larger than max_size"):
        get_adapter(AUDIO, "txt").parse_file(fp, max_size=10)


@pytest.mark.parametrize(
    ("value", "error"),
    [(0, ValueError), (-1, ValueError), ("many", ValueError), (True, TypeError), (1.5, TypeError), (None, TypeError)],
)
def test_max_size_must_be_a_positive_integer(tmp_path: Path, value: Any, error: type[Exception]) -> None:
    path = tmp_path / "a.txt"
    path.write_text("a", encoding="utf-8")
    with pytest.raises(error, match="max_size"):
        get_adapter(AUDIO, "txt").parse_file(path, max_size=value)


def test_max_size_from_a_command_line_string(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("abc", encoding="utf-8")
    assert get_adapter(AUDIO, "txt").parse_file(path, max_size="3")["text"] == "abc"  # type: ignore[arg-type]


def _peak(function: Any) -> tuple[int, type | None]:
    tracemalloc.start()
    failure = None
    try:
        function()
    except Exception as error:
        failure = type(error)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return peak, failure


@pytest.mark.parametrize(
    ("schema", "fmt", "content", "limit"),
    [
        (DOCUMENT, "hocr", '<span class="ocr_line">' * 200 + "x" * 1_000_000 + "</span>" * 200, 32),
        (DOCUMENT, "tsv", "\t".join(f"c{i}" for i in range(255)) + "\ttext\n" + "a\n" * 1_000_000, 260),
        (DOCUMENT, "tsv", "text\n" + "a\n" * 1_000_000, 260),
        (AUDIO, "md", "x\n" * 1_000_000, 200),
        (DOCUMENT, "hocr", '<div class="ocr_page" title="bbox 0 0 1 1"></div>' * 150_000, 260),
        (AUDIO, "vtt", "WEBVTT\n\n" + "00:01.000 --> 00:02.000\n\n" * 150_000, 32),
        ("generic", "json", '{"data":{"a":[' + "[]," * 3_000_000 + "0]}}", 32),
        ("generic", "json", '{"data":{"a":[' + "1," * 5_000_000 + "0]}}", 32),
    ],
)
def test_small_hostile_content_cant_multiply_memory(schema: str, fmt: str, content: str, limit: int) -> None:
    adapter = get_adapter(schema, fmt)
    peak, failure = _peak(lambda: adapter.parse(content, validate=False))
    assert failure is ValueError
    assert peak < limit * 1024 * 1024


@pytest.mark.parametrize(
    "content",
    [
        "1" * 200_000,
        "\n" * 200_000,
        " " * 200_000,
        "1\n" * 100_000,
        "1 --> " * 30_000,
        "00:00:01,000 -" * 20_000,
        "1:" * 100_000,
        "1" * 200_000 + ".x",
        "1:1:" + "1" * 200_000,
        "00:00:01,000 --> 00:00:02,000\n1:1:" + "1" * 200_000,
        "1" * 200_000 + "x",
    ],
)
def test_srt_takes_linear_time_on_hostile_text(content: str) -> None:
    started = time.monotonic()
    try:
        get_adapter(AUDIO, "srt").parse(content)
    except ValueError:
        pass
    assert time.monotonic() - started < 30


@pytest.mark.parametrize(
    "content",
    [
        '<span class="ocr_line">' * 250 + " " * 2_000_000 + "</span>" * 250,
        "<div>" * 250 + "x" * 2_000_000 + "</div>" * 250,
        "<i>" * 250 + "</b>" * 500_000,
        '<span class="ocr_line">' * 250 + "<b></b>" * 100_000 + "</span>" * 250,
    ],
)
def test_hocr_takes_linear_time_on_hostile_markup(content: str) -> None:
    started = time.monotonic()
    with pytest.raises(ValueError):
        get_adapter(DOCUMENT, "hocr").parse(content)
    assert time.monotonic() - started < 30


def test_huge_max_size_is_only_a_large_limit(tmp_path: Path) -> None:
    path = tmp_path / "a.txt.gz"
    path.write_bytes(gzip.compress(b"hi"))
    assert get_adapter(AUDIO, "txt").parse_file(path, max_size=2**80)["text"] == "hi"


@pytest.mark.parametrize("options", [{"on_bad_number": "x" * 100_000}, {"x" * 100_000: 1}, {"validate": "x" * 100_000}])
def test_option_errors_are_bounded(options: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)) as caught:
        get_adapter(AUDIO, "txt").parse("hi", **options)
    assert len(str(caught.value)) < 1200


@pytest.mark.parametrize("fmt", ["tsv", "md", "srt", "txt", "json", "vtt"])
def test_an_empty_text_file_object_is_a_value_error_or_invalid(fmt: str) -> None:
    with pytest.raises(ValueError):
        get_adapter(AUDIO, fmt).parse_file(io.StringIO(""))


@pytest.mark.parametrize(
    ("content", "texts"),
    [
        ("WEBVTT\n00:01.000 --> 00:02.000\na\n", ["a"]),
        ("WEBVTT\n\n00:01.000 --> 00:02.000\na\n00:03.000 --> 00:04.000\nb\n", ["a", "b"]),
        ("WEBVTT\nX-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0\n\n00:01.000 --> 00:02.000\na\n", ["a"]),
        ("WEBVTT\nKind: captions\nLanguage: en\n\n00:01.000 --> 00:02.000 align:start\na\n", ["a"]),
        ("WEBVTT - title\r\n\r\nid 1\r\n00:01.000 --> 00:02.000\r\na\r\n", ["a"]),
        ("WEBVTT\n\nNOTES on intro\n00:01.000 --> 00:02.000\na\n", ["a"]),
        ("WEBVTT\n\nNOTE a comment\nmore\n\nSTYLE\n::cue {}\n\n00:01.000 --> 00:02.000\na\n", ["a"]),
        ("WEBVTT\n\n00:01.000 --> 00:02.000\na\u2028\u2028b\n", None),
        ("WEBVTT\n\n00:01.000 --> 00:02.000\na -> b\n", ["a -> b"]),
        ("WEBVTT\n\n00:01.000 --> 00:02.000\n2 -> 3 today\n", ["2 -> 3 today"]),
        ("WEBVTT\n\n00:01.000 --> 00:02.000\n10 - > 20\n", ["10 - > 20"]),
        ("WEBVTT\n\n00:01.000 --> 00:02.000\n3:15 -> 3:45 is the slot\n", ["3:15 -> 3:45 is the slot"]),
        ("WEBVTT\n\n1 -> intro\n00:01.000 --> 00:02.000\na\n", ["a"]),
    ],
)
def test_legitimate_webvtt_is_read(content: str, texts: list[str] | None) -> None:
    parsed = get_adapter(AUDIO, "vtt").parse(content)
    assert len(parsed["segments"]) == 1 + ("00:03.000" in content)
    if texts is not None:
        assert [segment["text"] for segment in parsed["segments"]] == texts


@pytest.mark.parametrize(
    "content",
    [
        '{"producer":"p","data":{"a":[' + '{"a":0},' * 200_000 + "0]}}",
        '{"producer":"p","data":{"a":' + "[" * 60 + "-0.0," * 400_000 + "0" + "]" * 60 + "}}",
        '{"producer":"p","data":{"a":' + "[" * 60 + "1e300," * 400_000 + "0" + "]" * 60 + "}}",
    ],
)
def test_a_large_invalid_record_is_rejected_without_repair(content: str) -> None:
    peak, failure = _peak(lambda: get_adapter("generic", "json").parse(content))
    assert failure is oatschema.ValidationError
    assert peak < 300 * 1024 * 1024


def test_a_large_record_with_a_bad_number_drops_it_and_a_valid_one_is_kept() -> None:
    blocks = [{"block_type": "text", "text": "a", "page_number": 1} for _ in range(90_000)]
    record = {"extraction_type": "text", "blocks": blocks}
    blocks[-1]["score"] = 1.5
    with pytest.warns(oatschema.DroppedNumberWarning, match="/blocks/89999/score"):
        parsed = get_adapter(DOCUMENT, "json").parse(json.dumps(record))
    assert isinstance(parsed, ParsedRecord)
    assert [item.path for item in parsed.dropped] == [("blocks", 89_999, "score")]
    assert "score" not in parsed["blocks"][-1]
    assert len(parsed["blocks"]) == 90_000
    blocks[-1]["score"] = 0.5
    assert get_adapter(DOCUMENT, "json").parse(json.dumps(record))["blocks"][-1]["score"] == 0.5


def test_large_word_level_hocr_drops_a_bad_score() -> None:
    words = "".join(
        f"<span class='ocrx_word' title='bbox {i % 900} {i // 900} {i % 900 + 1} {i // 900 + 1}; "
        f"x_wconf {150 if i == 25_000 else 90}'>w{i}</span>"
        for i in range(30_000)
    )
    content = f"<div class='ocr_page' title='bbox 0 0 1000 1000'>{words}</div>"
    with pytest.warns(oatschema.DroppedNumberWarning):
        parsed = get_adapter(DOCUMENT, "hocr").parse(content, target_class="ocrx_word")
    assert isinstance(parsed, ParsedRecord)
    assert [item.path for item in parsed.dropped] == [("blocks", 25_000, "score")]
    assert len(parsed["blocks"]) == 30_000


def _small_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from oatschema_adapters import _validation

    monkeypatch.setattr(_validation, "MAX_VALUES_TO_REPAIR", 60)


def test_grouped_checks_report_the_whole_records_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch)
    segments = [{"text": "x", "start_time": i, "end_time": i + 1, "score": 0.5} for i in range(40)]
    segments[3]["score"] = 1.5
    segments[37]["score"] = -0.0
    segments[38]["speaker"] = {"id": "a", "name": "A", "score": 2}
    record = {"producer": "p", "duration": -0.0, "segments": segments}
    with pytest.warns(oatschema.DroppedNumberWarning, match="dropped 2 .*/segments/3/score"):
        parsed = get_adapter(AUDIO, "json").parse(json.dumps(record))
    assert isinstance(parsed, ParsedRecord)
    assert [item.path for item in parsed.dropped] == [("segments", 3, "score"), ("segments", 38, "speaker", "score")]
    assert sorted(item.path for item in parsed.converted) == [("duration",), ("segments", 37, "score")]
    assert list(parsed) == ["producer", "duration", "segments"]
    assert len(parsed["segments"]) == 40


def test_grouped_checks_give_the_index_of_an_invalid_item(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch)
    segments = [{"text": "x", "start_time": i, "end_time": i + 1, "score": 1.5} for i in range(40)]
    segments[33]["text"] = 5
    with pytest.raises(oatschema.ValidationError) as caught:
        get_adapter(AUDIO, "json").parse(json.dumps({"producer": "p", "segments": segments}))
    assert caught.value.path == ("segments", 33, "text")


def test_grouped_checks_give_whole_record_paths_in_the_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch)
    segments = [{"text": "x", "start_time": i, "end_time": i + 1} for i in range(40)]
    segments[31]["score"] = 1.5
    segments[33]["start_time"] = -1
    with pytest.raises(oatschema.ValidationError) as caught:
        get_adapter(AUDIO, "json").parse(json.dumps({"producer": "p", "segments": segments}))
    assert caught.value.path == ("segments", 33)
    assert "/segments/31/score, /segments/33/start_time" in caught.value.message


def test_a_large_rest_of_the_record_is_rejected_without_checking_each_item(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch)
    blocks: list[dict[str, Any]] = [{"block_type": "text", "text": "a"} for _ in range(30)]
    blocks[-1]["score"] = 1.5
    record = {"extraction_type": "text", "page_width": [{"value": 1, "pages": list(range(1, 30))}], "blocks": blocks}
    calls = 0
    check_numbers = oatschema.check_numbers

    def counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return check_numbers(*args, **kwargs)

    monkeypatch.setattr(oatschema, "check_numbers", counting)
    with pytest.raises(oatschema.ValidationError, match="too many to say where"):
        get_adapter(DOCUMENT, "json").parse(json.dumps(record))
    assert calls == 0


def test_grouped_checks_still_see_rules_across_items(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch)
    blocks = [{"block_type": "text", "text": "a", "score": 1.5} for _ in range(30)]
    blocks[25] = {"block_type": "box", "box": {"x": 0, "y": 0, "width": 1, "height": 1}}
    with pytest.raises(oatschema.ValidationError):
        get_adapter(DOCUMENT, "json").parse(json.dumps({"extraction_type": "mixed", "blocks": blocks}))


def test_a_single_item_too_large_to_check_is_rejected_without_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch)
    polygon = [{"x": i, "y": 0} for i in range(40)]
    record = {
        "extraction_type": "mixed",
        "unit": "px",
        "blocks": [{"block_type": "polygon", "polygon": polygon, "score": 2}],
    }
    with pytest.raises(oatschema.ValidationError, match="too many to say where"):
        get_adapter(DOCUMENT, "json").parse(json.dumps(record))

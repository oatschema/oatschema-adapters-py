# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import copy
import decimal
import json
import pickle
import random
import warnings
from typing import Any

import oatschema
import pytest

from oatschema_adapters import ParsedRecord, get_adapter
from oatschema_adapters._numbers import load_json, parse_number

AUDIO = "audio-transcription"
DOCUMENT = "document-extraction"
MAX = 9007199254740991

GOOD_CONTENT = [
    (AUDIO, "json", '{"text": "hi"}'),
    (AUDIO, "md", "**[00:01 - 00:02]** hi"),
    (AUDIO, "srt", "1\n00:00:01,000 --> 00:00:02,000\nhi\n"),
    (AUDIO, "tsv", "start_time\tend_time\ttext\n1\t2\thi\n"),
    (AUDIO, "txt", "hi"),
    (AUDIO, "vtt", "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n"),
    (DOCUMENT, "hocr", '<span class="ocr_line">hi</span>'),
    (DOCUMENT, "json", '{"extraction_type": "text", "blocks": []}'),
    (DOCUMENT, "tsv", "text\nhi\n"),
    (DOCUMENT, "txt", "hi"),
]

BAD_OPTIONAL = [
    (DOCUMENT, "hocr", '<span class="ocr_line" title="x_wconf 150">hi</span>', ("blocks", 0, "score")),
    (DOCUMENT, "tsv", f"page_number\ttext\n{MAX + 2}\thi\n", ("blocks", 0, "page_number")),
    (AUDIO, "json", '{"text": "hi", "duration": 9007199254740993}', ("duration",)),
    (AUDIO, "md", "---\nduration: 1e300\n---\n\n**[00:01 - 00:02]** hi", ("duration",)),
]

BAD_REQUIRED = [
    (AUDIO, "tsv", "start_time\ttext\n1e300\thi\n"),
    (AUDIO, "md", "**[90071992547409920 - 90071992547409920]** hi"),
    (DOCUMENT, "tsv", "block_type\tx\ty\twidth\theight\ttext\nbox\t1e300\t0\t1\t1\thi\n"),
    (DOCUMENT, "hocr", '<span class="ocr_line" title="bbox 1e300 0 1e301 1">hi</span>'),
    (
        DOCUMENT,
        "json",
        '{"extraction_type":"text","unit":"px","blocks":[{"block_type":"box","box":'
        '{"x":1e300,"y":0,"width":1,"height":1}}]}',
    ),
]

UNUSABLE = [
    (AUDIO, "tsv", "start_time\ttext\n{}\thi\n"),
    (AUDIO, "tsv", "start_time\tend_time\ttext\n1\t{}\thi\n"),
    (AUDIO, "md", "---\nduration: {}\n---\n\nhi"),
    (AUDIO, "json", '{{"text": "hi", "duration": {}}}'),
    (DOCUMENT, "tsv", "x\ty\twidth\theight\ttext\n{}\t0\t1\t1\thi\n"),
    (DOCUMENT, "tsv", "polygon\ttext\n[[{},0],[1,0],[1,1]]\thi\n"),
    (DOCUMENT, "hocr", '<span class="ocr_line" title="bbox {} 0 1 1">hi</span>'),
    (DOCUMENT, "hocr", '<span class="ocr_line" title="x_wconf {}">hi</span>'),
    (DOCUMENT, "hocr", '<div class="ocr_page" title="bbox 0 0 {} 1"><span class="ocr_line">hi</span></div>'),
    (DOCUMENT, "hocr", """<span class="ocr_line" data-polygon='[{{"x":{},"y":0}}]'>hi</span>"""),
    (DOCUMENT, "json", '{{"blocks": [], "extraction_type": "text", "page_width": {}}}'),
]
UNUSABLE_NUMBERS = ["NaN", "Infinity", "-Infinity", "1e400", "-1e400", "1e-400", "1.00000000000000001"]


@pytest.mark.parametrize(("schema", "fmt", "content"), GOOD_CONTENT)
@pytest.mark.parametrize("validate", [True, False])
def test_every_parser_returns_a_parsed_record(schema: str, fmt: str, content: str, validate: bool) -> None:
    parsed = get_adapter(schema, fmt).parse(content, validate=validate)
    assert isinstance(parsed, ParsedRecord)
    assert parsed.dropped == ()
    assert parsed.converted == ()
    assert json.loads(json.dumps(parsed)) == dict(parsed)


@pytest.mark.parametrize(("schema", "fmt", "content"), GOOD_CONTENT)
@pytest.mark.parametrize("version", ["0.4.0", "0.8.0", oatschema.SCHEMA_VERSION])
def test_parsed_records_are_valid_at_the_version_asked_for(schema: str, fmt: str, content: str, version: str) -> None:
    parsed = get_adapter(schema, fmt).parse(content, schema_version=version)
    oatschema.validate(parsed, schema, version)  # type: ignore[arg-type]


@pytest.mark.parametrize(("schema", "fmt", "content", "path"), BAD_OPTIONAL)
def test_a_bad_optional_number_is_dropped_and_reaches_the_caller(
    schema: str, fmt: str, content: str, path: tuple[Any, ...]
) -> None:
    adapter = get_adapter(schema, fmt)
    with pytest.warns(oatschema.DroppedNumberWarning):
        parsed = adapter.parse(content)
    assert isinstance(parsed, ParsedRecord)
    assert [item.path for item in parsed.dropped] == [path]
    oatschema.validate(parsed, schema)  # type: ignore[arg-type]


@pytest.mark.parametrize(("schema", "fmt", "content", "path"), BAD_OPTIONAL)
def test_a_bad_optional_number_can_reject_the_record(
    schema: str, fmt: str, content: str, path: tuple[Any, ...]
) -> None:
    with pytest.raises(oatschema.ValidationError) as caught:
        get_adapter(schema, fmt).parse(content, on_bad_number="raise")
    assert caught.value.path == path


@pytest.mark.parametrize(("schema", "fmt", "content"), BAD_REQUIRED)
def test_a_bad_required_number_rejects_the_record(schema: str, fmt: str, content: str) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", oatschema.DroppedNumberWarning)
        with pytest.raises(oatschema.ValidationError):
            get_adapter(schema, fmt).parse(content)


@pytest.mark.parametrize(("schema", "fmt", "content"), BAD_REQUIRED)
def test_validate_false_applies_no_bounds(schema: str, fmt: str, content: str) -> None:
    assert get_adapter(schema, fmt).parse(content, validate=False)


@pytest.mark.parametrize(("schema", "fmt", "template"), UNUSABLE)
@pytest.mark.parametrize("number", UNUSABLE_NUMBERS)
@pytest.mark.parametrize("validate", [True, False])
def test_unusable_numbers_are_refused_with_or_without_validation(
    schema: str, fmt: str, template: str, number: str, validate: bool
) -> None:
    with pytest.raises(ValueError):
        get_adapter(schema, fmt).parse(template.format(number), validate=validate)


@pytest.mark.parametrize("fmt", ["md", "vtt"])
def test_clock_times_are_refused_when_a_double_cant_hold_them(fmt: str) -> None:
    adapter = get_adapter(AUDIO, fmt)
    assert adapter.parse(adapter.export({"segments": [{"text": "a", "start_time": 3600.1, "end_time": 3600.2}]}))
    with pytest.raises(ValueError, match="not a time"):
        get_adapter(AUDIO, "md").parse("**[00:01.00000000000000001 - 00:02]** hi", validate=False)


def test_a_conversion_reaches_the_caller() -> None:
    parsed = get_adapter(DOCUMENT, "tsv").parse("block_type\tx\ty\twidth\theight\ttext\nbox\t-0.0\t0\t1\t1\thi\n")
    assert isinstance(parsed, ParsedRecord)
    assert [(item.path, item.after) for item in parsed.converted] == [(("blocks", 0, "box", "x"), 0.0)]


def test_lone_surrogates_fail_validation_in_every_parser_of_text() -> None:
    for schema, fmt, content in [
        (AUDIO, "txt", "hi \ud800"),
        (AUDIO, "srt", "1\n00:00:01,000 --> 00:00:02,000\nhi \ud800\n"),
        (AUDIO, "tsv", "start_time\ttext\n1\thi \ud800\n"),
        (DOCUMENT, "tsv", "text\nhi \ud800\n"),
    ]:
        with pytest.raises(oatschema.ValidationError, match="surrogate"):
            get_adapter(schema, fmt).parse(content)


def test_parsed_record_copies_and_pickles_keep_their_report() -> None:
    with pytest.warns(oatschema.DroppedNumberWarning):
        parsed = get_adapter(DOCUMENT, "hocr").parse('<span class="ocr_line" title="x_wconf 150">hi</span>')
    assert isinstance(parsed, ParsedRecord)
    for clone in (copy.copy(parsed), copy.deepcopy(parsed), pickle.loads(pickle.dumps(parsed))):
        assert clone == parsed
        assert clone.dropped == parsed.dropped


@pytest.mark.parametrize("schema, fmt, content", GOOD_CONTENT)
def test_on_bad_number_is_keyword_checked(schema: str, fmt: str, content: str) -> None:
    with pytest.raises(ValueError, match="on_bad_number"):
        get_adapter(schema, fmt).parse(content, on_bad_number="ignore")


@pytest.mark.parametrize(
    "text",
    [
        "0",
        "-0",
        "1",
        "1.5",
        ".5",
        "5.",
        "1e2",
        "1E+2",
        "0.1",
        "0.10000000000000001",
        "5e-324",
        "1.7976931348623157e308",
    ],
)
def test_parse_number_accepts_what_a_double_holds(text: str) -> None:
    assert parse_number(text) == float(text)
    assert parse_number(f" {text} ") == float(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "nan",
        "NaN",
        "inf",
        "-inf",
        "1e400",
        "1e-400",
        "1_000",
        "٣",
        "0x10",
        "1.00000000000000001",
        "1.0000000000000001",
        "9007199254740993",
        "1" * 2000,
    ],
)
def test_parse_number_refuses_the_rest(text: str) -> None:
    with pytest.raises(ValueError) as caught:
        parse_number(text)
    assert len(str(caught.value)) < 200


@pytest.mark.parametrize(
    "text",
    ["NaN", "[Infinity]", '{"a": -Infinity}', "[1e400]", '{"a": 1, "a": 2}', "[" * 200000, "{", b"\xff"],
)
def test_load_json_refuses_with_a_short_plain_value_error(text: str | bytes) -> None:
    with pytest.raises(ValueError) as caught:
        load_json(text)
    assert type(caught.value) is ValueError
    assert len(str(caught.value)) < 200
    assert caught.value.__context__ is None or len(str(caught.value.__context__)) < 300


def test_every_double_reads_back_as_itself_from_its_repr() -> None:
    generator = random.Random(7)
    samples = [2.0**power for power in range(-1074, 1024)]
    samples += [generator.uniform(0, 1) * 10.0 ** generator.randint(-300, 300) for _ in range(5000)]
    for value in samples:
        assert parse_number(repr(value)) == value
        assert load_json(json.dumps([value])) == [value]


def test_a_doubles_exact_expansion_reads_back_as_itself() -> None:
    assert parse_number("0.1000000000000000055511151231257827021181583404541015625") == 0.1


def test_parse_number_ignores_the_callers_decimal_context() -> None:
    with decimal.localcontext() as context:
        context.prec = 3
        context.traps[decimal.Inexact] = True
        assert parse_number("1.2345") == 1.2345
        assert parse_number("0.1000000000000000055511151231257827021181583404541015625") == 0.1
        with pytest.raises(ValueError):
            parse_number("1.00000000000000001")


@pytest.mark.parametrize(
    ("title", "field", "expected"),
    [
        ("bbox 0.1 0.2 0.3 0.4", "width", 0.2),
        ("bbox 1 1 1.1 1.1", "width", 0.1),
        ("x_wconf 57.1", "score", 0.571),
        ("x_wconf 14.3", "score", 0.143),
        ("x_wconf 8.299841949107146", "score", 0.08299841949107146),
        ("bbox 0 0 239.39853374935637 1", "width", 239.39853374935637),
        ("bbox 0.5 0 9007199254740991 1", "width", 9007199254740990.0),
    ],
)
def test_hocr_arithmetic_is_exact(title: str, field: str, expected: float) -> None:
    block = get_adapter(DOCUMENT, "hocr").parse(f'<span class="ocr_line" title="{title}">hi</span>')["blocks"][0]
    assert block.get(field, block.get("box", {}).get(field)) == expected


def test_srt_times_are_exact_and_read_as_milliseconds() -> None:
    adapter = get_adapter(AUDIO, "srt")
    segment = adapter.parse("1\n01:00:00,100 --> 01:00:00.200\nhi\n")["segments"][0]
    assert (segment["start_time"], segment["end_time"]) == (3600.1, 3600.2)


def test_a_whole_frontmatter_duration_stays_an_integer() -> None:
    assert get_adapter(AUDIO, "md").parse("---\nduration: 5\n---\n\nhi")["duration"] == 5
    assert type(get_adapter(AUDIO, "md").parse("---\nduration: 5\n---\n\nhi")["duration"]) is int

# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import inspect
import re
import os
import typing
from pathlib import Path
from typing import Any, Literal

import oatschema
import pytest

from conftest import load
from oatschema_adapters import get_adapter
from oatschema_adapters._options import checked
from test_registry import OATS_FORMATS, PARSERS

AUDIO = load("audio-transcription-2")
DOCUMENT = load("document-extraction-3")
RECORDS = {"audio-transcription": AUDIO, "document-extraction": DOCUMENT}


@checked
def sample(
    record: Any,
    *,
    flag: bool = False,
    count: int = 1,
    ratio: float = 0.5,
    choice: Literal["a", "b"] = "a",
    text: str | None = None,
    limit: float | None = None,
    theme: Literal["x"] | str = "x",
    path: str | os.PathLike[str] | None = None,
    anything: Any = None,
) -> dict[str, Any]:
    return {
        "flag": flag,
        "count": count,
        "ratio": ratio,
        "choice": choice,
        "text": text,
        "limit": limit,
        "theme": theme,
        "path": path,
        "anything": anything,
    }


@pytest.mark.parametrize(
    ("option", "value", "expected"),
    [
        ("flag", "false", False),
        ("flag", "False", False),
        ("flag", " no ", False),
        ("flag", "0", False),
        ("flag", "off", False),
        ("flag", "TRUE", True),
        ("flag", "yes", True),
        ("flag", "1", True),
        ("flag", "on", True),
        ("flag", True, True),
        ("count", "3", 3),
        ("count", 4, 4),
        ("ratio", "0.25", 0.25),
        ("ratio", "1e-1", 0.1),
        ("ratio", 2, 2),
        ("choice", "b", "b"),
        ("text", "none", "none"),
        ("text", None, None),
        ("text", 2026, "2026"),
        ("text", 1.5, "1.5"),
        ("limit", "null", None),
        ("limit", "None", None),
        ("limit", "2.5", 2.5),
        ("theme", "x", "x"),
        ("theme", "custom.css", "custom.css"),
        ("path", Path("a.css"), Path("a.css")),
        ("path", "a.css", "a.css"),
        ("anything", {"a": 1}, {"a": 1}),
    ],
)
def test_options_are_converted(option: str, value: Any, expected: Any) -> None:
    result = sample({}, **{option: value})[option]
    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize(
    ("option", "value", "error", "message"),
    [
        ("flag", "maybe", ValueError, "sample() option 'flag' must be true or false, not 'maybe'"),
        ("flag", 1, TypeError, "option 'flag' must be true or false, not 1"),
        ("flag", None, TypeError, "option 'flag' must be true or false, not None"),
        ("count", "1.5", ValueError, "option 'count' must be an integer, not '1.5'"),
        ("count", True, TypeError, "option 'count' must be an integer, not True"),
        ("ratio", "high", ValueError, "option 'ratio' must be a number, not 'high'"),
        ("ratio", "nan", ValueError, "option 'ratio' must be a number, not 'nan'"),
        ("ratio", float("inf"), TypeError, "option 'ratio' must be a number, not inf"),
        ("ratio", False, TypeError, "option 'ratio' must be a number"),
        ("choice", "c", ValueError, "option 'choice' must be 'a' or 'b', not 'c'"),
        ("choice", 1, TypeError, "option 'choice' must be 'a' or 'b', not 1"),
        ("text", True, TypeError, "option 'text' must be a string or None, not True"),
        ("text", ["a"], TypeError, "option 'text' must be a string or None"),
        ("limit", "lots", ValueError, "option 'limit' must be a number or None, not 'lots'"),
        ("path", True, TypeError, "option 'path' must be a string or a path or None, not True"),
    ],
)
def test_bad_options_raise_a_clear_error(option: str, value: Any, error: type, message: str) -> None:
    with pytest.raises(error, match=re.escape(message)):
        sample({}, **{option: value})


def test_unknown_options_are_listed() -> None:
    with pytest.raises(TypeError, match=r"sample\(\) got unknown option\(s\) 'colour', 'size'; options: flag, count"):
        sample({}, size=1, colour="red")  # type: ignore[call-arg]


def test_signature_and_name_are_kept() -> None:
    assert sample.__name__ == "sample"
    assert "flag" in inspect.signature(sample).parameters


def _cli_value(hint: Any, default: Any) -> str | None:
    if default is inspect.Parameter.empty:
        return None
    if hint is bool:
        return str(not default).lower()
    if hint is float:
        return str(default + 0.5)
    if typing.get_origin(hint) is Literal:
        return str(typing.get_args(hint)[-1])
    return None


def _options(function: Any) -> list[tuple[str, Any, str]]:
    hints = typing.get_type_hints(function)
    options = []
    for name, parameter in list(inspect.signature(function).parameters.items())[1:]:
        if name in ("validate", "schema_version", "producer"):
            continue
        value = _cli_value(hints[name], parameter.default)
        if value is not None:
            options.append((name, parameter.default, value))
    return options


EXPORT_OPTIONS = [
    (schema, fmt, name, value)
    for schema, formats in OATS_FORMATS.items()
    for fmt in formats
    for name, _, value in _options(get_adapter(schema, fmt)._export_fn)
]


def test_every_exporter_has_options_to_test() -> None:
    assert {(schema, fmt) for schema, fmt, _, _ in EXPORT_OPTIONS} == {
        (schema, fmt)
        for schema, formats in OATS_FORMATS.items()
        for fmt in formats
        if fmt != "tsv" or schema != "document-extraction"
    } - {("audio-transcription", "txt"), ("document-extraction", "hocr")}


@pytest.mark.parametrize(("schema", "fmt", "name", "value"), EXPORT_OPTIONS)
def test_string_options_give_the_same_output_as_typed_ones(schema: str, fmt: str, name: str, value: str) -> None:
    adapter = get_adapter(schema, fmt)
    hint = typing.get_type_hints(adapter._export_fn)[name]
    typed: Any = value == "true" if hint is bool else float(value) if hint is float else value
    assert adapter.export(RECORDS[schema], **{name: value}) == adapter.export(RECORDS[schema], **{name: typed})


@pytest.mark.parametrize(("schema", "fmt"), [(s, f) for s, formats in OATS_FORMATS.items() for f in formats])
def test_validate_false_as_a_string_skips_validation(schema: str, fmt: str) -> None:
    adapter = get_adapter(schema, fmt)
    record = dict(RECORDS[schema], unexpected="field")
    with pytest.raises(oatschema.ValidationError):
        adapter.export(record, validate="true")
    adapter.export(record, validate="false")


@pytest.mark.parametrize(("schema", "fmt"), [(s, f) for s, formats in PARSERS.items() for f in sorted(formats)])
def test_parse_options_from_strings(schema: str, fmt: str) -> None:
    adapter = get_adapter(schema, fmt)
    content = adapter.export(RECORDS[schema])
    too_long = "x" * 1025
    with pytest.raises(oatschema.ValidationError) as caught:
        adapter.parse(content, producer=too_long, validate="yes")
    assert caught.value.keyword == "maxLength"
    assert caught.value.path == ("producer",)
    assert adapter.parse(content, producer=too_long, validate="no")["producer"] == too_long
    assert adapter.parse(content, schema_version="0.6.0", producer="p")["producer"] == "p"


@pytest.mark.parametrize(("schema", "fmt"), [(s, f) for s, formats in OATS_FORMATS.items() for f in formats])
def test_unknown_export_options_raise(schema: str, fmt: str) -> None:
    with pytest.raises(TypeError, match=r"got unknown option\(s\) 'include_frontmater'"):
        get_adapter(schema, fmt).export(RECORDS[schema], include_frontmater=False)


def test_command_line_strings_reach_every_kind_of_option() -> None:
    audio_md = get_adapter("audio-transcription", "md")
    assert "**Ada:**" not in audio_md.export(AUDIO, include_speakers="false")
    assert "**Ada:**" in audio_md.export(AUDIO, include_speakers="true")
    assert "Low Confidence" not in audio_md.export(AUDIO, low_confidence_threshold="0.1")
    assert get_adapter("document-extraction", "txt").export(DOCUMENT, line_tolerance="3")
    assert get_adapter("document-extraction", "md").export(DOCUMENT, line_tolerance="3")
    assert get_adapter("document-extraction", "html").export(DOCUMENT, line_tolerance="3", gap_x="2", gap_y="2")
    with pytest.raises(ValueError, match="option 'include_speakers' must be true or false, not 'sometimes'"):
        get_adapter("audio-transcription", "srt").export(AUDIO, include_speakers="sometimes")


def test_footer_from_a_command_line_number() -> None:
    html = get_adapter("document-extraction", "html").export(DOCUMENT, footer=2026, fragment="true")
    assert '<div class="document-footer">\n    2026\n  </div>' in html
    assert "<html" not in html


@pytest.mark.parametrize(("schema", "fmt"), [(s, f) for s, formats in PARSERS.items() for f in sorted(formats)])
def test_parsers_reject_unknown_options_and_a_positional_producer(schema: str, fmt: str) -> None:
    adapter = get_adapter(schema, fmt)
    content = adapter.export(RECORDS[schema])
    with pytest.raises(TypeError, match=r"got unknown option\(s\) 'produser'"):
        adapter.parse(content, produser="x")
    function = adapter._parse_fn
    assert function is not None
    with pytest.raises(TypeError):
        function(content, "positional-producer")

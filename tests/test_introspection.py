# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

import pytest

from oatschema_adapters import AdapterOption, get_adapter, list_formats, list_schemas


def test_export_options_describe_names_types_defaults_and_text() -> None:
    options = {option.name: option for option in get_adapter("audio-transcription", "srt").export_options}
    assert list(options) == ["validate", "schema_version", "include_speakers"]
    assert options["include_speakers"] == AdapterOption(
        name="include_speakers",
        type="true or false",
        default=False,
        required=False,
        description="Start each subtitle with its speaker's name, as ``Name: text``.",
    )
    assert options["schema_version"].type == "a string or None"
    assert options["schema_version"].default is None


def test_parse_options_include_the_number_policy() -> None:
    options = {option.name: option for option in get_adapter("document-extraction", "tsv").parse_options}
    assert options["on_bad_number"].type == "'drop' or 'raise'"
    assert options["on_bad_number"].default == "drop"
    assert options["unit"].default == "px"
    assert "rejects the record" in options["on_bad_number"].description


def test_multi_line_descriptions_are_joined() -> None:
    options = {option.name: option for option in get_adapter("document-extraction", "html").export_options}
    assert "\n" not in options["layout"].description
    assert options["layout"].description.startswith('``"col"``')
    assert options["layout"].description.endswith("drawn at its coordinates).")


def test_every_builtin_option_is_described() -> None:
    for schema in list_schemas():
        for fmt, _ in list_formats(schema):
            adapter = get_adapter(schema, fmt)
            for option in (*adapter.export_options, *adapter.parse_options):
                assert option.description, (schema, fmt, option.name)
                assert not option.required


def test_a_direction_the_adapter_lacks_has_no_options() -> None:
    assert get_adapter("document-extraction", "md").parse_options == ()


@pytest.mark.parametrize("schema", ["audio-transcription", "document-extraction"])
def test_options_match_what_the_function_accepts(schema: str) -> None:
    for fmt, _ in list_formats(schema):
        adapter = get_adapter(schema, fmt)
        names = [option.name for option in adapter.export_options]
        assert "validate" in names and "schema_version" in names
        assert "record" not in names

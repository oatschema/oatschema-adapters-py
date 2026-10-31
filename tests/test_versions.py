# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

import typing

import oatschema
from oatschema import SchemaName
import pytest

from conftest import DATA, load
from oatschema_adapters import get_adapter
from test_registry import OATS_FORMATS, PARSERS

FIXTURES: dict[str, list[str]] = {
    schema: [path.stem for path in sorted(DATA.glob(f"{schema}-*.json"))]
    for schema in ("audio-transcription", "document-extraction")
}
INVALID = {
    "audio-transcription": [
        "invalid-audio-transcription-bad-language-code",
        "invalid-audio-transcription-invalid-segment",
        "invalid-audio-transcription-missing-content",
    ],
    "document-extraction": [
        "invalid-document-extraction-bad-missing-text",
        "invalid-document-extraction-bad-multipolygon-norm",
    ],
}


def _name(schema: str) -> SchemaName:
    return typing.cast(SchemaName, schema)


def _names(version: str) -> set[str]:
    names: set[str] = set()
    for name in FIXTURES:
        try:
            oatschema.get_schema(_name(name), version)
        except LookupError:
            continue
        names.add(name)
    return names


VERSIONS = {schema: [v for v in oatschema.available_versions() if schema in _names(v)] for schema in FIXTURES}


def _valid_at(schema: str, version: str) -> list[str]:
    return [name for name in FIXTURES[schema] if oatschema.is_valid(load(name), _name(schema), version)]


def _exportable(schema: str, fmt: str, record: dict[str, Any]) -> bool:
    if schema == "audio-transcription" and fmt in ("srt", "vtt", "tsv"):
        return bool(record.get("segments"))
    return True


def _parses_back(schema: str, fmt: str, record: dict[str, Any]) -> bool:
    if fmt not in PARSERS[schema]:
        return False
    blocks = record.get("blocks", [])
    if fmt == "hocr":
        return any(block.get("text") for block in blocks)
    if fmt == "tsv" and schema == "document-extraction":
        return not any(block["block_type"] in ("polygon", "multi_polygon") for block in blocks)
    return True


CASES = [
    (schema, fmt, version, fixture)
    for schema, formats in OATS_FORMATS.items()
    for fmt in formats
    for version in VERSIONS[schema]
    for fixture in _valid_at(schema, version)
    if _exportable(schema, fmt, load(fixture))
]


def test_both_schemas_are_in_every_bundled_version() -> None:
    assert VERSIONS["audio-transcription"] == oatschema.available_versions()
    assert VERSIONS["document-extraction"] == oatschema.available_versions()


@pytest.mark.parametrize("schema", sorted(OATS_FORMATS))
def test_every_format_has_a_valid_fixture_at_every_version(schema: str) -> None:
    for fmt in OATS_FORMATS[schema]:
        for version in VERSIONS[schema]:
            assert any(c[:3] == (schema, fmt, version) for c in CASES), (fmt, version)


@pytest.mark.parametrize(("schema", "fmt", "version", "fixture"), CASES)
def test_exports_validate_at_the_named_version(schema: str, fmt: str, version: str, fixture: str) -> None:
    adapter = get_adapter(schema, fmt)
    record = load(fixture)
    output = adapter.export(record, schema_version=version)
    assert output
    if _parses_back(schema, fmt, record):
        parsed = adapter.parse(output, schema_version=version)
        oatschema.validate(parsed, _name(schema), version)


@pytest.mark.parametrize("fmt", OATS_FORMATS["audio-transcription"])
def test_default_version_is_oatschemas_for_audio(fmt: str) -> None:
    record = load("audio-transcription-legacy-ids")
    adapter = get_adapter("audio-transcription", fmt)
    with pytest.raises(oatschema.ValidationError) as caught:
        adapter.export(record)
    assert (caught.value.schema_version, caught.value.keyword) == (oatschema.SCHEMA_VERSION, "type")
    assert adapter.export(record, schema_version="0.6.0")


@pytest.mark.parametrize("fmt", OATS_FORMATS["document-extraction"])
def test_default_version_is_not_the_old_0_5_0_for_documents(fmt: str) -> None:
    record = load("document-extraction-1")
    del record["extraction_type"]
    adapter = get_adapter("document-extraction", fmt)
    assert adapter.export(record)
    with pytest.raises(oatschema.ValidationError) as caught:
        adapter.export(record, schema_version="0.5.0")
    assert caught.value.schema_version == "0.5.0"


@pytest.mark.parametrize("version", oatschema.available_versions())
def test_from_hocr_gives_page_sizes_only_to_versions_that_have_them(version: str) -> None:
    adapter = get_adapter("document-extraction", "hocr")
    parsed = adapter.parse(adapter.export(load("document-extraction-1")), schema_version=version)
    assert ("page_width" in parsed) == (version != "0.4.0")
    assert ("page_height" in parsed) == (version != "0.4.0")


def test_tsv_of_polygon_blocks_does_not_parse_into_valid_blocks() -> None:
    adapter = get_adapter("document-extraction", "tsv")
    with pytest.raises(oatschema.ValidationError, match='"polygon" is a required property'):
        adapter.parse(adapter.export(load("document-extraction-1")))


@pytest.mark.parametrize(
    ("schema", "fmt", "fixture"),
    [(s, f, fixture) for s, formats in OATS_FORMATS.items() for f in formats for fixture in INVALID[s]],
)
def test_invalid_records_raise_bounded_validation_errors(schema: str, fmt: str, fixture: str) -> None:
    record = load(fixture)
    with pytest.raises(oatschema.ValidationError) as caught:
        get_adapter(schema, fmt).export(record)
    error = caught.value
    assert error.schema_name == schema
    assert error.schema_version == "0.8.0"
    assert error.keyword
    assert isinstance(error, ValueError)
    assert len(str(error)) < 1200


@pytest.mark.parametrize(("schema", "fmt"), [(s, f) for s, formats in OATS_FORMATS.items() for f in formats])
def test_unbundled_version_raises_lookup_error(schema: str, fmt: str) -> None:
    record = load(FIXTURES[schema][0])
    with pytest.raises(LookupError, match="schema version '9.9.9' is not bundled"):
        get_adapter(schema, fmt).export(record, schema_version="9.9.9")


@pytest.mark.parametrize(("schema", "fmt"), [(s, f) for s, formats in OATS_FORMATS.items() for f in formats])
@pytest.mark.parametrize("validate", [True, False])
def test_records_must_be_dicts(schema: str, fmt: str, validate: bool) -> None:
    function = get_adapter(schema, fmt)._export_fn
    assert function is not None
    with pytest.raises(TypeError, match="the record must be a dict, not list"):
        function([], validate=validate)

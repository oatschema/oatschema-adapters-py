# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import gzip
import json
import typing
from pathlib import Path

import oatschema
import pytest

from conftest import load
from oatschema_adapters import ParsedRecord, get_adapter, list_formats, list_schemas

SCHEMAS = sorted(typing.get_args(oatschema.SchemaName))
FIXTURES = {
    schema: "document-extraction-text-only" if schema == "document-extraction" else f"{schema}-1" for schema in SCHEMAS
}


def _versions(schema: str) -> list[str]:
    versions = []
    for version in oatschema.available_versions():
        try:
            oatschema.get_schema(typing.cast(oatschema.SchemaName, schema), version)
        except LookupError:
            continue
        versions.append(version)
    return versions


CASES = [(schema, version) for schema in SCHEMAS for version in _versions(schema)]


def test_every_oats_schema_has_a_json_adapter() -> None:
    assert list_schemas() == SCHEMAS
    for schema in SCHEMAS:
        assert "json" in dict(list_formats(schema))


@pytest.mark.parametrize(("schema", "version"), CASES)
def test_round_trip_at_every_version(schema: str, version: str) -> None:
    adapter = get_adapter(schema, "json")
    record = load(FIXTURES[schema])
    text = adapter.export(record, schema_version=version)
    assert json.loads(text) == record
    parsed = adapter.parse(text, schema_version=version)
    assert parsed == record
    oatschema.validate(parsed, schema, version)  # type: ignore[arg-type]


@pytest.mark.parametrize("schema", SCHEMAS)
def test_json_gz_round_trip(tmp_path: Path, schema: str) -> None:
    adapter = get_adapter(schema, "json")
    record = load(FIXTURES[schema])
    path = tmp_path / "record.json.gz"
    adapter.export_file(record, path)
    assert json.loads(gzip.decompress(path.read_bytes())) == record
    assert adapter.parse_file(path) == record


@pytest.mark.parametrize("schema", SCHEMAS)
def test_invalid_records_raise(schema: str) -> None:
    adapter = get_adapter(schema, "json")
    with pytest.raises(oatschema.ValidationError):
        adapter.export({"not a field": 1})
    with pytest.raises(oatschema.ValidationError):
        adapter.parse('{"not a field": 1}')
    assert adapter.export({"not a field": 1}, validate=False)
    assert adapter.parse('{"not a field": 1}', validate=False) == {"not a field": 1}


def test_non_ascii_is_kept_and_bytes_are_accepted() -> None:
    adapter = get_adapter("llm-output", "json")
    text = adapter.export(load("llm-output-1"))
    assert "héllo" in text
    assert adapter.parse(text.encode("utf-8"))["response_data"] == "héllo"


def test_llm_output_seed_is_converted_and_reported() -> None:
    adapter = get_adapter("llm-output", "json")
    record = {**load("llm-output-1"), "generation_params": {"seed": 222}}
    parsed = adapter.parse(json.dumps(record))
    assert parsed["generation_params"]["seed"] == "222"
    assert isinstance(parsed, ParsedRecord)
    assert [(item.path, item.before, item.after) for item in parsed.converted] == [
        (("generation_params", "seed"), 222, "222")
    ]


def test_integers_beyond_the_range_are_never_rounded() -> None:
    adapter = get_adapter("generic", "json")
    with pytest.warns(oatschema.DroppedNumberWarning):
        parsed = adapter.parse('{"data": {"a": 9007199254740993, "b": 1}}')
    assert parsed["data"] == {"b": 1}
    assert isinstance(parsed, ParsedRecord)
    assert parsed.dropped[0].value == 9007199254740993


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_export_refuses_what_json_cant_hold(bad: float) -> None:
    with pytest.raises(ValueError, match="not JSON compliant"):
        get_adapter("generic", "json").export({"data": {"a": bad}}, validate=False)


def test_json_options_are_named() -> None:
    adapter = get_adapter("generic", "json")
    with pytest.raises(TypeError, match="unknown option"):
        adapter.export(load("generic-1"), indent=4)
    with pytest.raises(TypeError, match="unknown option"):
        adapter.parse("{}", producer="me")

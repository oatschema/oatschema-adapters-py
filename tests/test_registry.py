# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import io
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import pytest

import oatschema_adapters
from oatschema_adapters import Adapter, format_aliases, get_adapter, list_formats, list_schemas, register_adapter
from oatschema_adapters import _registry

OATS_FORMATS = {
    "audio-transcription": ["md", "srt", "tsv", "txt", "vtt"],
    "document-extraction": ["hocr", "html", "md", "tsv", "txt"],
}
PARSERS = {
    "audio-transcription": {"md", "srt", "tsv", "txt", "vtt"},
    "document-extraction": {"hocr", "tsv", "txt"},
}
EXTENSIONS = {"hocr": "hocr.html"}


def _export(record: dict[str, Any], *, extra: str | None = None) -> str:
    return f"exported: {record.get('key')} extra={extra}"


def _parse(content: str, *, extra: str | None = None) -> dict[str, Any]:
    return {"parsed": content, "extra": extra}


@pytest.fixture
def registry() -> Iterator[None]:
    entries = dict(_registry._entries)
    aliases = dict(_registry._aliases)
    yield
    _registry._entries.clear()
    _registry._entries.update(entries)
    _registry._aliases.clear()
    _registry._aliases.update(aliases)


@pytest.fixture
def dummy_adapter() -> Adapter:
    return Adapter("test/schema", "test-fmt", "A test format", "tst", _export, _parse)


def test_adapter_export_dict(dummy_adapter: Adapter) -> None:
    assert dummy_adapter.export({"key": "value"}, extra="yes") == "exported: value extra=yes"


def test_adapter_export_json_str_and_bytes(dummy_adapter: Adapter) -> None:
    assert dummy_adapter.export('{"key": "json_str"}') == "exported: json_str extra=None"
    assert dummy_adapter.export(b'{"key": "json_bytes"}') == "exported: json_bytes extra=None"


def test_adapter_export_invalid_json(dummy_adapter: Adapter) -> None:
    with pytest.raises(ValueError, match="the record is not valid JSON"):
        dummy_adapter.export("{bad json")


@pytest.mark.parametrize("record", [123, [1, 2], "[1, 2]", "null"])
def test_adapter_export_rejects_records_that_are_not_objects(dummy_adapter: Adapter, record: Any) -> None:
    with pytest.raises(TypeError, match="the record must be a JSON object"):
        dummy_adapter.export(record)


def test_adapter_parse_and_files(dummy_adapter: Adapter) -> None:
    assert dummy_adapter.parse("raw", extra="yes") == {"parsed": "raw", "extra": "yes"}
    assert dummy_adapter.parse_file(io.StringIO("file content")) == {"parsed": "file content", "extra": None}
    fp = io.StringIO()
    dummy_adapter.export_file({"key": "file_val"}, fp, extra="yes")
    assert fp.getvalue() == "exported: file_val extra=yes"


def test_adapter_repr_and_capabilities(dummy_adapter: Adapter) -> None:
    assert repr(dummy_adapter) == "Adapter(schema_id='test/schema', format_name='test-fmt')"
    assert dummy_adapter.can_export and dummy_adapter.can_parse


def test_adapter_without_functions_raises_not_implemented() -> None:
    adapter = Adapter("test/schema", "none", "Nothing", "none", None, None)
    assert not adapter.can_export and not adapter.can_parse
    with pytest.raises(NotImplementedError, match="exporting to 'none' isn't supported for 'test/schema'"):
        adapter.export({})
    with pytest.raises(NotImplementedError, match="exporting to 'none' isn't supported"):
        adapter.export_file({}, io.StringIO())
    with pytest.raises(NotImplementedError, match="parsing 'none' isn't supported for 'test/schema'"):
        adapter.parse("x")
    with pytest.raises(NotImplementedError, match="parsing 'none' isn't supported"):
        adapter.parse_file(io.StringIO("x"))


def test_list_schemas() -> None:
    assert list_schemas() == ["audio-transcription", "document-extraction"]


@pytest.mark.parametrize("schema", sorted(OATS_FORMATS))
def test_list_formats(schema: str) -> None:
    formats = list_formats(schema)
    assert [name for name, _ in formats] == OATS_FORMATS[schema]
    assert all(description for _, description in formats)


@pytest.mark.parametrize("schema", ["open/audio-transcription", "audio", "unknown"])
def test_list_formats_of_unknown_schema_is_empty(schema: str) -> None:
    assert list_formats(schema) == []


@pytest.mark.parametrize(("schema", "fmt"), [(s, f) for s, formats in OATS_FORMATS.items() for f in formats])
def test_get_adapter_for_every_format(schema: str, fmt: str) -> None:
    adapter = get_adapter(schema, fmt)
    assert adapter.schema_id == schema
    assert adapter.format_name == fmt
    assert adapter.extension == EXTENSIONS.get(fmt, fmt)
    assert adapter.can_export
    assert adapter.can_parse == (fmt in PARSERS[schema])


@pytest.mark.parametrize(
    ("schema", "alias", "fmt"),
    [
        ("audio-transcription", "markdown", "md"),
        ("audio-transcription", "webvtt", "vtt"),
        ("document-extraction", "markdown", "md"),
        ("document-extraction", "hocr.html", "hocr"),
    ],
)
def test_format_aliases(schema: str, alias: str, fmt: str) -> None:
    assert get_adapter(schema, alias).format_name == fmt
    assert format_aliases(schema)[alias] == fmt


def test_one_way_adapter_cannot_parse() -> None:
    adapter = get_adapter("document-extraction", "html")
    with pytest.raises(NotImplementedError, match="parsing 'html' isn't supported for 'document-extraction'"):
        adapter.parse("<p>x</p>")


def test_get_adapter_unknown_format_lists_formats() -> None:
    with pytest.raises(ValueError, match="no 'fake' adapter for schema 'audio-transcription'; formats: md, srt"):
        get_adapter("audio-transcription", "fake")


def test_get_adapter_unknown_schema() -> None:
    with pytest.raises(ValueError, match="no adapters for schema 'classification'$"):
        get_adapter("classification", "txt")


def test_get_adapter_explains_the_old_prefix() -> None:
    with pytest.raises(ValueError, match="OATS schema names have no 'open/' prefix: use 'document-extraction'"):
        get_adapter("open/document-extraction", "html")


@pytest.mark.parametrize(("schema", "fmt"), [(1, "txt"), ("document-extraction", None)])
def test_get_adapter_rejects_non_str_names(schema: Any, fmt: Any) -> None:
    with pytest.raises(TypeError, match="must be a str"):
        get_adapter(schema, fmt)


def test_register_lazy_adapter_with_aliases(registry: None) -> None:
    register_adapter(
        "example/schema",
        "json",
        description="JSON",
        extension="json",
        export="json:dumps",
        parse="json:loads",
        aliases=["js", "json", "js"],
    )
    assert "example/schema" in list_schemas()
    assert list_formats("example/schema") == [("json", "JSON")]
    assert format_aliases("example/schema") == {"js": "json"}
    adapter = get_adapter("example/schema", "js")
    assert adapter.format_name == "json"
    assert adapter.export({"a": 1}) == '{"a": 1}'
    assert adapter.parse('{"b": 2}') == {"b": 2}


def test_register_callable_adapter(registry: None) -> None:
    register_adapter("example/schema", "fmt", description="Format", extension="f", export=_export)
    adapter = get_adapter("example/schema", "fmt")
    assert adapter.export({"key": "k"}) == "exported: k extra=None"
    assert not adapter.can_parse


def test_register_adds_a_format_to_an_oats_schema(registry: None) -> None:
    register_adapter("document-extraction", "json", description="JSON", extension="json", export="json:dumps")
    assert "json" in [name for name, _ in list_formats("document-extraction")]


def test_register_refuses_to_shadow_a_format(registry: None) -> None:
    with pytest.raises(ValueError, match="'md' is already registered for schema 'document-extraction'"):
        register_adapter("document-extraction", "md", description="Mine", extension="md", export=_export)
    assert get_adapter("document-extraction", "md").description.startswith("Markdown")


def test_register_replace(registry: None) -> None:
    register_adapter("example/schema", "fmt", description="Old", extension="o", export=_export, aliases=["old"])
    register_adapter(
        "example/schema", "fmt", description="New", extension="n", export=_export, aliases=["new"], replace=True
    )
    assert get_adapter("example/schema", "new").description == "New"
    assert format_aliases("example/schema") == {"new": "fmt"}
    with pytest.raises(ValueError, match="no 'old' adapter"):
        get_adapter("example/schema", "old")


def test_register_refuses_alias_clashes(registry: None) -> None:
    with pytest.raises(ValueError, match="alias 'md' is already a format of schema 'document-extraction'"):
        register_adapter("document-extraction", "x", description="X", extension="x", export=_export, aliases=["md"])
    with pytest.raises(ValueError, match="alias 'markdown' already belongs to 'md'"):
        register_adapter(
            "document-extraction", "x", description="X", extension="x", export=_export, aliases=["markdown"]
        )
    with pytest.raises(ValueError, match="'markdown' is already an alias of 'md'"):
        register_adapter("document-extraction", "markdown", description="X", extension="x", export=_export)


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"export": None, "parse": None}, ValueError, "needs an export or a parse function"),
        ({"export": "no_colon"}, TypeError, "export must be a callable, a 'module:function' str"),
        ({"parse": 3}, TypeError, "parse must be a callable"),
        ({"description": ""}, ValueError, "the description must be a non-empty str"),
        ({"extension": 3}, TypeError, "the extension must be a str"),
        ({"aliases": [" x"]}, ValueError, "the format alias must be a non-empty str"),
        ({"aliases": "bib"}, TypeError, "aliases must be a list of str, not the str 'bib'"),
    ],
)
def test_register_checks_arguments(registry: None, kwargs: dict[str, Any], error: type, message: str) -> None:
    arguments: dict[str, Any] = {"description": "D", "extension": "e", "export": _export, **kwargs}
    with pytest.raises(error, match=message):
        register_adapter("example/schema", "fmt", **arguments)


def test_register_rejects_bad_names(registry: None) -> None:
    with pytest.raises(ValueError, match="the schema name must be a non-empty str"):
        register_adapter("", "fmt", description="D", extension="e", export=_export)
    with pytest.raises(TypeError, match="the format name must be a str"):
        register_adapter("s", None, description="D", extension="e", export=_export)  # type: ignore[arg-type]


def test_registered_target_must_be_callable(registry: None) -> None:
    register_adapter("example/schema", "fmt", description="D", extension="e", export="json:__name__")
    with pytest.raises(TypeError, match="'json:__name__' is not callable"):
        get_adapter("example/schema", "fmt")


def test_importing_the_package_imports_no_adapter() -> None:
    script = (
        "import sys, oatschema_adapters, oatschema_adapters.audio, oatschema_adapters.document\n"
        "prefixes = ('oatschema_adapters.', 'oatschema.', 'jsonschema_rs', 'srt', 'webvtt')\n"
        "loaded = sorted(m for m in sys.modules if m.startswith(prefixes) or m == 'oatschema')\n"
        "print(','.join(loaded))\n"
        "oatschema_adapters.get_adapter('audio-transcription', 'srt')\n"
        "print('oatschema_adapters.audio._srt' in sys.modules, 'oatschema_adapters.audio._vtt' in sys.modules)\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    loaded, after = result.stdout.splitlines()
    assert loaded.split(",") == [
        "oatschema_adapters._builtin",
        "oatschema_adapters._registry",
        "oatschema_adapters.audio",
        "oatschema_adapters.document",
    ]
    assert after == "True False"


def test_subpackages_export_their_functions_lazily() -> None:
    from oatschema_adapters import audio, document

    assert sorted(audio.__all__) == sorted(
        f"{d}_{f}" for f in OATS_FORMATS["audio-transcription"] for d in ("from", "to")
    )
    assert set(document.__all__) == {
        "to_html",
        "to_hocr",
        "from_hocr",
        "to_md",
        "to_tsv",
        "from_tsv",
        "to_txt",
        "from_txt",
    }
    assert document.to_html is get_adapter("document-extraction", "html")._export_fn
    assert set(document.__all__) <= set(dir(document))
    with pytest.raises(AttributeError, match="has no attribute 'nothing'"):
        document.nothing  # noqa: B018
    with pytest.raises(AttributeError, match="has no attribute 'nothing'"):
        audio.nothing  # noqa: B018


def test_version() -> None:
    import importlib.metadata

    assert oatschema_adapters.__version__ == importlib.metadata.version("oatschema-adapters")

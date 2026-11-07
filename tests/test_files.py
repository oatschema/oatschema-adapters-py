# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import gzip
import io
from pathlib import Path

import pytest

from conftest import load
from oatschema_adapters import get_adapter
from test_registry import OATS_FORMATS

FIXTURE = {"audio-transcription": "audio-transcription-1", "document-extraction": "document-extraction-3"}
CASES = [(schema, fmt) for schema, formats in OATS_FORMATS.items() for fmt in formats]


@pytest.mark.parametrize(("schema", "fmt"), CASES)
@pytest.mark.parametrize("as_str", [True, False])
def test_gz_paths_hold_exactly_what_export_returns(tmp_path: Path, schema: str, fmt: str, as_str: bool) -> None:
    adapter = get_adapter(schema, fmt)
    record = load(FIXTURE[schema])
    path = tmp_path / f"out.{fmt}.gz"
    adapter.export_file(record, str(path) if as_str else path)
    assert path.read_bytes()[:2] == b"\x1f\x8b"
    assert gzip.decompress(path.read_bytes()) == adapter.export(record).encode("utf-8")


@pytest.mark.parametrize(("schema", "fmt"), [case for case in CASES if get_adapter(*case).can_parse])
def test_gz_and_plain_paths_parse_the_same(tmp_path: Path, schema: str, fmt: str) -> None:
    adapter = get_adapter(schema, fmt)
    record = load(FIXTURE[schema])
    plain = tmp_path / f"out.{fmt}"
    zipped = tmp_path / f"out.{fmt}.gz"
    adapter.export_file(record, plain)
    adapter.export_file(record, zipped)
    expected = adapter.parse(adapter.export(record))
    assert adapter.parse_file(plain) == expected
    assert adapter.parse_file(zipped) == expected
    assert adapter.parse_file(str(zipped), schema_version="0.9.0") == expected


def test_paths_keep_the_exact_bytes_on_every_platform(tmp_path: Path) -> None:
    adapter = get_adapter("audio-transcription", "tsv")
    record = load("audio-transcription-1")
    path = tmp_path / "out.tsv"
    adapter.export_file(record, path)
    assert path.read_bytes() == adapter.export(record).encode("utf-8")
    assert b"\r\n" in path.read_bytes()


def test_gzip_output_is_reproducible(tmp_path: Path) -> None:
    adapter = get_adapter("audio-transcription", "srt")
    record = load("audio-transcription-1")
    first, second = tmp_path / "a.srt.gz", tmp_path / "b.srt.gz"
    adapter.export_file(record, first)
    adapter.export_file(record, second)
    assert first.read_bytes() == second.read_bytes()


def test_the_gz_suffix_ignores_case(tmp_path: Path) -> None:
    adapter = get_adapter("audio-transcription", "txt")
    path = tmp_path / "A.TXT.GZ"
    adapter.export_file({"text": "hi"}, path)
    assert adapter.parse_file(path)["text"] == "hi"


def test_only_a_gz_path_is_gunzipped(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_bytes(gzip.compress(b"hi"))
    with pytest.raises(ValueError, match="not valid UTF-8"):
        get_adapter("audio-transcription", "txt").parse_file(path)


def test_a_byte_order_mark_is_not_content(tmp_path: Path) -> None:
    path = tmp_path / "a.tsv"
    path.write_bytes(b"\xef\xbb\xbfstart_time\ttext\n1\thi\n")
    assert get_adapter("audio-transcription", "tsv").parse_file(path)["segments"][0]["text"] == "hi"


def test_file_objects_work_as_before() -> None:
    adapter = get_adapter("audio-transcription", "txt")
    written = io.StringIO()
    adapter.export_file({"text": "hi"}, written)
    assert written.getvalue() == "hi"
    written.seek(0)
    assert adapter.parse_file(written)["text"] == "hi"


def test_options_reach_the_parser_and_exporter(tmp_path: Path) -> None:
    adapter = get_adapter("audio-transcription", "txt")
    path = tmp_path / "a.txt.gz"
    adapter.export_file({"text": "hi"}, path, validate=False)
    assert adapter.parse_file(path, producer="me")["producer"] == "me"
    with pytest.raises(TypeError, match="unknown option"):
        adapter.parse_file(path, nope=1)
    with pytest.raises(TypeError, match="unknown option"):
        adapter.export_file({"text": "hi"}, path, nope=1)


def test_a_failed_export_leaves_no_file(tmp_path: Path) -> None:
    path = tmp_path / "a.txt.gz"
    with pytest.raises(ValueError):
        get_adapter("audio-transcription", "txt").export_file({"text": "hi", "language": "nope"}, path)
    assert not path.exists()


def test_a_surrogate_cant_be_written_to_a_path(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    with pytest.raises(ValueError, match="can't be written as UTF-8") as caught:
        get_adapter("audio-transcription", "txt").export_file({"text": "hi \ud800"}, path, validate=False)
    assert not isinstance(caught.value, UnicodeError)
    assert not path.exists()


def test_exporter_only_adapters_refuse_parse_file_first(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError):
        get_adapter("document-extraction", "md").parse_file(tmp_path / "missing.md.gz")

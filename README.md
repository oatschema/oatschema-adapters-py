# oatschema-adapters

[![PyPI](https://img.shields.io/pypi/v/oatschema-adapters.svg)](https://pypi.org/project/oatschema-adapters/)
[![Python versions](https://img.shields.io/pypi/pyversions/oatschema-adapters.svg)](https://pypi.org/project/oatschema-adapters/)
[![CI](https://github.com/oatschema/oatschema-adapters-py/actions/workflows/ci.yml/badge.svg)](https://github.com/oatschema/oatschema-adapters-py/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/oatschema/oatschema-adapters-py/graph/badge.svg)](https://codecov.io/gh/oatschema/oatschema-adapters-py)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/oatschema/oatschema-adapters-py/blob/main/LICENSE)

Export [OATS](https://oatschema.org) (Open Annotation Task Schemas) records to standard formats, and parse those formats back into records.

- **`audio-transcription`** records become SRT or WebVTT subtitles, Markdown, plain text or a TSV table, and each of those parses back.
- **`document-extraction`** records become HTML, hOCR, Markdown, plain text or a TSV table. hOCR, plain text and TSV parse back.
- **Validated.** Records are validated with [oatschema](https://pypi.org/project/oatschema/) before export and after parsing, against the schema version you name.
- **Safe with untrusted records.** Every value is escaped in HTML and hOCR, whether or not the record was validated, and no TSV cell runs as a spreadsheet formula.
- **Typed.** Ships `py.typed`.

## Quick start

```
pip install oatschema-adapters
```

```python
from oatschema_adapters import get_adapter

record = {
    "language": "eng",
    "segments": [
        {"text": "Welcome back.", "start_time": 0.5, "end_time": 2.25, "speaker": {"id": "s1", "name": "Maria"}},
        {"text": "Thank you.", "start_time": 2.5, "end_time": 3.0, "speaker": {"id": "s2", "name": "Jean"}},
    ],
}

vtt = get_adapter("audio-transcription", "vtt")
captions = vtt.export(record, include_speakers=True)
# WEBVTT
#
# 00:00:00.500 --> 00:00:02.250
# <v Maria>Welcome back.
# ...

parsed = vtt.parse(captions)  # an audio-transcription record, validated
```

Requires Python 3.11 or later.

## Formats

| Schema | Format | Aliases | Extension | Parses |
| :--- | :--- | :--- | :--- | :--- |
| `audio-transcription` | `srt` | | `srt` | yes |
| | `vtt` | `webvtt` | `vtt` | yes |
| | `md` | `markdown` | `md` | yes |
| | `txt` | | `txt` | yes |
| | `tsv` | | `tsv` | yes |
| `document-extraction` | `html` | | `html` | no |
| | `hocr` | `hocr.html` | `hocr.html` | yes |
| | `md` | `markdown` | `md` | no |
| | `txt` | | `txt` | yes |
| | `tsv` | | `tsv` | yes |

`list_schemas()` and `list_formats(schema)` list them at run time, and `format_aliases(schema)` maps each alias to its format.

```python
from oatschema_adapters import get_adapter, list_formats

list_formats("document-extraction")
# [('hocr', 'hOCR (.html) - ...'), ('html', 'Semantic HTML (.html) - ...'), ...]

adapter = get_adapter("document-extraction", "markdown")
adapter.format_name  # 'md'
adapter.extension  # 'md'
adapter.can_parse  # False
```

An `Adapter` has `export(record, **options)` and `parse(content, **options)`, and `export_file` and `parse_file` for file objects. `export` takes a dict, or a JSON object as `str` or `bytes`.

## Options

Every exporter and parser takes `validate` (default `True`) and `schema_version` (default `None`, the newest version `oatschema` bundles). Parsers also take `producer`, the parsed record's `producer`.

| Schema | Format | Export options |
| :--- | :--- | :--- |
| `audio-transcription` | `srt`, `vtt`, `tsv` | `include_speakers=False` |
| | `md` | `include_timestamps=True`, `include_milliseconds=False`, `include_speakers=False`, `include_frontmatter=True`, `low_confidence_threshold=0.8` |
| `document-extraction` | `html` | `layout="col"` (`"col"`, `"grid"` or `"wireframe"`), `style="default"` (`"default"`, `"dark"` or `"none"`), `style_path=None`, `footer=None`, `fragment=False`, `gap_x=-1.0`, `gap_y=-1.0`, and the layout options below |
| | `md` | `include_frontmatter=True`, `low_confidence_threshold=0.8`, and the layout options below |
| | `txt` | the layout options below |

The layout options decide how blocks are joined into lines and paragraphs: `strict=False`, `line_tolerance=5.0`, `paragraph_margin=20.0`, `column_jump=-10.0` and `scale=None`. The document `tsv` parser takes `unit="px"`, and the `hocr` parser takes `target_class="ocr_line"`.

Options are keyword arguments. A value given as a string, as from a command line, is converted to the option's type: `"false"`, `"no"`, `"off"` and `"0"` are false, and `"0.5"` is a number. A value that can't be converted, or an option the adapter doesn't have, raises an error naming it:

```python
adapter.export(record, include_speakers="maybe")
# ValueError: to_vtt() option 'include_speakers' must be true or false, not 'maybe'
adapter.export(record, include_speaker=True)
# TypeError: to_vtt() got unknown option(s) 'include_speaker'; options: validate, schema_version, include_speakers
```

You can also call the functions directly, from `oatschema_adapters.audio` and `oatschema_adapters.document`:

```python
from oatschema_adapters.document import to_html

fragment = to_html(document_record, layout="wireframe", fragment=True)
```

## Validation

Records are validated before they're exported, and parsed records before they're returned. A record that doesn't conform raises `oatschema.ValidationError`, which says where and why without quoting the record's values:

```python
import oatschema

try:
    get_adapter("audio-transcription", "srt").export({"segments": [{"text": "hi", "start_time": -1, "end_time": 1}]})
except oatschema.ValidationError as error:
    print(error)  # audio-transcription 0.8.0 at /segments/0/start_time: … is less than the minimum of 0
    print(error.keyword)  # minimum
```

Pass `schema_version="0.6.0"` to validate against an older version, such as the one a stored record was written for; any version from 0.4.0 that `oatschema` bundles works. An unbundled version raises `LookupError`. Pass `validate=False` to skip validation.

Output is escaped whether or not the record was validated, so `validate=False` is safe for untrusted records: every value is escaped in HTML and hOCR, a `style` value is only ever a theme name, never a file to read, and a stylesheet from `style_path` can't close its `<style>` element.

## TSV and spreadsheets

A TSV cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return gets a leading `'`, unless the whole cell is a number, so Excel, LibreOffice Calc and Google Sheets show it as text instead of running it as a formula. A cell that already starts with `'` followed by one of those characters gets another `'`. The TSV parsers remove exactly one, so exporting and parsing gives back the original text. The one exception is the audio exporter, which, as before, replaces tabs in a segment's text with spaces and trims surrounding whitespace.

## Adding adapters

`register_adapter` adds an adapter to the same registry, for another schema or another format of an OATS schema. Give the functions as `"module:function"` strings, so they're imported only when used:

```python
from oatschema_adapters import get_adapter, register_adapter

register_adapter(
    "example/citation",
    "bibtex",
    description="BibTeX (.bib) - A bibliographic reference format.",
    extension="bib",
    export="my_package.bibtex:to_bibtex",
    aliases=["bib"],
)

get_adapter("example/citation", "bib").export(record)
```

The export function takes the record first and its options as keyword arguments; a parse function takes the content first. Registering a format that already exists raises `ValueError` unless you pass `replace=True`. Validating records of schemas other than OATS is up to your functions.

## Versions

`oatschema-adapters` uses [semantic versioning](https://semver.org), independently of the OATS schema versions. Until 1.0, a minor release (0.2.0) may change the API, and a patch release (0.1.1) won't. Pin with `oatschema-adapters>=0.1,<0.2`. It depends on `oatschema[validate]>=0.8.0.2,<0.9`.

See the [CHANGELOG](https://github.com/oatschema/oatschema-adapters-py/blob/main/CHANGELOG.md) for what changed in each release.

## License

Apache-2.0. Copyright The OATS Authors; see [AUTHORS](https://github.com/oatschema/oatschema-adapters-py/blob/main/AUTHORS).

# oatschema-adapters

[![PyPI](https://img.shields.io/pypi/v/oatschema-adapters.svg)](https://pypi.org/project/oatschema-adapters/)
[![Python versions](https://img.shields.io/pypi/pyversions/oatschema-adapters.svg)](https://pypi.org/project/oatschema-adapters/)
[![CI](https://github.com/oatschema/oatschema-adapters-py/actions/workflows/ci.yml/badge.svg)](https://github.com/oatschema/oatschema-adapters-py/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/oatschema/oatschema-adapters-py/graph/badge.svg)](https://codecov.io/gh/oatschema/oatschema-adapters-py)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/oatschema/oatschema-adapters-py/blob/main/LICENSE)

Export [OATS](https://oatschema.org) (Open Annotation Task Schemas) records to standard formats, and parse those formats back into records.

- **`audio-transcription`** records become SRT or WebVTT subtitles, Markdown, plain text or a TSV table, and each of those parses back.
- **`document-extraction`** records become HTML, hOCR, Markdown, plain text or a TSV table. hOCR, plain text and TSV parse back.
- **Every OATS schema** has a `json` adapter, so a record can be read and written as it is, with `.json.gz` files too.
- **Validated.** Records are validated with [oatschema](https://pypi.org/project/oatschema/) before export, and parsed records have their numbers checked and are validated, against the schema version you name.
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
| Every OATS schema | `json` | | `json` | yes |
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

An `Adapter` has `export(record, **options)` and `parse(content, **options)`, and `export_file` and `parse_file` for files. `export` takes a dict, or a JSON object as `str` or `bytes`.

## Files and gzip

`export_file` and `parse_file` take an open file object or a path. A path is read and written as UTF-8, and one ending in `.gz` is compressed or decompressed for you, whatever the format:

```python
adapter = get_adapter("audio-transcription", "srt")
adapter.export_file(record, "captions.srt.gz")
parsed = adapter.parse_file("captions.srt.gz")

get_adapter("classification", "json").parse_file("labels.json.gz", max_size=16 * 1024 * 1024)
```

`parse_file` stops reading at `max_size`, keyword-only, 256 MiB by default, and raises `ValueError` beyond it. For a `.gz` path it counts decompressed bytes, so a small file that expands enormously fails without being expanded. A `.gz` file that isn't valid gzip raises `ValueError`. A file object is read and written as it is, so gzip applies only to paths: for your own file objects, use `gzip.open(path, "rt", encoding="utf-8")`, since these parsers take text.

## Options

Every exporter and parser takes `validate` (default `True`) and `schema_version` (default `None`, the newest version `oatschema` bundles). Parsers also take `on_bad_number` (see [Numbers on import](#numbers-on-import)), and every parser but `json` takes `producer`, the parsed record's `producer`. The Markdown parser uses the frontmatter's producer if you don't pass one.

| Schema | Format | Export options |
| :--- | :--- | :--- |
| `audio-transcription` | `srt`, `vtt`, `tsv` | `include_speakers=False` |
| | `md` | `include_timestamps=True`, `include_milliseconds=False`, `include_speakers=False`, `include_frontmatter=True`, `low_confidence_threshold=0.8` |
| `document-extraction` | `html` | `layout="col"` (`"col"`, `"grid"` or `"wireframe"`), `style="default"` (`"default"`, `"dark"` or `"none"`), `style_path=None`, `footer=None`, `fragment=False`, `gap_x=-1.0`, `gap_y=-1.0`, and the layout options below |
| | `md` | `include_frontmatter=True`, `low_confidence_threshold=0.8`, and the layout options below |
| | `txt` | the layout options below |

The layout options decide how blocks are joined into lines and paragraphs: `strict=False`, `line_tolerance=5.0`, `paragraph_margin=20.0`, `column_jump=-10.0` and `scale=None`. The document `tsv` parser takes `unit="px"`, the `hocr` parser takes `target_class="ocr_line"`, and the `srt` parser takes `include_speakers=False`.

`adapter.export_options` and `adapter.parse_options` list an adapter's options at run time. Each is an `AdapterOption` with a `name`, `type`, `default`, `required` and `description`:

```python
option = get_adapter("audio-transcription", "srt").export_options[-1]
option.name, option.type, option.default  # ('include_speakers', 'true or false', False)
```

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

Records are validated before they're exported. A record that doesn't conform raises `oatschema.ValidationError`, which says where and why without quoting the record's values:

```python
import oatschema

try:
    get_adapter("audio-transcription", "srt").export({"segments": [{"text": "hi", "start_time": -1, "end_time": 1}]})
except oatschema.ValidationError as error:
    print(error)  # audio-transcription 0.9.0 at /segments/0/start_time: … is less than the minimum of 0
    print(error.keyword)  # minimum
```

With no `schema_version`, a record is validated at the newest version `oatschema` bundles, now 0.9.0. Pass `schema_version="0.6.0"` to validate against an older version, such as the one a stored record was written for; any version from 0.4.0 that `oatschema` bundles works. An unbundled version raises `LookupError`. Pass `validate=False` to skip validation.

A schema version's files never change, but a verdict can: `oatschema` can tighten its own checks. Since `oatschema` 0.9.0.0, a string or key with an unpaired surrogate, and a malformed `date-time`, are invalid at every schema version, so a stored record that has one no longer exports unless you pass `validate=False`.

Output is escaped whether or not the record was validated, so `validate=False` is safe for untrusted records: every value is escaped in HTML and hOCR, a `style` value is only ever a theme name, never a file to read, and a stylesheet from `style_path` can't close its `<style>` element.

## Numbers on import

A parsed record has been through `oatschema.check_numbers` and validation at the version you name. Parsers return a `ParsedRecord`, a dict with two more attributes, which list everything `check_numbers` did. It never rounds a number:

```python
parsed = get_adapter("document-extraction", "hocr").parse(content)
parsed.dropped  # (DroppedNumber(path, value, reason), ...), each also reported by one DroppedNumberWarning
parsed.converted  # (ConvertedNumber(path, before, after), ...), rewritten without changing the value, like -0.0 to 0.0
```

- A bad number is NaN, ±infinity, beyond ±9007199254740991, or outside its field's bounds, such as an hOCR `x_wconf` of 150. In an optional property it is dropped. In a required property or a list, it rejects the record with `ValidationError`.
- `on_bad_number="raise"` rejects the record for any bad number.
- An invalid record with more than 250,000 values is rejected outright, so nothing is dropped from it, and the error doesn't say where it is invalid, because finding that out can take gigabytes.
- `validate=False` skips all of this, including the bounds, and `dropped` and `converted` are empty.
- With or without `validate`, a parser refuses, with `ValueError`, text that holds no number a double can represent without rounding: `nan`, `inf`, `1e400`, `1e-400` and `1.00000000000000001`. A double written to any number of digits, such as `0.10000000000000001`, reads back as itself. The same goes for `NaN` and `Infinity` in JSON, where a key repeated in an object is refused too.
- The one value that can be rounded is one a parser computes rather than reads: an hOCR box's `width` and `height`, and its `score`. These are computed exactly, so `bbox 0.1 0.2 0.3 0.4` gives a width of 0.2, and then stored as the nearest double.

Malformed content raises `ValueError`, with a short message that never repeats the content at length. To limit what hostile content can cost, with or without `validate`: a table has at most 100,000 rows, 256 columns and 16 MiB a cell, and can't name a column it reads twice, while other columns and cells past the end of the header are ignored; SRT, WebVTT and Markdown have at most 100,000 segments; hOCR has at most 100,000 blocks and pages and 256 nested elements; and JSON has at most 4,000,000 commas and opening brackets, 64 nested levels and 1,024 characters in a key. A schema-valid `json` record beyond these limits, such as thousands of blocks with 1,000-point polygons, is refused.

## What each format holds

A round trip through a format keeps what the format can hold. These are not kept:

| Format | Not kept |
| :--- | :--- |
| `json` | Nothing |
| Every audio format but `json` | A segment's `language`, `score`, `id` and `attributes`, and a speaker's `score`. A record's `text` becomes its segments' text joined, where it has segments |
| Audio `srt` | The record's other fields, and `events`. Times are milliseconds. Segments are sorted by start time, and empty ones, and ones that don't end after they start, are left out. A newline in text becomes a space, and text is trimmed. A speaker's `id` becomes its name, a speaker with no name is lost, and speakers are read only with `include_speakers=True` |
| Audio `vtt` | The record's other fields, and `events`. Times are milliseconds. A newline in text becomes a space, text is trimmed, and whitespace in a speaker's name collapses. A speaker's `id` becomes its name, and a speaker with no name is lost |
| Audio `md` | A segment's `score` is shown only as a low-confidence note, to two places. Times are seconds, or milliseconds with `include_milliseconds=True`. A speaker's `id` becomes its name, and a speaker with no name is lost. A name containing `:` isn't read back, and an event containing `,` is split. A line break in text starts a new segment with times of 0. An empty segment with no events, and empty `attributes`, are left out. A record with only `text` reads back with one segment, with times of 0, or fails validation if the text starts with `#`. A text line starting with `#` is left out, `*[x]*` becomes an event, and with `include_timestamps=False` `**` is removed |
| Audio `tsv` | The record's other fields, and `events`. Times are milliseconds, tabs in text become spaces, and text and speakers are trimmed |
| Audio and document `txt` | Everything but the text |
| Document `tsv` | The record's `producer`, `extraction_type`, `unit`, `score_explanation`, page sizes and `attributes`, and a block's `id`, `line_number`, `score` and `attributes`. A block with both a polygon and a multi-polygon keeps the polygon. A box equal to its block's polygon's bounding box reads back as no box. Whole-number coordinates in a box read back as floats, and an empty `text` on a block that doesn't need one is left out |
| `hocr` | The record's `producer`, `attributes`, `score_explanation` and `extraction_type`, and a block's `block_type` and `line_number`. Blocks with no text are left out, and a record with none doesn't parse back, as is a block whose `hocr_class` isn't the parser's `target_class`. A polygon-only block gains a box, and a block with both a polygon and a multi-polygon keeps the polygon. Blocks are grouped by page, and a missing page number becomes 1. A record with no page sizes gains sizes of 1000 by 1000. Each block gains an `hocr_class` attribute, attribute values become strings, and unsafe characters in attribute names become `_`. Scores are cut to a whole percentage, so 0.29 can read back as 0.28. Boxes and page sizes are cut to whole pixels, `normalized` and `per_mille` coordinates are scaled to pixels with polygon points rounded to three places, and whitespace in text collapses |
| Document `html`, `md` | Don't parse back |

## TSV and spreadsheets

A TSV cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return gets a leading `'`, unless the whole cell is a number, so Excel, LibreOffice Calc and Google Sheets show it as text instead of running it as a formula. A cell that already starts with `'` followed by one of those characters gets another `'`. The TSV parsers remove exactly one, so exporting and parsing gives back the original text. The one exception is the audio exporter, which, as before, replaces tabs in a segment's text with spaces and trims surrounding whitespace.

**Excel keeps only 15 significant digits of a number.** Opening a table in Excel and saving it can change a longer number, such as 9007199254740991 or a precise coordinate. Excel also cuts a cell at 32,767 characters, which a large polygon can exceed. To keep every value, read TSV with these parsers rather than through a spreadsheet.

A document table gets a last `polygon` column if any block has a polygon or multi-polygon, as compact JSON: `[[x,y],[x,y],[x,y]]`, or one level deeper for a multi-polygon. The box columns of such a block with no box hold its bounding box. An audio table with `include_speakers=True` gets a last `speaker_id` column if a speaker's id differs from its name.

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

`oatschema-adapters` uses [semantic versioning](https://semver.org), independently of the OATS schema versions. Until 1.0, a minor release (0.2.0) may change the API, and a patch release (0.1.1) won't. Pin with `oatschema-adapters>=0.2,<0.3`. It depends on `oatschema[validate]>=0.9.0.0,<0.10`.

See the [CHANGELOG](https://github.com/oatschema/oatschema-adapters-py/blob/main/CHANGELOG.md) for what changed in each release.

## License

Apache-2.0. Copyright The OATS Authors; see [AUTHORS](https://github.com/oatschema/oatschema-adapters-py/blob/main/AUTHORS).

# Changelog

## 0.2.0 (2026-11-07)

**Pin:** `oatschema-adapters>=0.2,<0.3`. It needs `oatschema[validate]>=0.9.0.0,<0.10`, `webvtt-py>=0.6.0` and Python 3.11 or later.

### Breaking

- With no `schema_version`, records are validated at OATS 0.9.0. For `audio-transcription` and `document-extraction`, the only change from 0.8.0 is that every number is bounded within ±9007199254740991, so a 0.8.0 record exports the same bytes unless it has a number beyond that. Pass `schema_version` to validate at an older version.
- From `oatschema` 0.9.0.0, at every schema version, a string or key with an unpaired surrogate, and a malformed `date-time`, are invalid. So a stored record with one no longer exports, and text with bad UTF-16 no longer imports. `validate=False` still skips validation.
- Parsers run `oatschema.check_numbers`. A bad number in an optional property, such as an hOCR `x_wconf` of 150, is now dropped and reported instead of failing validation. Pass `on_bad_number="raise"` to reject the record.
- Parsers refuse, with `ValueError`, numbers a double can't hold without rounding (`nan`, `inf`, `1e400`, `1e-400`, `1.00000000000000001`), with or without `validate`.
- Document TSV and hOCR raise `ValueError` for a box, score or polygon that isn't a number or valid JSON, and document TSV for a page number that isn't a whole number. hOCR also raises for a repeated or incomplete `bbox` or `x_wconf`, and for two sizes for one page. They used to ignore these.
- `from_vtt` raises `ValueError` for a line with `-->` that isn't a timing it can read, and for a block with no timing, other than the header and `NOTE`, `STYLE` and `REGION` blocks. These used to vanish. `from_md` raises for a line whose time isn't one, such as `**[Music - intro]** la la`, which used to become text.
- `from_srt` reads SRT itself instead of through `srt.parse`, whose time grew steeply on hostile input. It reads what `srt.parse` did, and raises `ValueError` for a time that is out of range or has more than three digits of a second. Its messages give a line number. A line like `nan --> inf` after a caption stays caption text, as before.
- Document TSV output changes for records with polygon or multi-polygon blocks: a new last `polygon` column, and those blocks' box columns hold their bounding box. Other records export the same bytes.
- Audio TSV with `include_speakers=True` gains a last `speaker_id` column if a speaker's id differs from its name, and `from_tsv` reads it. Other records export the same bytes.
- `from_md` reads the frontmatter's `language`, `duration`, `score_explanation`, `track_id` and `attributes`, and its `producer` unless you pass one. `producer` now defaults to `None`, and to `"md-adapter"` if there is no frontmatter producer. Frontmatter that 0.1.0 ignored can now fail the parse: a value the schema refuses, such as `language: en` or `track_id: 3`, raises `ValidationError`, and a `duration` that isn't a number, such as `1:23:45`, or `attributes` that aren't JSON values, raises `ValueError`.
- Document Markdown renders a record with no blocks, such as an image-only PDF's, as "No content extracted from this document." instead of raising `ValueError`. Plain text, TSV and hOCR still raise.
- `parse_file` stops at `max_size` (256 MiB by default) and raises `ValueError`.
- With or without `validate`, tables are limited to 100,000 rows and 256 cells in a row, with no repeated column among those read; SRT, WebVTT and Markdown to 100,000 segments; hOCR to 100,000 blocks, pages and open elements; and JSON to 4,000,000 commas and opening brackets, 64 levels and 1,024 characters in a key. Errors no longer quote the content at length.
- `list_schemas()` now returns all 12 OATS schemas, because each has a `json` adapter. Registering your own `json` format for one of them now needs `replace=True`.

### Added

- A `json` adapter for every OATS schema. Export is the record as JSON text. Parsing checks its numbers and validates it, and refuses `NaN`, `Infinity`, a key repeated in an object, and excessive nesting.
- `export_file` and `parse_file` take a path as well as a file object. A path ending in `.gz` is compressed or decompressed, for every format, including `.json.gz`.
- `ParsedRecord`, what parsers now return: a dict with `dropped` and `converted`.
- `on_bad_number` on every parser, and `include_speakers` on `from_srt`.
- `Adapter.export_options` and `Adapter.parse_options`, lists of `AdapterOption`, for help text.
- The README lists what each format holds, and warns about Excel's 15 digits.

### Fixed

- `to_tsv` then `from_tsv` is lossless for `polygon` and `multi_polygon` blocks.
- A small hostile hOCR, TSV, SRT, JSON or `.gz` file can no longer take unbounded time or memory. An invalid audio or document record with more than 250,000 values is checked a group of segments or blocks at a time, so its bad numbers are still dropped and reported. A segment or block that large, or an invalid record of another schema that large, is rejected without dropping anything, and without saying where it is invalid.
- hOCR widths, heights and scores are computed exactly, then stored as the nearest double: `bbox 0.1 0.2 0.3 0.4` gives a width of 0.2. SRT, WebVTT and Markdown times are computed exactly, and a time a double can't hold is refused.

## 0.1.0 (2026-10-31)

First release.

- Exporters for `audio-transcription` (SRT, WebVTT, Markdown, plain text and TSV) and `document-extraction` (HTML, hOCR, Markdown, plain text and TSV) records, with parsers for every format except document HTML and Markdown.
- Records are validated with `oatschema`, against the newest bundled schema version or the one passed as `schema_version`.
- `register_adapter` adds adapters for other schemas and formats to the same registry.
- Carries over the OATS adapters of `dorsalhub-adapters` 0.4.3, with bare schema names (no `open/` prefix), keyword-only options, and fixes to TSV, WebVTT, Markdown and hOCR output and parsing.

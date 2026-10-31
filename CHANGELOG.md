# Changelog

## 0.1.0 (2026-10-31)

First release.

- Exporters for `audio-transcription` (SRT, WebVTT, Markdown, plain text and TSV) and `document-extraction` (HTML, hOCR, Markdown, plain text and TSV) records, with parsers for every format except document HTML and Markdown.
- Records are validated with `oatschema`, against the newest bundled schema version or the one passed as `schema_version`.
- `register_adapter` adds adapters for other schemas and formats to the same registry.
- Carries over the OATS adapters of `dorsalhub-adapters` 0.4.3, with bare schema names (no `open/` prefix), keyword-only options, and fixes to TSV, WebVTT, Markdown and hOCR output and parsing.

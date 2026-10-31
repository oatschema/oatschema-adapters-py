# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from oatschema_adapters._registry import register_adapter

_AUDIO = "oatschema_adapters.audio"
_DOCUMENT = "oatschema_adapters.document"


def register_builtin_adapters() -> None:
    """Register the adapters this package ships."""
    for fmt, description, extension, aliases in (
        ("srt", "SubRip Text (.srt) - A widely used, plaintext subtitle format.", "srt", ()),
        ("vtt", "WebVTT (.vtt) - W3C standard web subtitle format.", "vtt", ("webvtt",)),
        ("md", "Markdown (.md) - A markdown-formatted audio transcription", "md", ("markdown",)),
        ("txt", "Plain Text (.txt).", "txt", ()),
        ("tsv", "Tab-Separated Values (.tsv).", "tsv", ()),
    ):
        register_adapter(
            "audio-transcription",
            fmt,
            description=description,
            extension=extension,
            export=f"{_AUDIO}._{fmt}:to_{fmt}",
            parse=f"{_AUDIO}._{fmt}:from_{fmt}",
            aliases=aliases,
        )

    for fmt, description, extension, aliases, parses in (
        ("txt", "Plain Text (.txt).", "txt", (), True),
        ("tsv", "Tab-Separated Values (.tsv).", "tsv", (), True),
        ("hocr", "hOCR (.html) - An OCR output format in standard HTML", "hocr.html", ("hocr.html",), True),
        ("md", "Markdown (.md) - A markdown-formatted document transcription", "md", ("markdown",), False),
        ("html", "Semantic HTML (.html) - A responsive, visually inferred layout.", "html", (), False),
    ):
        register_adapter(
            "document-extraction",
            fmt,
            description=description,
            extension=extension,
            export=f"{_DOCUMENT}._{fmt}:to_{fmt}",
            parse=f"{_DOCUMENT}._{fmt}:from_{fmt}" if parses else None,
            aliases=aliases,
        )

# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import copy
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from conftest import load
from oatschema_adapters import get_adapter

HTML_TAGS = {"html", "head", "meta", "title", "style", "body", "div", "p", "em"}
HTML_ATTRIBUTES = {"lang", "charset", "class", "style", "title"}
HOCR_TAGS = {"html", "head", "meta", "title", "body", "div", "span"}
HOCR_ATTRIBUTES = {"charset", "name", "content", "class", "id", "title"}
SAFE_STYLE = re.compile(r"^(?:\s*[a-z-]+: [-0-9.e]+(?:px|%)?;)+(?: max-width: 100%;)?$|^flex: 1;$")
SAFE_CLASS = re.compile(r"^[a-z_ -]+$")


class _Elements(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.style_text: list[str] = []
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))
        self._in_style = tag == "style"

    def handle_endtag(self, tag: str) -> None:
        self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.style_text.append(data)


def _elements(markup: str) -> _Elements:
    parser = _Elements()
    parser.feed(markup)
    parser.close()
    return parser


def _hostile_unvalidated() -> dict[str, Any]:
    record = copy.deepcopy(load("document-extraction-hostile"))
    record["producer"] = ["</title><script>alert('list')</script>"]
    record["unit"] = "\"><script>alert('unit')</script>"
    first = record["blocks"][0]
    first["block_type"] = "<script>alert('type')</script>"
    first["page_number"] = "\"><script>alert('page')</script>"
    first["id"] = {"x": '"><script>'}
    first["attributes"]['\x00 ="x y/>'] = "<script>"
    record["blocks"][1]["block_type"] = '"><svg onload=alert(1)>'
    record["blocks"].append(
        {"block_type": "</div><script>alert('figure')</script>", "box": {"x": 1, "y": 2, "width": 3, "height": 4}}
    )
    return record


HTML_OPTIONS = [
    {"layout": layout, "fragment": fragment, "style": style}
    for layout in ("col", "grid", "wireframe")
    for fragment in (True, False)
    for style in ("default", "dark", "none")
]
RECORDS = [("validated", True), ("unvalidated", False)]


def _record(kind: str) -> dict[str, Any]:
    return load("document-extraction-hostile") if kind == "validated" else _hostile_unvalidated()


def _check_markup(markup: str, tags: set[str], attributes: set[str], data_attributes: bool) -> None:
    assert "<script" not in markup.lower()
    assert "<svg" not in markup.lower() and "<img" not in markup.lower() and "<iframe" not in markup.lower()
    parsed = _elements(markup)
    for tag, attrs in parsed.elements:
        assert tag in tags, tag
        for name, value in attrs.items():
            assert name in attributes or (data_attributes and re.fullmatch(r"data-[^\s\"'<>/=]+", name)), name
            if name == "style":
                assert value is not None and SAFE_STYLE.match(value), value
            if name == "class" and tag != "span" and tag != "div":
                assert value is not None and SAFE_CLASS.match(value), value
    assert "</style" not in "".join(parsed.style_text).lower()


@pytest.mark.parametrize(("kind", "validate"), RECORDS)
@pytest.mark.parametrize("options", HTML_OPTIONS, ids=lambda o: "-".join(f"{k}={v}" for k, v in o.items()))
def test_html_escapes_every_value(kind: str, validate: bool, options: dict[str, Any]) -> None:
    footer = "</div><script>alert('footer')</script>"
    markup = get_adapter("document-extraction", "html").export(
        _record(kind), validate=validate, footer=footer, **options
    )
    _check_markup(markup, HTML_TAGS, HTML_ATTRIBUTES, data_attributes=False)
    assert "&lt;/div&gt;&lt;script&gt;alert(&#x27;footer&#x27;)&lt;/script&gt;" in markup
    for _, attrs in _elements(markup).elements:
        assert attrs.get("class") in (
            None,
            "page-container page-flow",
            "page-container page-wireframe",
            "layout-y",
            "layout-x",
            "col",
            "block-text",
            "figure-placeholder",
            "wireframe-box",
            "page-divider",
            "document-footer",
        )


@pytest.mark.parametrize(("kind", "validate"), RECORDS)
def test_hocr_escapes_every_value(kind: str, validate: bool) -> None:
    markup = get_adapter("document-extraction", "hocr").export(_record(kind), validate=validate)
    _check_markup(markup, HOCR_TAGS, HOCR_ATTRIBUTES, data_attributes=True)
    for tag, attrs in _elements(markup).elements:
        if tag == "span" or (tag == "div" and attrs.get("class") != "ocr_page"):
            title = attrs.get("title")
            assert title is None or re.fullmatch(r"bbox -?\d+ -?\d+ -?\d+ -?\d+(; x_wconf \d+)?", title), title


def test_hocr_round_trips_hostile_text_and_attributes() -> None:
    adapter = get_adapter("document-extraction", "hocr")
    record = load("document-extraction-hostile")
    del record["blocks"][0]["attributes"]["hocr_class"]
    parsed = adapter.parse(adapter.export(record))
    first = parsed["blocks"][0]
    assert first["text"] == record["blocks"][0]["text"]
    assert first["id"] == record["blocks"][0]["id"]
    assert first["attributes"]["visual_class"] == record["blocks"][0]["attributes"]["visual_class"]
    assert first["attributes"]["hocr_class"] == "ocr_line"


@pytest.mark.parametrize("style", ["/etc/passwd", "style.css", str(Path(__file__)), "../secret.css"])
def test_style_paths_are_never_read(style: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    opened: list[Any] = []
    real_open = builtins.open

    def recording_open(*args: Any, **kwargs: Any) -> Any:
        opened.append(args)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", recording_open)
    with pytest.raises(ValueError, match="pass a stylesheet file as 'style_path'"):
        get_adapter("document-extraction", "html").export(load("document-extraction-1"), style=style)
    assert opened == []


def test_style_path_cannot_close_the_style_element(tmp_path: Path) -> None:
    css = tmp_path / "theme.css"
    css.write_text("body { color: red; }</StYlE ><script>alert(1)</script></style>", encoding="utf-8")
    markup = get_adapter("document-extraction", "html").export(load("document-extraction-1"), style_path=css)
    parsed = _elements(markup)
    assert {tag for tag, _ in parsed.elements} <= HTML_TAGS
    assert "</style" not in "".join(parsed.style_text).lower()
    assert markup.lower().count("</style") == 1


def test_markdown_frontmatter_cannot_be_broken_out_of() -> None:
    record = load("document-extraction-hostile")
    record["producer"] = "x\n---\n# injected"
    output = get_adapter("document-extraction", "md").export(record)
    assert output.split("\n")[:2] == ["---", 'producer: "x\\n---\\n# injected"']

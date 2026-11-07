# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import html
import json
import re
from collections import Counter
from html.parser import HTMLParser
from typing import Any, Literal

from oatschema_adapters._numbers import MAX_ITEMS, MAX_KEY, difference, load_json, parse_number, percentage
from oatschema_adapters._options import checked, shorten
from oatschema_adapters._parsed import ParsedRecord
from oatschema_adapters._validation import check_record, finish_parse

_UNSAFE_ATTR_NAME_CHARS = re.compile(r"[\s\"'<>/=&\x00-\x1f\x7f]")
_ATTRIBUTE = re.compile(r"""([^\s"'<>/=]+)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?""")
_TAG_NAME = re.compile(r"<\s*[^\s/>]+")
_PAGE_NUMBER = re.compile(r"\d+")
_WHITESPACE = re.compile(r"\s+")
_MAX_DEPTH = MAX_ITEMS
_RELATIVE_UNITS = {"normalized": 1.0, "per_mille": 1000.0}
_VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)


def _get_page_dimension(dim_data: Any, page_num: int, *, default: int = 1000) -> int:
    if isinstance(dim_data, (int, float)):
        return int(dim_data)
    if isinstance(dim_data, list):
        for config in dim_data:
            if page_num in config.get("pages", []):
                return int(config.get("value", default))
    return default


def _corners(block: dict[str, Any]) -> tuple[float, float, float, float] | None:
    if "box" in block:
        b = block["box"]
        return (b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"])
    points: list[dict[str, Any]] = []
    if "polygon" in block:
        points = block["polygon"]
    elif "multi_polygon" in block:
        for polygon in block["multi_polygon"]:
            points.extend(polygon)
    if not points:
        return None
    xs = [point["x"] for point in points]
    ys = [point["y"] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _scale(unit: Any, width: int, height: int) -> tuple[float, float] | None:
    full = _RELATIVE_UNITS.get(unit)
    if full is None:
        return None
    return width / full, height / full


def _calculate_bbox(block: dict[str, Any], scale: tuple[float, float] | None) -> tuple[int, int, int, int] | None:
    corners = _corners(block)
    if corners is None:
        return None
    x0, y0, x1, y1 = corners
    if scale is None:
        return (int(x0), int(y0), int(x1), int(y1))
    sx, sy = scale
    return (round(x0 * sx), round(y0 * sy), round(x1 * sx), round(y1 * sy))


def _scale_points(points: list[dict[str, Any]], scale: tuple[float, float] | None) -> list[dict[str, Any]]:
    if scale is None:
        return points
    sx, sy = scale
    return [{**point, "x": round(point["x"] * sx, 3), "y": round(point["y"] * sy, 3)} for point in points]


def _page_order(page: Any) -> tuple[int, Any]:
    if isinstance(page, int) and not isinstance(page, bool):
        return (0, page)
    return (1, str(page))


@checked
def to_hocr(
    record: dict[str, Any],
    *,
    validate: bool = True,
    schema_version: str | None = None,
) -> str:
    """Convert a ``document-extraction`` record to an hOCR document, with one element per block.

    Boxes, polygons and multi-polygons become ``bbox`` properties in pixels. ``px`` and ``pt`` coordinates are written
    as they are. ``normalized`` and ``per_mille`` ones, including the points in ``data-polygon``, are scaled to the
    page size, or to 1000 by 1000 if the record doesn't give one. Scores become ``x_wconf``, block attributes become ``data-*`` attributes, and an
    ``hocr_class`` attribute sets the element's class (``ocr_line`` by default). Every value is escaped.

    Args:
        record: The record to convert.
        validate: Validate the record before converting it.
        schema_version: The schema version to validate against, such as ``"0.9.0"``. Defaults to the newest.

    Raises:
        ValueError: The record has no blocks.
        oatschema.ValidationError: The record doesn't conform to the schema.
    """
    check_record(record, "document-extraction", validate=validate, version=schema_version)

    blocks = record.get("blocks", [])
    if not blocks:
        raise ValueError("The provided record contains no 'blocks'.")

    pages: dict[Any, list[dict[str, Any]]] = {}
    for block in blocks:
        pages.setdefault(block.get("page_number", 1), []).append(block)

    unit = record.get("unit")
    output = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        '  <meta charset="utf-8"/>',
        "  <title>hOCR Output</title>",
        f'  <meta name="ocr-system" content="{html.escape(str(record.get("producer", "oatschema-adapters")))}"/>',
        '  <meta name="ocr-capabilities" content="ocr_page ocr_carea ocr_par ocr_line ocrx_word"/>',
        "</head>",
        "<body>",
    ]

    for page_num in sorted(pages, key=_page_order):
        width = _get_page_dimension(record.get("page_width"), page_num, default=1000)
        height = _get_page_dimension(record.get("page_height"), page_num, default=1000)
        output.append(
            f'  <div class="ocr_page" id="page_{html.escape(str(page_num))}" title="bbox 0 0 {width} {height}">'
        )

        scale = _scale(unit, width, height)
        for block in pages[page_num]:
            attrs = dict(block.get("attributes", {}))
            hocr_class = str(attrs.pop("hocr_class", "ocr_line"))

            title_parts = []
            bbox = _calculate_bbox(block, scale)
            if bbox:
                title_parts.append(f"bbox {bbox[0]} {bbox[1]} {bbox[2]} {bbox[3]}")
            if "score" in block:
                title_parts.append(f"x_wconf {int(block['score'] * 100)}")
            title_attr = f' title="{"; ".join(title_parts)}"' if title_parts else ""

            data_attrs = []
            for key, value in attrs.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
                data_attrs.append(f'data-{_UNSAFE_ATTR_NAME_CHARS.sub("_", str(key))}="{html.escape(str(value))}"')
            if "polygon" in block:
                polygon = _scale_points(block["polygon"], scale)
                data_attrs.append(f'data-polygon="{html.escape(json.dumps(polygon))}"')
            elif "multi_polygon" in block:
                multi_polygon = [_scale_points(polygon, scale) for polygon in block["multi_polygon"]]
                data_attrs.append(f'data-multi-polygon="{html.escape(json.dumps(multi_polygon))}"')

            id_attr = f' id="{html.escape(str(block["id"]))}"' if "id" in block else ""
            data_attr_str = (" " + " ".join(data_attrs)) if data_attrs else ""
            tag = "div" if hocr_class in ("ocr_carea", "ocr_par") else "span"
            text_content = html.escape(str(block.get("text", "")))

            output.append(
                f'    <{tag} class="{html.escape(hocr_class)}"{id_attr}{title_attr}{data_attr_str}>{text_content}</{tag}>'
            )

        output.append("  </div>")

    output.append("</body>\n</html>")
    return "\n".join(output)


def _parse_hocr_title(title: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for prop in title.split(";"):
        parts = prop.split()
        if not parts or parts[0] not in ("bbox", "x_wconf"):
            continue
        if parts[0] == "bbox":
            if len(parts) != 5 or "box" in result:
                raise ValueError("An hOCR title's bbox must be given once, as four numbers.")
            result["box"] = {
                "x": parse_number(parts[1]),
                "y": parse_number(parts[2]),
                "width": difference(parts[3], parts[1]),
                "height": difference(parts[4], parts[2]),
            }
        else:
            if len(parts) != 2 or "score" in result:
                raise ValueError("An hOCR title's x_wconf must be given once, as one number.")
            result["score"] = percentage(parts[1])
    return result


def _attribute_names(start_tag: str | None) -> dict[str, str]:
    if not start_tag:
        return {}
    body = _TAG_NAME.sub("", start_tag, count=1)
    return {match.group(1).lower(): match.group(1) for match in _ATTRIBUTE.finditer(body)}


def _flatten(chunks: list[Any]) -> tuple[str, int]:
    parts: list[str] = []
    visited = 0
    stack = [iter(chunks)]
    while stack:
        for chunk in stack[-1]:
            visited += 1
            if isinstance(chunk, str):
                parts.append(chunk)
            else:
                stack.append(iter(chunk))
                break
        else:
            stack.pop()
    return "".join(parts), visited


class _HOCRParser(HTMLParser):
    def __init__(self, target_class: str, *, max_text: int) -> None:
        super().__init__()
        self.target_class = target_class
        self.max_text = max_text
        self.block_text = 0
        self.searched = 0
        self.open_tags: Counter[str] = Counter()
        self.blocks: list[dict[str, Any]] = []
        self.page_width_map: dict[int, float] = {}
        self.page_height_map: dict[int, float] = {}
        self.page_count = 0
        self.current_page_num = 1
        self.hocr_elements = 0
        self.stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_ELEMENTS:
            if tag == "br" and self.stack:
                self.stack[-1]["text_chunks"].append(" ")
            return
        attr_dict = {k: v or "" for k, v in attrs}
        original_names = _attribute_names(self.get_starttag_text())
        classes = attr_dict.get("class", "").split()
        hocr_class = next((c for c in classes if c.startswith("ocr")), None)
        if hocr_class is not None:
            self.hocr_elements += 1

        if hocr_class == "ocr_page":
            self.page_count += 1
            if self.page_count > MAX_ITEMS:
                raise ValueError(f"The hOCR content has more than {MAX_ITEMS} pages.")
            match = _PAGE_NUMBER.search(attr_dict.get("id", ""))
            self.current_page_num = int(match.group()) if match else self.page_count
            title_data = _parse_hocr_title(attr_dict.get("title", ""))
            if "box" in title_data:
                self._set_page_size(self.page_width_map, title_data["box"]["width"])
                self._set_page_size(self.page_height_map, title_data["box"]["height"])

        if len(self.stack) >= _MAX_DEPTH:
            raise ValueError(f"The hOCR content leaves more than {_MAX_DEPTH:,} elements open.")
        self.open_tags[tag] += 1
        self.stack.append(
            {
                "tag": tag,
                "hocr_class": hocr_class,
                "attr_dict": attr_dict,
                "names": original_names,
                "text_chunks": [],
                "page_num": self.current_page_num,
            }
        )

    def _set_page_size(self, sizes: dict[int, float], size: float) -> None:
        if sizes.setdefault(self.current_page_num, size) != size:
            raise ValueError(f"The hOCR content gives page {self.current_page_num} two sizes.")

    def handle_data(self, data: str) -> None:
        if self.stack:
            self.stack[-1]["text_chunks"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.open_tags[tag]:
            return
        self.open_tags[tag] -= 1
        for i in reversed(range(len(self.stack))):
            self.searched += 1
            if self.searched > self.max_text:
                raise ValueError("The hOCR content leaves too many elements open.")
            if self.stack[i]["tag"] == tag:
                closed = self.stack.pop(i)
                if self.stack:
                    self.stack[-1]["text_chunks"].append(closed["text_chunks"])
                if closed["hocr_class"] == self.target_class:
                    text, visited = _flatten(closed["text_chunks"])
                    self.block_text += len(text) + visited
                    if self.block_text > self.max_text:
                        raise ValueError("The hOCR content nests its text too many times.")
                    clean_text = _WHITESPACE.sub(" ", text).strip()
                    if clean_text:
                        self._build_block(closed, clean_text)
                break

    def _build_block(self, element: dict[str, Any], text: str) -> None:
        if len(self.blocks) >= MAX_ITEMS:
            raise ValueError(f"The hOCR content has more than {MAX_ITEMS} blocks.")
        attr_dict = element["attr_dict"]
        title_data = _parse_hocr_title(attr_dict.get("title", ""))

        block: dict[str, Any] = {"block_type": "text", "text": text, "page_number": element["page_num"]}
        if "id" in attr_dict:
            block["id"] = attr_dict["id"]
        if "box" in title_data:
            block["box"] = title_data["box"]
        if "score" in title_data:
            block["score"] = title_data["score"]

        attributes: dict[str, Any] = {"hocr_class": element["hocr_class"]}
        for name, value in attr_dict.items():
            if not name.startswith("data-"):
                continue
            key = element["names"].get(name, name)[5:]
            if len(key) > MAX_KEY:
                raise ValueError(f"An hOCR attribute name is longer than {MAX_KEY} characters.")
            if name == "data-polygon":
                block["polygon"] = _geometry(value)
            elif name == "data-multi-polygon":
                block["multi_polygon"] = _geometry(value)
            else:
                attributes[key] = value
        for geometry in ("polygon", "multi_polygon"):
            if block.get(geometry) is None:
                block.pop(geometry, None)

        block["attributes"] = attributes
        self.blocks.append(block)


def _has_page_sizes(version: str | None) -> bool:
    import oatschema

    try:
        properties = oatschema.get_schema("document-extraction", version)["properties"]
    except LookupError:
        return True
    return "page_width" in properties and "page_height" in properties


def _geometry(value: str) -> Any:
    return load_json(value) if value.strip() else None


@checked
def from_hocr(
    hocr_content: str,
    *,
    producer: str = "hocr-adapter",
    validate: bool = True,
    schema_version: str | None = None,
    target_class: str = "ocr_line",
    on_bad_number: Literal["drop", "raise"] = "drop",
) -> ParsedRecord:
    """Parse an hOCR document into a ``document-extraction`` record, with one text block per ``target_class`` element.

    Each block gets the element's text, ``id``, ``bbox`` (as a pixel box), ``x_wconf`` (as a score) and page number.
    hOCR holds no ``line_number``. The record's ``producer`` is the option below, not the document's ``ocr-system``.
    Its attributes are the element's hOCR class and its ``data-*`` attributes, as strings, with their names'
    case kept. ``data-polygon`` and ``data-multi-polygon`` become the block's geometry. Page sizes come from each
    ``ocr_page``'s ``bbox``, unless ``schema_version`` is one without page sizes (0.4.0).

    Args:
        hocr_content: The hOCR document.
        producer: The record's ``producer``.
        validate: Check the record's numbers and validate it before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.
        target_class: The hOCR class whose elements become blocks, such as ``ocr_line``, ``ocrx_word`` or ``ocr_par``.
        on_bad_number: What ``oatschema.check_numbers`` does with a bad number in an optional property: ``"drop"``
            removes it and reports it in the result's ``dropped``, and ``"raise"`` rejects the record.

    Raises:
        ValueError: The content is empty, isn't hOCR, leaves more than 100,000 elements open, has more than 100,000 blocks or
            pages,
            has no non-empty ``target_class`` elements, gives a page two sizes, or has a ``bbox``, ``x_wconf`` or
            polygon that isn't a usable number or JSON.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    if not hocr_content.strip():
        raise ValueError("Provided hOCR content is empty.")

    parser = _HOCRParser(target_class=target_class, max_text=4 * len(hocr_content))
    parser.feed(hocr_content)
    parser.close()

    if parser.hocr_elements == 0:
        raise ValueError("The content has no hOCR elements (no element has an 'ocr_*' class).")
    if not parser.blocks:
        raise ValueError(f"The hOCR content has no {shorten(target_class)} elements with text.")

    record: dict[str, Any] = {"producer": producer, "extraction_type": "mixed", "unit": "px", "blocks": parser.blocks}
    if not _has_page_sizes(schema_version):
        parser.page_width_map.clear()
        parser.page_height_map.clear()
    if parser.page_width_map:
        record["page_width"] = [{"value": v, "pages": [k]} for k, v in parser.page_width_map.items()]
    if parser.page_height_map:
        record["page_height"] = [{"value": v, "pages": [k]} for k, v in parser.page_height_map.items()]

    return finish_parse(
        record, "document-extraction", validate=validate, version=schema_version, on_bad_number=on_bad_number
    )

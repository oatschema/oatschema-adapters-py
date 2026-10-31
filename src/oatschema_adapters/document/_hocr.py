# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import html
import json
import re
from html.parser import HTMLParser
from typing import Any

from oatschema_adapters._options import checked
from oatschema_adapters._validation import check_record, validate_record

_UNSAFE_ATTR_NAME_CHARS = re.compile(r"[\s\"'<>/=&\x00-\x1f\x7f]")
_ATTRIBUTE = re.compile(r"""([^\s"'<>/=]+)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?""")
_TAG_NAME = re.compile(r"<\s*[^\s/>]+")
_PAGE_NUMBER = re.compile(r"\d+")
_WHITESPACE = re.compile(r"\s+")
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
        schema_version: The schema version to validate against, such as ``"0.8.0"``. Defaults to the newest.

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
        if not parts:
            continue
        if parts[0] == "bbox" and len(parts) == 5:
            try:
                x0, y0, x1, y1 = map(float, parts[1:])
            except ValueError:
                continue
            result["box"] = {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
        elif parts[0] == "x_wconf" and len(parts) == 2:
            try:
                result["score"] = float(parts[1]) / 100.0
            except ValueError:
                continue
    return result


def _attribute_names(start_tag: str | None) -> dict[str, str]:
    if not start_tag:
        return {}
    body = _TAG_NAME.sub("", start_tag, count=1)
    return {match.group(1).lower(): match.group(1) for match in _ATTRIBUTE.finditer(body)}


class _HOCRParser(HTMLParser):
    def __init__(self, target_class: str) -> None:
        super().__init__()
        self.target_class = target_class
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
            match = _PAGE_NUMBER.search(attr_dict.get("id", ""))
            self.current_page_num = int(match.group()) if match else self.page_count
            title_data = _parse_hocr_title(attr_dict.get("title", ""))
            if "box" in title_data:
                self.page_width_map[self.current_page_num] = title_data["box"]["width"]
                self.page_height_map[self.current_page_num] = title_data["box"]["height"]

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

    def handle_data(self, data: str) -> None:
        if self.stack:
            self.stack[-1]["text_chunks"].append(data)

    def handle_endtag(self, tag: str) -> None:
        for i in reversed(range(len(self.stack))):
            if self.stack[i]["tag"] == tag:
                closed = self.stack.pop(i)
                full_text = "".join(closed["text_chunks"])
                if self.stack:
                    self.stack[-1]["text_chunks"].append(full_text)
                clean_text = _WHITESPACE.sub(" ", full_text).strip()
                if closed["hocr_class"] == self.target_class and clean_text:
                    self._build_block(closed, clean_text)
                break

    def _build_block(self, element: dict[str, Any], text: str) -> None:
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
            if name == "data-polygon":
                block["polygon"] = _json_or_none(value)
            elif name == "data-multi-polygon":
                block["multi_polygon"] = _json_or_none(value)
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


def _json_or_none(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


@checked
def from_hocr(
    hocr_content: str,
    *,
    producer: str = "hocr-adapter",
    validate: bool = True,
    schema_version: str | None = None,
    target_class: str = "ocr_line",
) -> dict[str, Any]:
    """Parse an hOCR document into a ``document-extraction`` record, with one text block per ``target_class`` element.

    Each block gets the element's text, ``id``, ``bbox`` (as a pixel box), ``x_wconf`` (as a score) and page number.
    Its attributes are the element's hOCR class and its ``data-*`` attributes, as strings, with their names'
    case kept. ``data-polygon`` and ``data-multi-polygon`` become the block's geometry. Page sizes come from each
    ``ocr_page``'s ``bbox``, unless ``schema_version`` is one without page sizes (0.4.0).

    Args:
        hocr_content: The hOCR document.
        producer: The record's ``producer``.
        validate: Validate the record before returning it.
        schema_version: The schema version to validate against. Defaults to the newest.
        target_class: The hOCR class whose elements become blocks, such as ``ocr_line``, ``ocrx_word`` or ``ocr_par``.

    Raises:
        ValueError: The content is empty, isn't hOCR, or has no non-empty ``target_class`` elements.
        oatschema.ValidationError: The parsed record doesn't conform to the schema.
    """
    if not hocr_content.strip():
        raise ValueError("Provided hOCR content is empty.")

    parser = _HOCRParser(target_class=target_class)
    parser.feed(hocr_content)
    parser.close()

    if parser.hocr_elements == 0:
        raise ValueError("The content has no hOCR elements (no element has an 'ocr_*' class).")
    if not parser.blocks:
        raise ValueError(f"The hOCR content has no {target_class!r} elements with text.")

    record: dict[str, Any] = {"producer": producer, "extraction_type": "mixed", "unit": "px", "blocks": parser.blocks}
    if not _has_page_sizes(schema_version):
        parser.page_width_map.clear()
        parser.page_height_map.clear()
    if parser.page_width_map:
        record["page_width"] = [{"value": v, "pages": [k]} for k, v in parser.page_width_map.items()]
    if parser.page_height_map:
        record["page_height"] = [{"value": v, "pages": [k]} for k, v in parser.page_height_map.items()]

    if validate:
        validate_record(record, "document-extraction", version=schema_version)
    return record

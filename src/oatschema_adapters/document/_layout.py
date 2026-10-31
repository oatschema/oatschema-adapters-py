# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

HYPHEN_CHARS = ("-", "\u0002", "\u00ad", "\u2010", "\u2013")


DEFAULT_LINE_TOLERANCE = 5.0
DEFAULT_PARAGRAPH_MARGIN = 20.0
DEFAULT_COLUMN_JUMP = -10.0


def _get_scale_factor(record: dict[str, Any], *, page_num: int | None = None) -> float:
    """Determines the scaling multiplier based on the schema unit."""
    unit = record.get("unit")
    if unit == "normalized":
        return 0.001
    if unit in ("px", "pt"):
        ph = record.get("page_height")
        height_val = None
        if isinstance(ph, int):
            height_val = ph
        elif isinstance(ph, list):
            if page_num is not None:
                for item in ph:
                    if page_num in item.get("pages", []):
                        height_val = item.get("value")
                        break
            if height_val is None and ph:
                height_val = ph[0].get("value")
        if isinstance(height_val, (int, float)) and height_val > 0:
            return height_val / 1000.0
    return 1.0


def _get_bounding_box(block: dict[str, Any]) -> dict[str, float] | None:
    """Extracts or computes a standard bounding box from any valid spatial block."""
    if "box" in block:
        b = block["box"]
        return {
            "x": float(b["x"]),
            "y": float(b["y"]),
            "width": float(b["width"]),
            "height": float(b["height"]),
        }

    pts = []
    if "polygon" in block:
        pts = block["polygon"]
    elif "multi_polygon" in block:
        for poly in block["multi_polygon"]:
            pts.extend(poly)

    if pts:
        xs = [float(p["x"]) for p in pts]
        ys = [float(p["y"]) for p in pts]
        return {
            "x": min(xs),
            "y": min(ys),
            "width": max(xs) - min(xs),
            "height": max(ys) - min(ys),
        }

    return None


def _union_boxes(boxes: list[dict[str, float] | None]) -> dict[str, float] | None:
    """Calculates the bounding box union of multiple boxes."""
    valid = [b for b in boxes if b is not None]
    if not valid:
        return None
    min_x = min(b["x"] for b in valid)
    min_y = min(b["y"] for b in valid)
    max_x = max(b["x"] + b["width"] for b in valid)
    max_y = max(b["y"] + b["height"] for b in valid)
    return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}


def get_page_dim(record: dict[str, Any], page_num: int, dim_key: str) -> float | None:
    """Safely extracts the dimension (width/height) for a specific page."""
    val = record.get(dim_key)
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, list):
        for item in val:
            if page_num in item.get("pages", []):
                return float(item.get("value"))
        if val:
            return float(val[0].get("value"))
    return None


def extract_spatial_pages(
    record: dict[str, Any],
    *,
    strict: bool = False,
    line_tolerance: float = DEFAULT_LINE_TOLERANCE,
    paragraph_margin: float = DEFAULT_PARAGRAPH_MARGIN,
    column_jump: float = DEFAULT_COLUMN_JUMP,
    scale: float | None = None,
) -> list[tuple[int, list[dict[str, Any]]]]:
    """
    1D Spatial Sorter: Processes blocks into stitched paragraphs, preserving
    both the model's reading order AND calculating absolute bounding boxes.
    """
    blocks = record.get("blocks", [])

    pages = []
    current_page_num = None

    current_paragraphs: list[dict[str, Any]] = []
    current_lines: list[dict[str, Any]] = []
    current_line_text: list[str] = []
    current_line_boxes: list[dict[str, float] | None] = []
    current_line_scores: list[float] = []
    current_line_attrs: list[dict[str, Any]] = []
    last_y = None

    def flush_line() -> None:
        if current_line_text:
            text = "".join(current_line_text)
            box = _union_boxes(current_line_boxes)
            score = min(current_line_scores) if current_line_scores else None
            attrs = next((a for a in current_line_attrs if a), {})

            current_lines.append({"text": text, "box": box, "score": score, "attributes": attrs})

            current_line_text.clear()
            current_line_boxes.clear()
            current_line_scores.clear()
            current_line_attrs.clear()

    def flush_paragraph() -> None:
        flush_line()
        if current_lines:
            para_text = (
                "\n".join([ln["text"] for ln in current_lines])
                if strict
                else " ".join([ln["text"] for ln in current_lines])
            )
            para_box = _union_boxes([ln["box"] for ln in current_lines])

            valid_scores = [ln["score"] for ln in current_lines if ln.get("score") is not None]
            para_score = min(valid_scores) if valid_scores else None
            para_attrs: dict[str, Any] = next((ln["attributes"] for ln in current_lines if ln.get("attributes")), {})

            current_paragraphs.append(
                {
                    "block_type": "text",
                    "text": para_text,
                    "lines": list(current_lines),
                    "box": para_box,
                    "score": para_score,
                    "attributes": para_attrs,
                }
            )
            current_lines.clear()

    for block in blocks:
        text = block.get("text")
        box = _get_bounding_box(block)
        page = block.get("page_number", 1)
        score = block.get("score")
        attrs = block.get("attributes", {})

        applied_scale = float(scale) if scale is not None else _get_scale_factor(record, page_num=page)
        scaled_line_tol = line_tolerance * applied_scale
        scaled_para_margin = paragraph_margin * applied_scale
        scaled_col_jump = column_jump * applied_scale

        if current_page_num is not None and page != current_page_num:
            flush_paragraph()
            if current_paragraphs:
                pages.append((current_page_num, current_paragraphs))
            current_paragraphs = []
            last_y = None

        current_page_num = page

        if not text or not isinstance(text, str):
            flush_paragraph()
            if box:
                current_paragraphs.append(
                    {
                        "block_type": block.get("block_type", "unknown"),
                        "text": "",
                        "box": box,
                        "score": score,
                        "attributes": attrs,
                    }
                )
            last_y = None
            continue

        text = text.strip()

        def append_to_line(t: str, b: dict[str, float] | None, s: float | None, a: dict[str, Any]) -> None:
            current_line_text.append(t)
            current_line_boxes.append(b)
            if s is not None:
                current_line_scores.append(s)
            if a:
                current_line_attrs.append(a)

        if box and "y" in box:
            y = box["y"]
            if last_y is not None:
                y_diff = y - last_y

                if y_diff < scaled_col_jump or y_diff > scaled_para_margin:
                    flush_paragraph()
                    append_to_line(text, box, score, attrs)
                elif y_diff > scaled_line_tol:
                    if strict:
                        flush_line()
                        append_to_line(text, box, score, attrs)
                    else:
                        if current_line_text and current_line_text[-1].endswith(HYPHEN_CHARS):
                            current_line_text[-1] = current_line_text[-1][:-1]
                            append_to_line(text, box, score, attrs)
                        else:
                            append_to_line(" " + text, box, score, attrs)
                else:
                    append_to_line(" " + text, box, score, attrs)
            else:
                append_to_line(text, box, score, attrs)
            last_y = y
        else:
            flush_paragraph()
            append_to_line(text, None, score, attrs)
            flush_paragraph()
            last_y = None

    flush_paragraph()
    if current_page_num is not None and current_paragraphs:
        pages.append((current_page_num, current_paragraphs))

    return pages


def xy_cut(nodes: list[dict[str, Any]], *, gap_y: float = -1.0, gap_x: float = -1.0) -> dict[str, Any]:
    """
    Recursively slices a list of spatial blocks into a 2D hierarchical layout tree.

    This algorithm projects bounding boxes onto the vertical (Y) and horizontal (X) axes
    to find physical gaps. It slices the document into rows, then slices those rows into
    columns, repeating until it isolates individual blocks (leaves).

    Args:
        nodes: A list of block dictionaries. Each block must contain a 'box' dictionary
               with 'x', 'y', 'width', and 'height' keys to be spatially sorted.
        gap_y: The minimum vertical gap required to slice a row. Defaults to -1.0 to
               absorb minor 1px overlapping errors typical in OCR bounding boxes.
        gap_x: The minimum horizontal gap required to slice a column. Defaults to -1.0.

    Returns:
        A dictionary representing the root node of the layout tree.
        The dictionary contains a 'type' key which determines its structure:
            - 'y-cut': A vertical stack of rows. Contains 'children'.
            - 'x-cut': A horizontal row of columns. Contains 'children'.
            - 'leaf': A single isolated block. Contains 'block'.
            - 'cluster': An irreducible group of blocks that overlap in both X and Y
                         directions (e.g., intersecting background text). Contains 'children'.
            - 'empty': Returned if the input list is empty.
    """
    if not nodes:
        return {"type": "empty"}
    if len(nodes) == 1:
        return {"type": "leaf", "block": nodes[0], "box": nodes[0].get("box")}

    union_box = _union_boxes([n.get("box") for n in nodes])

    nodes_y = sorted(nodes, key=lambda n: (n.get("box") or {}).get("y", 0))
    y_groups, curr_g = [], []
    curr_b = -1.0

    for n in nodes_y:
        b = n.get("box")
        if not b:
            curr_g.append(n)
            continue

        if not curr_g:
            curr_g.append(n)
            curr_b = b["y"] + b["height"]
        else:
            if b["y"] - curr_b >= gap_y:
                y_groups.append(curr_g)
                curr_g = [n]
                curr_b = b["y"] + b["height"]
            else:
                curr_g.append(n)
                curr_b = max(curr_b, b["y"] + b["height"])
    if curr_g:
        y_groups.append(curr_g)

    if len(y_groups) > 1:
        return {"type": "y-cut", "box": union_box, "children": [xy_cut(g, gap_y=gap_y, gap_x=gap_x) for g in y_groups]}

    nodes_x = sorted(nodes, key=lambda n: (n.get("box") or {}).get("x", 0))
    x_groups, curr_g = [], []
    curr_r = -1.0

    for n in nodes_x:
        b = n.get("box")
        if not b:
            curr_g.append(n)
            continue

        if not curr_g:
            curr_g.append(n)
            curr_r = b["x"] + b["width"]
        else:
            if b["x"] - curr_r >= gap_x:
                x_groups.append(curr_g)
                curr_g = [n]
                curr_r = b["x"] + b["width"]
            else:
                curr_g.append(n)
                curr_r = max(curr_r, b["x"] + b["width"])
    if curr_g:
        x_groups.append(curr_g)

    if len(x_groups) > 1:
        return {"type": "x-cut", "box": union_box, "children": [xy_cut(g, gap_y=gap_y, gap_x=gap_x) for g in x_groups]}

    nodes_sorted = sorted(nodes, key=lambda n: ((n.get("box") or {}).get("y", 0), (n.get("box") or {}).get("x", 0)))
    return {
        "type": "cluster",
        "box": union_box,
        "children": [{"type": "leaf", "block": n, "box": n.get("box")} for n in nodes_sorted],
    }

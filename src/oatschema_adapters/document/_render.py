# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import html

from typing import Any


def format_css_coords(box: dict[str, float], unit: str) -> str:
    """Translates schema units into absolute CSS positioning coordinates."""
    if unit == "normalized":
        return f"left: {box['x'] * 100}%; top: {box['y'] * 100}%; width: {box['width'] * 100}%; height: {box['height'] * 100}%;"
    elif unit == "per_mille":
        return f"left: {box['x'] / 10}%; top: {box['y'] / 10}%; width: {box['width'] / 10}%; height: {box['height'] / 10}%;"
    else:
        return f"left: {box['x']}px; top: {box['y']}px; width: {box['width']}px; height: {box['height']}px;"


def render_tree(node: dict[str, Any]) -> str:
    """Converts the layout tree into responsive Flexbox HTML."""
    ntype = node.get("type")
    if ntype == "empty":
        return ""

    if ntype == "leaf":
        block = node["block"]
        text = block.get("text", "")
        b_type = block.get("block_type", "text")
        if text:
            return f'<p class="block-text">{html.escape(text)}</p>'
        return f'<div class="figure-placeholder">[{html.escape(str(b_type))}]</div>'

    if ntype == "cluster":
        return "".join(render_tree(c) for c in node.get("children", []))

    box = node.get("box")
    children = node.get("children", [])

    if ntype == "y-cut":
        html_out = ['<div class="layout-y">']
        for c in children:
            html_out.append(render_tree(c))
        html_out.append("</div>")
        return "".join(html_out)

    if ntype == "x-cut":
        html_out = ['<div class="layout-x">']
        curr_x = box["x"] if box else 0
        parent_w = box["width"] if box and box["width"] > 0 else 1

        for c in children:
            c_box = c.get("box")
            if c_box:
                w_pct = (c_box["width"] / parent_w) * 100
                ml_pct = max(0, ((c_box["x"] - curr_x) / parent_w) * 100)
                style = f"width: {w_pct}%; margin-left: {ml_pct}%;"
                curr_x = c_box["x"] + c_box["width"]
            else:
                style = "flex: 1;"
            html_out.append(f'<div class="col" style="{style}">{render_tree(c)}</div>')
        html_out.append("</div>")
        return "".join(html_out)

    return ""

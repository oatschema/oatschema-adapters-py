# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from oatschema_adapters.document._render import format_css_coords, render_tree


def test_format_css_coords() -> None:
    """Test translation of the three different coordinate units into CSS strings."""

    box_px = {"x": 10.0, "y": 20.0, "width": 50.0, "height": 100.0}
    assert format_css_coords(box_px, "px") == "left: 10.0px; top: 20.0px; width: 50.0px; height: 100.0px;"

    box_norm = {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.9}
    assert format_css_coords(box_norm, "normalized") == "left: 10.0%; top: 20.0%; width: 50.0%; height: 90.0%;"

    box_pm = {"x": 100.0, "y": 200.0, "width": 500.0, "height": 900.0}
    assert format_css_coords(box_pm, "per_mille") == "left: 10.0%; top: 20.0%; width: 50.0%; height: 90.0%;"


def test_render_tree_empty() -> None:
    """Test the empty node fallback."""
    assert render_tree({"type": "empty"}) == ""


def test_render_tree_leaf_placeholder() -> None:
    """Test rendering a leaf node that lacks text, triggering the figure placeholder."""
    node = {"type": "leaf", "block": {"block_type": "image", "text": ""}}
    assert render_tree(node) == '<div class="figure-placeholder">[image]</div>'


def test_render_tree_cluster() -> None:
    """Test rendering an irreducible cluster of overlapping nodes."""
    child1 = {"type": "leaf", "block": {"block_type": "text", "text": "Layer A"}}
    child2 = {"type": "leaf", "block": {"block_type": "text", "text": "Layer B"}}
    node = {"type": "cluster", "children": [child1, child2]}

    result = render_tree(node)
    assert '<p class="block-text">Layer A</p>' in result
    assert '<p class="block-text">Layer B</p>' in result


def test_render_tree_x_cut_flex_fallback() -> None:
    """Test rendering columns where one column is missing a bounding box."""

    child_with_box = {"type": "leaf", "block": {"text": "Col 1"}, "box": {"x": 0, "y": 0, "width": 50, "height": 10}}

    child_no_box = {"type": "leaf", "block": {"text": "Col 2"}}

    node = {
        "type": "x-cut",
        "box": {"x": 0, "y": 0, "width": 100, "height": 10},
        "children": [child_with_box, child_no_box],
    }

    result = render_tree(node)
    assert 'style="width: 50.0%; margin-left: 0%;"' in result
    assert 'style="flex: 1;"' in result
    assert "Col 2" in result


def test_render_tree_unknown_type() -> None:
    """Test the absolute fallback for an unrecognized node type."""
    node = {"type": "unknown_magical_type"}
    assert render_tree(node) == ""

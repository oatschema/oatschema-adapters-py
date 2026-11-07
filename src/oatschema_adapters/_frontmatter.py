# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import json
import re
from collections.abc import Iterable
from typing import Any

from oatschema_adapters._numbers import MAX_KEY, load_json, parse_number

_UNSAFE = re.compile(r"[:#{}\[\],&*!|>'\"%@`\\\x00-\x1f\x7f\u0085\u2028\u2029\ufeff]")
_NUMBER_KEY = "duration"
_QUOTED_KEY = re.compile(r'("(?:[^"\\]|\\.)*"): (.*)')
_RESOLVES = re.compile(
    r"(?i:y|yes|n|no|true|false|on|off|null|~|[-+]?(\.inf|\.nan)|[-+]?0x[0-9a-f_]+|[-+]?[0-9][0-9_.,:eExXoObB+-]*|<<|=)"
)


def scalar(value: Any) -> str:
    """Return ``value`` as a YAML scalar that reads back as the same value."""
    if isinstance(value, str):
        plain = (
            value
            and value == value.strip()
            and (value[0].isalnum() or value[0] in "_(")
            and not _UNSAFE.search(value)
            and not _RESOLVES.fullmatch(value)
        )
        return value if plain else json.dumps(value)
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value)


def frontmatter(record: dict[str, Any], keys: Iterable[str]) -> str | None:
    """Return YAML frontmatter with the record's ``keys`` and ``attributes``, or ``None`` if it has none of them."""
    lines = ["---"]
    for key in keys:
        if key in record:
            lines.append(f"{key}: {scalar(record[key])}")
    attributes = record.get("attributes")
    if isinstance(attributes, dict):
        lines.append("attributes:")
        for name, value in attributes.items():
            lines.append(f"  {scalar(str(name))}: {json.dumps(value)}")
    lines.append("---")
    if len(lines) == 2:
        return None
    return "\n".join(lines)


def _read_scalar(text: str) -> Any:
    if text.startswith('"') or text in ("true", "false", "null"):
        return load_json(text)
    if _RESOLVES.fullmatch(text):
        try:
            return int(text)
        except ValueError:
            return text
    return text


def _read_number(text: str) -> int | float:
    return int(text) if text.isascii() and text.isdigit() else parse_number(text)


def _attribute(line: str) -> tuple[str, str]:
    if line.startswith('"'):
        match = _QUOTED_KEY.match(line)
        if match:
            return str(load_json(match.group(1))), match.group(2)
    name, _, value = line.partition(": ")
    return name, value


def read_frontmatter(text: str, keys: Iterable[str]) -> dict[str, Any]:
    """Return the ``keys`` and ``attributes`` that ``frontmatter`` wrote in ``text``, its lines between the ``---``.

    Raises:
        ValueError: A value has a number a double can't hold, an attribute isn't JSON, or a name is repeated.
    """
    wanted = set(keys)
    fields: dict[str, Any] = {}
    attributes: dict[str, Any] = {}
    in_attributes = False
    for line in text.splitlines():
        if line.startswith("  ") and in_attributes:
            name, value = _attribute(line[2:])
            if len(name) > MAX_KEY or name in attributes:
                raise ValueError("Frontmatter has an attribute name that is too long or repeated.")
            attributes[name] = load_json(value)
            continue
        key, separator, value = line.partition(":")
        in_attributes = key == "attributes" and not value.strip()
        if separator and key in wanted:
            if key in fields:
                raise ValueError(f"Frontmatter has {key!r} twice.")
            text = value.strip()
            fields[key] = _read_number(text) if key == _NUMBER_KEY else _read_scalar(text)
    if attributes:
        fields["attributes"] = attributes
    return fields

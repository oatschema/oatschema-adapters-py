# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import json
import re
from collections.abc import Iterable
from typing import Any

_UNSAFE = re.compile(r"[:#{}\[\],&*!|>'\"%@`\\\x00-\x1f\x7f\u0085\u2028\u2029\ufeff]")
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

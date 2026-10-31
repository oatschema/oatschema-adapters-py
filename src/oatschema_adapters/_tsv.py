# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import csv
import io
import re
from collections.abc import Iterable, Iterator
from typing import Any

_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", re.ASCII)
_ESCAPED = re.compile(r"'+[=+\-@\t\r]")


def neutralise(cell: object) -> str:
    """Return ``cell`` as text that spreadsheets won't run as a formula.

    A cell starting with ``=``, ``+``, ``-``, ``@``, a tab or a carriage return gets a leading ``'``, unless it is
    a plain number. So does one that already starts with ``'`` followed by one of those, so ``restore`` can undo it.
    """
    text = "" if cell is None else str(cell)
    if _ESCAPED.match(text) or (text.startswith(_TRIGGERS) and not _NUMBER.fullmatch(text)):
        return "'" + text
    return text


def restore(cell: str) -> str:
    """Undo ``neutralise``."""
    if _ESCAPED.match(cell):
        return cell[1:]
    return cell


def write(header: list[str], rows: Iterable[list[object]]) -> str:
    """Return a TSV table, with every cell passed through ``neutralise``."""
    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t")
    writer.writerow(header)
    for row in rows:
        writer.writerow([neutralise(cell) for cell in row])
    return output.getvalue()


def read(content: str) -> tuple[list[str], Iterator[dict[str, str]]]:
    """Return the header and rows of a TSV table, with every cell passed through ``restore``.

    Blank lines before the header and after the last row are ignored; a last row ending in empty cells keeps them.

    Raises:
        ValueError: The content is empty.
    """
    lines = content.lstrip("\r\n").rstrip("\r\n")
    if not lines.strip():
        raise ValueError("Provided TSV content is empty.")
    reader = csv.reader(io.StringIO(lines, newline=""), delimiter="\t")
    header = next(reader)

    def rows() -> Iterator[dict[str, str]]:
        for row in reader:
            if not row:
                continue
            cells = [restore(cell) for cell in row]
            cells += [""] * (len(header) - len(cells))
            yield dict(zip(header, cells, strict=False))

    return header, rows()

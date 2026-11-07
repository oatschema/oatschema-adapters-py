# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import csv
import io
import re
from collections.abc import Iterable

from oatschema_adapters._numbers import MAX_ITEMS


_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", re.ASCII)
_ESCAPED = re.compile(r"'+[=+\-@\t\r]")
_MAX_COLUMNS = 256
_CELL = r'(?:"(?:[^"]++|"")*+(?:"|\Z))?[^\t\r\n]*+'
_RECORD = re.compile(rf"[\r\n]*+{_CELL}(?:\t{_CELL}){{0,{_MAX_COLUMNS - 1}}}+")


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


def _has_a_wide_row(lines: str) -> bool:
    position = 0
    for _ in range(MAX_ITEMS + 2):
        match = _RECORD.match(lines, position)
        if match is None:
            return False
        position = match.end()
        if position >= len(lines):
            return False
        if lines[position] == "\t":
            return True
    return False


def read(content: str, columns: Iterable[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Return the header of a TSV table, and its rows as the named ``columns``, with cells passed through ``restore``.

    Blank lines before the header and after the last row are ignored; a last row ending in empty cells keeps them.
    Other columns, and cells past the end of the header, are ignored. Cells are limited by ``csv.field_size_limit``.

    Raises:
        ValueError: The content is empty, isn't a table, has a row of more than 256 cells, more than 100,000 rows or
            a cell over ``csv.field_size_limit``, or names one of ``columns`` twice.
    """
    lines = content.lstrip("\r\n").rstrip("\r\n")
    if not lines.strip():
        raise ValueError("Provided TSV content is empty.")
    wanted = set(columns)
    header: list[str] = []
    positions: list[tuple[str, int]] = []
    rows: list[dict[str, str]] = []
    problem = None
    if _has_a_wide_row(lines):
        raise ValueError(f"A TSV table can have at most {_MAX_COLUMNS} cells in a row.")
    try:
        for number, row in enumerate(csv.reader(io.StringIO(lines, newline=""), delimiter="\t")):
            if number == 0:
                header = row
                named = [name for name in header if name in wanted]
                if len(named) != len(set(named)):
                    raise ValueError("A TSV table names a column twice.")
                positions = [(name, index) for index, name in enumerate(header) if name in wanted]
            elif row:
                if len(rows) >= MAX_ITEMS:
                    raise ValueError(f"A TSV table can have at most {MAX_ITEMS} rows.")
                rows.append({name: restore(row[index]) if index < len(row) else "" for name, index in positions})
    except csv.Error as error:
        problem = str(error)
    if problem:
        raise ValueError(f"Failed to read the TSV table: {problem}")
    return header, rows

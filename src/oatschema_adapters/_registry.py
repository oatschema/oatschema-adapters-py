# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import importlib
import json
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import IO, Any

ExportFunction = Callable[..., Any]
ParseFunction = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class _Entry:
    schema: str
    format: str
    description: str
    extension: str
    export: str | ExportFunction | None
    parse: str | ParseFunction | None
    aliases: tuple[str, ...]


class Adapter:
    """Converts records of one schema to and from one format.

    Get one with ``get_adapter``. ``schema_id`` and ``format_name`` are the canonical names, whatever alias was
    asked for, and ``extension`` is the file extension without a leading dot (for example ``"hocr.html"``).
    """

    __slots__ = ("schema_id", "format_name", "description", "extension", "_export_fn", "_parse_fn")

    def __init__(
        self,
        schema_id: str,
        format_name: str,
        description: str,
        extension: str,
        export_fn: ExportFunction | None,
        parse_fn: ParseFunction | None,
    ) -> None:
        self.schema_id = schema_id
        self.format_name = format_name
        self.description = description
        self.extension = extension
        self._export_fn = export_fn
        self._parse_fn = parse_fn

    @property
    def can_export(self) -> bool:
        """Whether this adapter exports records."""
        return self._export_fn is not None

    @property
    def can_parse(self) -> bool:
        """Whether this adapter parses content into records."""
        return self._parse_fn is not None

    def export(self, record: dict[str, Any] | str | bytes, **options: Any) -> Any:
        """Convert ``record`` to this format and return the result, usually a str.

        ``record`` is a dict, or a JSON object as str or bytes. Options may be given as strings, as from a command
        line: ``validate="false"`` and ``low_confidence_threshold="0.5"`` are converted.

        Raises:
            NotImplementedError: this adapter only parses.
            ValueError: ``record`` is not valid JSON, or an option's string value can't be converted.
            TypeError: ``record`` is not a JSON object, or an option is unknown or has the wrong type.
            oatschema.ValidationError: the record doesn't conform to its schema.
        """
        if self._export_fn is None:
            raise NotImplementedError(f"exporting to {self.format_name!r} isn't supported for {self.schema_id!r}")
        if isinstance(record, (str, bytes)):
            try:
                record = json.loads(record)
            except json.JSONDecodeError as error:
                raise ValueError(f"the record is not valid JSON: {error}") from error
        if not isinstance(record, dict):
            raise TypeError(f"the record must be a JSON object, not {type(record).__name__}")
        return self._export_fn(record, **options)

    def parse(self, content: Any, **options: Any) -> dict[str, Any]:
        """Parse ``content`` in this format into a record, validated unless ``validate=False``.

        Raises:
            NotImplementedError: this adapter only exports.
            ValueError: ``content`` can't be parsed, or an option's string value can't be converted.
            TypeError: an option is unknown or has the wrong type.
            oatschema.ValidationError: the parsed record doesn't conform to its schema.
        """
        if self._parse_fn is None:
            raise NotImplementedError(f"parsing {self.format_name!r} isn't supported for {self.schema_id!r}")
        return self._parse_fn(content, **options)

    def export_file(self, record: dict[str, Any] | str | bytes, fp: IO[Any], **options: Any) -> None:
        """Export ``record`` and write the result to the file object ``fp``."""
        fp.write(self.export(record, **options))

    def parse_file(self, fp: IO[Any], **options: Any) -> dict[str, Any]:
        """Read the file object ``fp`` and parse its content into a record."""
        if self._parse_fn is None:
            raise NotImplementedError(f"parsing {self.format_name!r} isn't supported for {self.schema_id!r}")
        return self.parse(fp.read(), **options)

    def __repr__(self) -> str:
        return f"Adapter(schema_id={self.schema_id!r}, format_name={self.format_name!r})"


_lock = threading.RLock()
_entries: dict[tuple[str, str], _Entry] = {}
_aliases: dict[tuple[str, str], str] = {}


def _check_name(kind: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"the {kind} must be a str, not {type(value).__name__}")
    if not value or value != value.strip():
        raise ValueError(f"the {kind} must be a non-empty str without surrounding whitespace, not {value!r}")
    return value


def _check_target(kind: str, value: object) -> None:
    if value is None or callable(value):
        return
    if isinstance(value, str):
        module, sep, attribute = value.partition(":")
        if sep and module and attribute:
            return
    raise TypeError(f"{kind} must be a callable, a 'module:function' str, or None, not {value!r}")


def register_adapter(
    schema: str,
    format: str,
    *,
    description: str,
    extension: str,
    export: str | ExportFunction | None = None,
    parse: str | ParseFunction | None = None,
    aliases: Iterable[str] = (),
    replace: bool = False,
) -> None:
    """Register an adapter, so ``get_adapter``, ``list_formats`` and ``list_schemas`` include it.

    ``export`` and ``parse`` are callables, or ``"module:function"`` strings imported on first use, so registering
    doesn't import the adapter. At least one is required. ``export`` takes the record as its first argument and the
    options as keywords; ``parse`` takes the content first. ``aliases`` are other names for ``format`` within this
    schema. With ``replace=True`` an existing format is replaced, along with its aliases. ``schema`` may be any name: schemas other than OATS are allowed, and validating their records is up to
    the adapter.

    Raises:
        ValueError: ``format`` is already registered for ``schema`` and ``replace`` is false; ``format`` is an alias,
            or an alias is another format or another format's alias; or neither ``export`` nor ``parse`` is given.
        TypeError: an argument has the wrong type.
    """
    schema = _check_name("schema name", schema)
    format = _check_name("format name", format)
    if isinstance(aliases, str):
        raise TypeError(f"aliases must be a list of str, not the str {aliases!r}")
    alias_names = tuple(dict.fromkeys(_check_name("format alias", alias) for alias in aliases if alias != format))
    _check_name("description", description)
    _check_name("extension", extension)
    _check_target("export", export)
    _check_target("parse", parse)
    if export is None and parse is None:
        raise ValueError("an adapter needs an export or a parse function")

    entry = _Entry(schema, format, description, extension, export, parse, alias_names)
    with _lock:
        if (schema, format) in _aliases:
            raise ValueError(f"{format!r} is already an alias of {_aliases[(schema, format)]!r} for schema {schema!r}")
        for alias in alias_names:
            if (schema, alias) in _entries:
                raise ValueError(f"alias {alias!r} is already a format of schema {schema!r}")
            owner = _aliases.get((schema, alias))
            if owner is not None and owner != format:
                raise ValueError(f"alias {alias!r} already belongs to {owner!r} for schema {schema!r}")
        previous = _entries.get((schema, format))
        if previous is not None:
            if not replace:
                raise ValueError(f"{format!r} is already registered for schema {schema!r}; pass replace=True")
            for alias in previous.aliases:
                del _aliases[(schema, alias)]
        _entries[(schema, format)] = entry
        for alias in alias_names:
            _aliases[(schema, alias)] = format


def _resolve(schema: str, format: str) -> _Entry:
    if not isinstance(schema, str):
        raise TypeError(f"the schema name must be a str, not {type(schema).__name__}")
    if not isinstance(format, str):
        raise TypeError(f"the format name must be a str, not {type(format).__name__}")
    with _lock:
        canonical = _aliases.get((schema, format), format)
        entry = _entries.get((schema, canonical))
        if entry is not None:
            return entry
        known = sorted(fmt for sid, fmt in _entries if sid == schema)
    if not known:
        hint = ""
        if schema.startswith("open/"):
            hint = f"; OATS schema names have no 'open/' prefix: use {schema.removeprefix('open/')!r}"
        raise ValueError(f"no adapters for schema {schema!r}{hint}")
    raise ValueError(f"no {format!r} adapter for schema {schema!r}; formats: {', '.join(known)}")


def _load(target: str | Callable[..., Any] | None) -> Callable[..., Any] | None:
    if target is None or callable(target):
        return target
    module, _, attribute = target.partition(":")
    function = getattr(importlib.import_module(module), attribute)
    if not callable(function):
        raise TypeError(f"{target!r} is not callable")
    return function  # type: ignore[no-any-return]


def get_adapter(schema: str, format: str) -> Adapter:
    """Return the adapter for ``schema`` and ``format``, a format name or alias.

    The adapter's module is imported on first use, not when this package is imported.

    Raises:
        ValueError: nothing is registered for ``schema`` and ``format``. The message lists the schema's formats.
    """
    entry = _resolve(schema, format)
    return Adapter(
        schema_id=entry.schema,
        format_name=entry.format,
        description=entry.description,
        extension=entry.extension,
        export_fn=_load(entry.export),
        parse_fn=_load(entry.parse),
    )


def list_formats(schema: str) -> list[tuple[str, str]]:
    """Return ``(format, description)`` for each format of ``schema``, sorted by format, or ``[]`` if it has none."""
    with _lock:
        return sorted((entry.format, entry.description) for (sid, _), entry in _entries.items() if sid == schema)


def list_schemas() -> list[str]:
    """Return the name of every schema with at least one adapter, sorted."""
    with _lock:
        return sorted({schema for schema, _ in _entries})


def format_aliases(schema: str) -> dict[str, str]:
    """Return a dict mapping each format alias of ``schema`` to its format name."""
    with _lock:
        return {alias: fmt for (sid, alias), fmt in _aliases.items() if sid == schema}

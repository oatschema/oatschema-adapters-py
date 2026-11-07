# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import re
import warnings
from typing import Any, Literal

from oatschema import SchemaName

from oatschema_adapters._parsed import ParsedRecord

MAX_VALUES_TO_REPAIR = 250_000
_ITEMS = {"audio-transcription": "segments", "document-extraction": "blocks"}
_REPORTED_DROPS = 5
_AFTER_DROPPING = ", after dropping bad numbers at "


def check_record(record: Any, name: SchemaName, *, validate: bool, version: str | None) -> dict[str, Any]:
    """Return ``record`` after checking it is a dict and, if ``validate`` is true, that it conforms to ``name``.

    ``version`` is the schema version to validate against; ``None`` means ``oatschema``'s default.

    Raises:
        TypeError: ``record`` is not a dict.
        oatschema.ValidationError: the record doesn't conform.
        LookupError: ``version`` is not bundled with ``oatschema``.
    """
    if not isinstance(record, dict):
        raise TypeError(f"the record must be a dict, not {type(record).__name__}")
    if validate:
        validate_record(record, name, version=version)
    return record


def validate_record(record: dict[str, Any], name: SchemaName, *, version: str | None) -> None:
    """Raise ``oatschema.ValidationError`` unless ``record`` conforms to schema ``name`` at ``version``."""
    import oatschema

    oatschema.validate(record, name, version)


def _count_values(record: Any, limit: int) -> int:
    count = 0
    stack: list[Any] = [record]
    while stack:
        value = stack.pop()
        count += 1
        if count > limit:
            return count
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return count


def _has_more_values_than(record: Any, limit: int) -> bool:
    return _count_values(record, limit) > limit


def _too_large(name: SchemaName, version: str | None) -> Exception:
    import oatschema

    return oatschema.ValidationError(
        f"the record is invalid, and has more than {MAX_VALUES_TO_REPAIR} values, too many to say where",
        schema_name=name,
        schema_version=oatschema.get_validator(name, version).schema_version,
        path=(),
    )


def _groups(items: list[Any], limit: int) -> list[tuple[int, list[Any]]]:
    groups: list[tuple[int, list[Any]]] = []
    group: list[Any] = []
    start, size = 0, 0
    for index, item in enumerate(items):
        count = _count_values(item, limit)
        if group and size + count > limit:
            groups.append((start, group))
            group = []
            start, size = index, 0
        group.append(item)
        size += count
    if group:
        groups.append((start, group))
    return groups


def _pointer(path: tuple[Any, ...]) -> str:
    return "/" + "/".join(str(part) for part in path)


def _moved_message(message: str, key: str, start: int) -> str:
    head, found, tail = message.rpartition(_AFTER_DROPPING)
    if not found or not start:
        return message
    item = re.compile(rf"(^|, )/{re.escape(key)}/([0-9]+)(?=[/ ,]|$)")
    return head + found + item.sub(lambda match: f"{match.group(1)}/{key}/{int(match.group(2)) + start}", tail)


def _moved(path: tuple[Any, ...], key: str, start: int) -> tuple[Any, ...]:
    if len(path) >= 2 and path[0] == key and isinstance(path[1], int):
        return (key, path[1] + start, *path[2:])
    return path


def _check_in_groups(
    record: dict[str, Any],
    name: SchemaName,
    *,
    version: str | None,
    on_bad_number: Literal["drop", "raise"],
) -> ParsedRecord:
    import oatschema

    key = _ITEMS.get(name)
    items = record.get(key) if key else None
    if key is None or not isinstance(items, list) or not items:
        raise _too_large(name, version)
    rest = {field: value for field, value in record.items() if field != key}
    rest_values = _count_values(rest, MAX_VALUES_TO_REPAIR)
    if rest_values > MAX_VALUES_TO_REPAIR // 2:
        raise _too_large(name, version)
    rest_limit = MAX_VALUES_TO_REPAIR - rest_values
    dropped: list[Any] = []
    converted: list[Any] = []
    kept: list[Any] = []
    for start, group in _groups(items, rest_limit):
        if len(group) == 1 and _has_more_values_than(group[0], rest_limit):
            if not oatschema.is_valid({**rest, key: group}, name, version):
                raise _too_large(name, version)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", oatschema.DroppedNumberWarning)
                checked = oatschema.check_numbers({**rest, key: group}, name, version, on_bad_number=on_bad_number)
        except oatschema.ValidationError as error:
            raise oatschema.ValidationError(
                _moved_message(error.message, key, start),
                schema_name=error.schema_name,
                schema_version=error.schema_version,
                path=_moved(error.path, key, start),
                schema_path=error.schema_path,
            ) from None
        rest = {field: value for field, value in checked.record.items() if field != key}
        kept.extend(checked.record[key])
        dropped.extend(item._replace(path=_moved(item.path, key, start)) for item in checked.dropped)
        converted.extend(item._replace(path=_moved(item.path, key, start)) for item in checked.converted)
    result = {field: kept if field == key else rest[field] for field in record if field == key or field in rest}
    if not oatschema.is_valid(result, name, version):
        raise _too_large(name, version)
    if dropped:
        version_name = oatschema.get_validator(name, version).schema_version
        shown = ", ".join(f"{_pointer(item.path)} ({item.value!r:.100})" for item in dropped[:_REPORTED_DROPS])
        more = f" and {len(dropped) - _REPORTED_DROPS} more" if len(dropped) > _REPORTED_DROPS else ""
        warnings.warn(
            f"check_numbers dropped {len(dropped)} from a {name} {version_name} record: {shown}{more}",
            oatschema.DroppedNumberWarning,
            stacklevel=2,
        )
    return ParsedRecord(result, dropped=tuple(dropped), converted=tuple(converted))


def finish_parse(
    record: dict[str, Any],
    name: SchemaName,
    *,
    validate: bool,
    version: str | None,
    on_bad_number: Literal["drop", "raise"],
) -> ParsedRecord:
    """Return a parsed ``record``, after ``oatschema.check_numbers`` unless ``validate`` is false.

    An invalid ``audio-transcription`` or ``document-extraction`` record with more than 250,000 values is checked in
    groups of segments or blocks, each with the rest of the record and up to 250,000 values in all, because checking
    it whole can take gigabytes. It is rejected without saying where it is invalid, and no number is dropped from it,
    if it has no segments or blocks, if the rest of the record has more than 125,000 values, if a segment or block
    with the rest has more than 250,000, or if its groups are each valid but the whole isn't. So is an invalid record
    of another schema with more than 250,000 values.

    Raises:
        oatschema.ValidationError: the record doesn't conform, or has a number ``check_numbers`` rejects.
        LookupError: ``version`` is not bundled with ``oatschema``.
    """
    if not validate:
        return ParsedRecord(record)

    import oatschema

    if _has_more_values_than(record, MAX_VALUES_TO_REPAIR) and not oatschema.is_valid(record, name, version):
        return _check_in_groups(record, name, version=version, on_bad_number=on_bad_number)

    checked = oatschema.check_numbers(record, name, version, on_bad_number=on_bad_number)
    return ParsedRecord(checked.record, dropped=checked.dropped, converted=checked.converted)

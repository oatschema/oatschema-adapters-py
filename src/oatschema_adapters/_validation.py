# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Literal

from oatschema import SchemaName

from oatschema_adapters._parsed import ParsedRecord

MAX_VALUES_TO_REPAIR = 250_000


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


def _has_more_values_than(record: dict[str, Any], limit: int) -> bool:
    count = 0
    stack: list[Any] = [record]
    while stack:
        value = stack.pop()
        count += 1
        if count > limit:
            return True
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return False


def finish_parse(
    record: dict[str, Any],
    name: SchemaName,
    *,
    validate: bool,
    version: str | None,
    on_bad_number: Literal["drop", "raise"],
) -> ParsedRecord:
    """Return a parsed ``record``, after ``oatschema.check_numbers`` unless ``validate`` is false.

    An invalid record with more than 250,000 values is rejected before ``check_numbers``, and without saying where it
    is invalid, because finding that out can take gigabytes for such a record. No number is dropped from it.

    Raises:
        oatschema.ValidationError: the record doesn't conform, or has a number ``check_numbers`` rejects.
        LookupError: ``version`` is not bundled with ``oatschema``.
    """
    if not validate:
        return ParsedRecord(record)

    import oatschema

    if _has_more_values_than(record, MAX_VALUES_TO_REPAIR) and not oatschema.is_valid(record, name, version):
        raise oatschema.ValidationError(
            f"the record is invalid, and has more than {MAX_VALUES_TO_REPAIR} values, too many to say where",
            schema_name=name,
            schema_version=oatschema.get_validator(name, version).schema_version,
            path=(),
        )

    checked = oatschema.check_numbers(record, name, version, on_bad_number=on_bad_number)
    return ParsedRecord(checked.record, dropped=checked.dropped, converted=checked.converted)

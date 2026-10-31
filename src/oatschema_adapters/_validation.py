# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from oatschema import SchemaName


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

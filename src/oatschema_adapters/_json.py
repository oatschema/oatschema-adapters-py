# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import json
import typing
from collections.abc import Callable
from typing import Any, Literal

from oatschema import SchemaName

from oatschema_adapters._numbers import load_json
from oatschema_adapters._options import checked
from oatschema_adapters._parsed import ParsedRecord
from oatschema_adapters._validation import check_record, finish_parse


def _exporter(schema: SchemaName) -> Callable[..., str]:
    @checked
    def to_json(
        record: dict[str, Any],
        *,
        validate: bool = True,
        schema_version: str | None = None,
    ) -> str:
        """Convert a record to JSON text, indented by two spaces, with non-ASCII characters as they are.

        Args:
            record: The record to convert.
            validate: Validate the record before converting it.
            schema_version: The schema version to validate against, such as ``"0.9.0"``. Defaults to the newest.

        Raises:
            ValueError: The record has NaN or an infinity, which JSON can't hold.
            oatschema.ValidationError: The record doesn't conform to the schema.
        """
        check_record(record, schema, validate=validate, version=schema_version)
        return json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2)

    return to_json


def _parser(schema: SchemaName) -> Callable[..., ParsedRecord]:
    @checked
    def from_json(
        json_content: str | bytes,
        *,
        validate: bool = True,
        schema_version: str | None = None,
        on_bad_number: Literal["drop", "raise"] = "drop",
    ) -> ParsedRecord:
        """Parse JSON text into a record, as it is, keeping its ``producer``.

        Args:
            json_content: The JSON text.
            validate: Check the record's numbers and validate it before returning it.
            schema_version: The schema version to validate against. Defaults to the newest.
            on_bad_number: What ``oatschema.check_numbers`` does with a bad number in an optional property:
                ``"drop"`` removes it and reports it in the result's ``dropped``, and ``"raise"`` rejects the record.

        Raises:
            ValueError: The content isn't a JSON object, has ``NaN`` or ``Infinity``, repeats a key in an object,
                nests too deeply, or has a number that a double can't hold without rounding it.
            oatschema.ValidationError: The record doesn't conform to the schema.
        """
        record = load_json(json_content)
        if not isinstance(record, dict):
            raise ValueError(f"the content must be a JSON object, not {type(record).__name__}")
        return finish_parse(record, schema, validate=validate, version=schema_version, on_bad_number=on_bad_number)

    return from_json


def __getattr__(name: str) -> Callable[..., Any]:
    kind, _, schema = name.partition("_")
    schema = schema.replace("_", "-")
    if schema in typing.get_args(SchemaName):
        if kind == "to":
            return _exporter(typing.cast(SchemaName, schema))
        if kind == "from":
            return _parser(typing.cast(SchemaName, schema))
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

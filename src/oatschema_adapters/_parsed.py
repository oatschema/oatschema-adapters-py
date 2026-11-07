# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from oatschema import ConvertedNumber, DroppedNumber


class ParsedRecord(dict[str, Any]):
    """A parsed record: a dict, plus what ``oatschema.check_numbers`` changed on the way in.

    ``dropped`` lists the numbers removed from the record, and ``converted`` the values rewritten without changing
    what they mean. Both are empty if the parser was called with ``validate=False``, which doesn't check them.
    A plain ``dict(record)`` or ``record.copy()`` is an ordinary dict, without these attributes.
    """

    dropped: "tuple[DroppedNumber, ...]"
    converted: "tuple[ConvertedNumber, ...]"

    def __init__(
        self,
        record: Mapping[str, Any],
        *,
        dropped: "tuple[DroppedNumber, ...]" = (),
        converted: "tuple[ConvertedNumber, ...]" = (),
    ) -> None:
        super().__init__(record)
        self.dropped = dropped
        self.converted = converted

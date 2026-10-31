# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

"""Export OATS (Open Annotation Task Schemas) records to standard formats, and parse them back."""

from oatschema_adapters._builtin import register_builtin_adapters
from oatschema_adapters._registry import (
    Adapter,
    format_aliases,
    get_adapter,
    list_formats,
    list_schemas,
    register_adapter,
)

__version__ = "0.1.0"

__all__ = [
    "Adapter",
    "__version__",
    "format_aliases",
    "get_adapter",
    "list_formats",
    "list_schemas",
    "register_adapter",
]

register_builtin_adapters()

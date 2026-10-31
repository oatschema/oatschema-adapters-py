# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

"""Exporters and parsers for ``document-extraction`` records.

Each module is imported on first use.
"""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from oatschema_adapters.document._hocr import from_hocr, to_hocr
    from oatschema_adapters.document._html import to_html
    from oatschema_adapters.document._md import to_md
    from oatschema_adapters.document._tsv import from_tsv, to_tsv
    from oatschema_adapters.document._txt import from_txt, to_txt

_MODULES = {
    "from_hocr": "_hocr",
    "to_hocr": "_hocr",
    "to_html": "_html",
    "to_md": "_md",
    "from_tsv": "_tsv",
    "to_tsv": "_tsv",
    "from_txt": "_txt",
    "to_txt": "_txt",
}

__all__ = [
    "from_hocr",
    "from_tsv",
    "from_txt",
    "to_hocr",
    "to_html",
    "to_md",
    "to_tsv",
    "to_txt",
]


def __getattr__(name: str) -> Any:
    module = _MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f"{__name__}.{module}"), name)


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})

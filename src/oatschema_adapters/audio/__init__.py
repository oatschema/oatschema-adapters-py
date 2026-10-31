# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

"""Exporters and parsers for ``audio-transcription`` records.

Each module is imported on first use.
"""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from oatschema_adapters.audio._md import from_md, to_md
    from oatschema_adapters.audio._srt import from_srt, to_srt
    from oatschema_adapters.audio._tsv import from_tsv, to_tsv
    from oatschema_adapters.audio._txt import from_txt, to_txt
    from oatschema_adapters.audio._vtt import from_vtt, to_vtt

_MODULES = {
    "from_md": "_md",
    "to_md": "_md",
    "from_srt": "_srt",
    "to_srt": "_srt",
    "from_tsv": "_tsv",
    "to_tsv": "_tsv",
    "from_txt": "_txt",
    "to_txt": "_txt",
    "from_vtt": "_vtt",
    "to_vtt": "_vtt",
}

__all__ = [
    "from_md",
    "from_srt",
    "from_tsv",
    "from_txt",
    "from_vtt",
    "to_md",
    "to_srt",
    "to_tsv",
    "to_txt",
    "to_vtt",
]


def __getattr__(name: str) -> Any:
    module = _MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f"{__name__}.{module}"), name)


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})

# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

"""Export and parse one record of each schema with every installed adapter, validating each step.

Run it against an installed wheel, outside the source tree:

    uv run --isolated --no-project --python 3.11 --with dist/oatschema_adapters-0.1.0-py3-none-any.whl \\
        python -I scripts/smoke.py
"""

import json
import sys
from pathlib import Path

import oatschema

import oatschema_adapters
from oatschema_adapters import get_adapter, list_formats, list_schemas

DATA = Path(__file__).resolve().parent.parent / "tests" / "data"
RECORDS = {"audio-transcription": "audio-transcription-1.json", "document-extraction": "document-extraction-3.json"}


def main() -> int:
    location = Path(oatschema_adapters.__file__).resolve()
    print(
        f"oatschema-adapters {oatschema_adapters.__version__} from {location.parent}, Python {sys.version.split()[0]}"
    )
    if (Path(__file__).resolve().parent.parent / "src") in location.parents:
        print("imported from the source tree, not an installed wheel")
        return 1
    count = 0
    for schema in list_schemas():
        record = json.loads((DATA / RECORDS[schema]).read_text(encoding="utf-8"))
        for fmt, _ in list_formats(schema):
            adapter = get_adapter(schema, fmt)
            output = adapter.export(record)
            if adapter.can_parse:
                oatschema.validate(adapter.parse(output), schema)  # type: ignore[arg-type]
            print(f"{schema} {fmt}: ok")
            count += 1
    print(f"{count} adapters ok")
    return 0 if count == 10 else 1


if __name__ == "__main__":
    raise SystemExit(main())

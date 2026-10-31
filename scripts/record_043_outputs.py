# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

"""Record dorsalhub-adapters 0.4.3's output for every case in tests/golden_cases.py.

Run it in a throwaway environment that has dorsalhub-adapters 0.4.3 and no oatschema-adapters:

    uv run --isolated --no-project --with dorsalhub-adapters==0.4.3 python scripts/record_043_outputs.py

It writes tests/data/expected/: one file per export, one JSON file per parse of that export, and index.json with
the errors 0.4.3 raised. Records are exported and parsed with validate=False, so dorsalhub isn't needed.
"""

import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from golden_cases import EXTENSIONS, PARSE_FORMATS, export_cases  # noqa: E402

from dorsal_adapters.registry import get_adapter  # type: ignore[import-not-found]  # noqa: E402

DATA = ROOT / "tests" / "data"
OUT = DATA / "expected"


def main() -> None:
    version = importlib.metadata.version("dorsalhub-adapters")
    if version != "0.4.3":
        raise SystemExit(f"needs dorsalhub-adapters 0.4.3, found {version}")
    OUT.mkdir(exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()

    index: dict[str, Any] = {}
    for case_id, schema, fmt, fixture, options in export_cases():
        record = json.loads((DATA / f"{fixture}.json").read_text(encoding="utf-8"))
        adapter = get_adapter(schema, fmt)
        try:
            output = adapter.export(record, validate=False, **options)
        except Exception as error:
            index[case_id] = {"error": type(error).__name__, "message": str(error)}
            continue
        (OUT / f"{case_id}.{EXTENSIONS[fmt]}").write_bytes(output.encode("utf-8"))
        index[case_id] = {"error": None}

        if fmt in PARSE_FORMATS[schema]:
            parse_id = f"{case_id}.parsed"
            try:
                parsed = adapter.parse(output, validate=False)
            except Exception as error:
                index[parse_id] = {"error": type(error).__name__, "message": str(error)}
                continue
            text = json.dumps(parsed, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            (OUT / f"{parse_id}.json").write_bytes(text.encode("utf-8"))
            index[parse_id] = {"error": None}

    text = json.dumps(index, indent=2, sort_keys=True) + "\n"
    (OUT / "index.json").write_bytes(text.encode("utf-8"))
    print(f"recorded {len(index)} cases in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

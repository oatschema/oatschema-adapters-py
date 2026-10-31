# Contributing

The schemas themselves are maintained in [oatschema/oats](https://github.com/oatschema/oats), and bundled for Python by [oatschema](https://github.com/oatschema/oatschema-py). This repository holds the adapters that convert records to and from other formats. Bug reports and pull requests are welcome.

## Development

```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests scripts
```

`scripts/check.sh` runs all of these, with the tests on every supported Python version.

## Tests

- Every rule an adapter follows has tests on every path it applies to: export and parse, validated and unvalidated, and Python values and command-line strings.
- `tests/test_golden.py` compares every export, and the parse of each export, with the output recorded from `dorsalhub-adapters` 0.4.3, the package this one replaced, in `tests/data/expected/`. A case may differ only if it's listed in `CHANGED` with its reason. To add cases, edit `tests/golden_cases.py` and record them again in a throwaway environment:

  ```
  uv run --isolated --no-project --with dorsalhub-adapters==0.4.3 python scripts/record_043_outputs.py
  ```

- Fixtures in `tests/data/` are named `<schema>-<description>.json`, and invalid ones start with `invalid-`. Each adapter needs at least one fixture valid at every schema version `oatschema` bundles; `tests/test_versions.py` checks this.
- Coverage must stay at or above 80% overall, and 90% on each pull request's changed lines.

## Versions

The package version follows [semantic versioning](https://semver.org), independently of the schema versions. Until 1.0, a minor release may change the API and a patch release won't. Every release has a CHANGELOG entry saying what changed, and whether anything breaks.

## Licensing and sign-off

- The adapters are licensed under Apache-2.0, and contributions are accepted under the same licence. There is no CLA.
- Contributors keep the copyright in their contributions. Copyright is held by The OATS Authors, and you may add yourself or your employer to `AUTHORS`.
- Every commit needs a [Developer Certificate of Origin](https://developercertificate.org/) sign-off: commit with `git commit -s`.
- Every new source file (`.py`, `.toml`, `.yml`, `.sh`) starts with this header, which the tests check:

  ```
  # SPDX-FileCopyrightText: 2026 The OATS Authors
  # SPDX-License-Identifier: Apache-2.0
  ```

  Keep the year as it is in new files; it is the year the project started, not the current year.

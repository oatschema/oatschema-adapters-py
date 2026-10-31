#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

uv run ruff format --check .
uv run ruff check .
uv run mypy src tests scripts

for version in 3.11 3.12 3.13 3.14; do
  echo "--- pytest on Python $version ---"
  uv run --isolated --python="$version" pytest -q
done

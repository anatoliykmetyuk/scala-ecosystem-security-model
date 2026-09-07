#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest

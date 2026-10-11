#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/provenance_check.sh
uv run python scripts/check_imports.py
uv run python scripts/check_descriptions.py
uv lock --check
uv run ruff check .
echo "check_all: OK"

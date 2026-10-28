#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/provenance_check.sh
uv run python scripts/check_imports.py
uv run python scripts/check_descriptions.py
uv run python scripts/check_vocabulary.py
uv run python scripts/check_bench_rows.py
uv run python scripts/export_schemas.py --check
uv run python scripts/export_ddl.py --check
uv run python scripts/export_openapi.py --check
uv run python scripts/make_sim_devices.py --check
uv run python -m phantom.contract packages/qdt-sim/src/qdt_sim/devices/*.json | tail -n 1
uv lock --check
uv run ruff check .
echo "check_all: OK"

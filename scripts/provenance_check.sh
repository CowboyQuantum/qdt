#!/usr/bin/env bash
# Rule 7: the public repo names no real stand, lot, internal system, tolerance, or person.
set -euo pipefail
cd "$(dirname "$0")/.."
terms=$(grep -v '^#' scripts/provenance_terms.txt | grep -v '^\s*$' | paste -sd'|' -)
if grep -rn -i -E "($terms)" --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules --exclude=provenance_terms.txt . ; then
  echo "provenance_check: FAIL — matches above"; exit 1
fi
echo "provenance_check: OK"

#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  printf '%s\n' 'Set PLINK2_BOUNDARY_PANEL to the executable 22-chromosome synthetic fixture and PLINK2_BOUNDARY_EVIDENCE to a new output directory.'
  exit 0
fi
root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
: "${PLINK2_BOUNDARY_PANEL:?Explicit synthetic reference fixture required}"
: "${PLINK2_BOUNDARY_EVIDENCE:?New retained evidence directory required}"
command -v podman >/dev/null
command -v python3 >/dev/null
python3 -m unittest discover -s "$root/tests" -p test_boundaries.py -v

#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
: "${WGCNA_EVIDENCE:?Set a new evidence directory}"
: "${WGCNA_REFERENCE_LIBRARY:?Set the fresh author package library}"
if [[ -e "$WGCNA_EVIDENCE" || -L "$WGCNA_EVIDENCE" ]]; then
  printf 'Refusing to overwrite existing evidence\n' >&2
  exit 1
fi
mkdir -p -- "$WGCNA_EVIDENCE"
image=$(python -c 'import tomllib; print(tomllib.load(open("manifest.toml", "rb"))["image"]["reference"])')
python tests/run_wgcna_official_matrix.py --image "$image" \
  --reference-library "$WGCNA_REFERENCE_LIBRARY" --evidence "$WGCNA_EVIDENCE/official"
python tests/test_wgcna_boundaries.py --image "$image" \
  --fixture "$WGCNA_EVIDENCE/official/signed-pearson-split2/expression.tsv" \
  --evidence "$WGCNA_EVIDENCE/boundaries"

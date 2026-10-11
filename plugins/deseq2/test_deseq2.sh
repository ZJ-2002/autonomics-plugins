#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [[ "${1:-}" == -h || "${1:-}" == --help ]]; then
  printf '%s\n' 'Usage: DESEQ2_EVIDENCE=<new-directory> DESEQ2_REFERENCE_LIBRARY=<fresh-official-library> test_deseq2.sh' \
    'DESEQ2_IMAGE optionally overrides the immutable manifest image. No image build, missing-dependency skip or automatic evidence deletion.'
  exit 0
fi
: "${DESEQ2_EVIDENCE:?Specify a new evidence directory}"
: "${DESEQ2_REFERENCE_LIBRARY:?Specify an independently source-installed DESeq2/apeglm reference library}"
image=${DESEQ2_IMAGE:-$(python -c 'import sys,tomllib;print(tomllib.load(open(sys.argv[1],"rb"))["image"]["reference"])' "$root/manifest.toml")}
[[ "$image" =~ @sha256:[0-9a-f]{64}$ ]] || { echo 'Immutable image required' >&2; exit 1; }
mkdir "$DESEQ2_EVIDENCE"
podman run --rm --pull=never --network=none --entrypoint cat "$image" /opt/autonomics/deseq2_runner.R > "$DESEQ2_EVIDENCE/baked-source.R"
cmp "$root/deseq2_runner.R" "$DESEQ2_EVIDENCE/baked-source.R"
bash "$root/test_deseq2_fixture.sh" > "$DESEQ2_EVIDENCE/fixture.stdout.txt" 2> "$DESEQ2_EVIDENCE/fixture.stderr.txt"
DESEQ2_IMAGE="$image" bash "$root/test_deseq2_data_boundary.sh" > "$DESEQ2_EVIDENCE/data-boundary.stdout.txt" 2> "$DESEQ2_EVIDENCE/data-boundary.stderr.txt"
DESEQ2_BOUNDARY_IMAGE="$image" DESEQ2_BOUNDARY_BAKED=1 DESEQ2_BOUNDARY_EVIDENCE="$DESEQ2_EVIDENCE/boundaries" \
  python -m unittest discover -s "$root/tests" -p test_deseq2_boundaries.py -v \
  > "$DESEQ2_EVIDENCE/boundaries.stdout.txt" 2> "$DESEQ2_EVIDENCE/boundaries.stderr.txt"
DESEQ2_NUMERICAL_IMAGE="$image" DESEQ2_NUMERICAL_EVIDENCE="$DESEQ2_EVIDENCE/numerical" \
  python "$root/tests/run_official_matrix.py" > "$DESEQ2_EVIDENCE/numerical.stdout.txt" 2> "$DESEQ2_EVIDENCE/numerical.stderr.txt"
printf '%s\n' 'Technical checks completed; evidence retained. No scientific admission or deployment permission.'

#!/usr/bin/env bash
# singscore_bspec smoke: run scripts/singscore.sh inside the pinned image
# against the fixture set + golden produced by test_singscore_hostref.R
# (host official package, same version), and require the container scores
# to match the host golden at <=1e-12 per sample.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
image=$(python3 - "$root/manifest.toml" <<'PYEOF'
import sys,tomllib
with open(sys.argv[1], 'rb') as handle:
    print(tomllib.load(handle)['image']['reference'])
PYEOF
)
fixtures=${SIGNSCORE_FIXTURES:-/tmp/singscore_smoke}
out=$(mktemp -d /tmp/singscore-smoke.XXXXXX)
trap 'rm -rf "$out"' EXIT
mkdir -p "$out/run"
podman run --rm --pull=never --network=none --cpus=2 --memory=2g \
  -v "$fixtures":/work/fixtures:ro \
  -v "$root/scripts/singscore.sh":/work/singscore.sh:ro \
  -v "$out/run":/work/run \
  -e AUTONOMICS_INPUT0=/work/fixtures/matrix.tsv \
  -e AUTONOMICS_INPUT1=/work/fixtures/geneset.tsv \
  -e AUTONOMICS_INPUT2=/work/fixtures/samples.tsv \
  -e AUTONOMICS_OUTPUT0=/work/run/scores.tsv \
  -e AUTONOMICS_OUTPUT1=/work/run/singscore.RDS \
  -e AUTONOMICS_OUTPUT2=/work/run/singscore.log \
  --entrypoint Rscript "$image" /work/singscore.sh > "$out/stdout.log" 2>&1
python3 "$root/verify_scores.py" "$fixtures/host_golden.tsv" "$out/run/scores.tsv" "$out/run/singscore.log"

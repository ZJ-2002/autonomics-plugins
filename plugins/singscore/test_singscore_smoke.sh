#!/usr/bin/env bash
# singscore_bspec smoke: run scripts/singscore.sh inside the pinned image
# against the fixture set + golden produced by test_singscore_hostref.R
# (host official package, same version), and require the container scores
# to match the host golden at <=1e-12 per sample.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
image=${SIGNSCORE_IMAGE:-localhost/singscore-official:1.32.0}
fixtures=${SIGNSCORE_FIXTURES:-/tmp/singscore_smoke}
out=$(mktemp -d /tmp/singscore-smoke.XXXXXX)
trap 'rm -rf "$out"' EXIT
mkdir -p "$out/run"
podman run --rm --network=none \
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
python3 - "$fixtures/host_golden.tsv" "$out/run/scores.tsv" "$out/run/singscore.log" <<'PYEOF'
import csv,sys
gold={r["sample"]:float(r["TotalScore"]) for r in csv.DictReader(open(sys.argv[1]),delimiter="\t")}
got={r["sample"]:float(r["TotalScore"]) for r in csv.DictReader(open(sys.argv[2]),delimiter="\t")}
bad=[(s,gold[s],got.get(s)) for s in gold if abs(got.get(s,-1)-gold[s])>1e-12]
print("container-vs-host golden:", "PASS (all samples <=1e-12)" if not bad else f"FAIL {bad}")
import os
log_ok = os.path.getsize(sys.argv[3]) > 0 if len(sys.argv) > 3 else True
ok = (not bad) and log_ok
print("declared log port present:", log_ok)
sys.exit(0 if ok else 1)
PYEOF

#!/usr/bin/env bash
set -euo pipefail

: "${UCELL_H5AD_EVIDENCE:?Set a new evidence directory}"
: "${UCELL_H5AD_REFERENCE_R:?Set the independently source-installed UCell library}"
family=$(cd -- "$(dirname -- "$0")" && pwd)
plugins=$(dirname -- "$family")
image=$(python3 -c 'import pathlib,sys,tomllib;print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())["image"]["reference"])' "$family/manifest.toml")
test ! -e "$UCELL_H5AD_EVIDENCE"
test -f "$UCELL_H5AD_REFERENCE_R/UCell/DESCRIPTION"
test -f "$plugins/single-cell/tests/qc_compare.py"
mkdir -p -- "$UCELL_H5AD_EVIDENCE"
evidence=$(realpath -- "$UCELL_H5AD_EVIDENCE")
reference=$(realpath -- "$UCELL_H5AD_REFERENCE_R")
podman image inspect "$image" > "$evidence/image-inspect.json"

podman run --rm --pull=never --network=none --read-only --cpus=2 --memory=4g \
  --userns=keep-id --tmpfs /tmp:rw,size=512m --env PYTHONDONTWRITEBYTECODE=1 \
  --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$reference,dst=/reference,ro=true" \
  --mount "type=bind,src=$plugins,dst=/source,ro=true" \
  --entrypoint python "$image" /source/ucell-h5ad/tests/test_official.py \
  /proof/official --reference-library /reference \
  > "$evidence/official.stdout.txt" 2> "$evidence/official.stderr.txt"

podman run --rm --pull=never --network=none --read-only --cpus=2 --memory=4g \
  --userns=keep-id --tmpfs /tmp:rw,size=512m --env PYTHONDONTWRITEBYTECODE=1 \
  --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$plugins,dst=/source,ro=true" \
  --entrypoint python "$image" /source/ucell-h5ad/tests/test_boundaries.py \
  /proof/boundaries > "$evidence/boundaries.stdout.txt" 2> "$evidence/boundaries.stderr.txt"

podman run --rm --pull=never --network=none --read-only --cpus=1 --memory=2g \
  --userns=keep-id --tmpfs /tmp:rw,size=128m --env PYTHONDONTWRITEBYTECODE=1 \
  --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$plugins,dst=/source,ro=true" \
  --entrypoint python "$image" /source/ucell-h5ad/tests/test_comparison.py \
  /proof/official/dense /proof/comparison-mutants \
  > "$evidence/comparison-mutants.stdout.txt" 2> "$evidence/comparison-mutants.stderr.txt"

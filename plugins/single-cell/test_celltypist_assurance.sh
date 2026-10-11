#!/usr/bin/env bash
set -euo pipefail

: "${CELLTYPIST_EVIDENCE:?Set a new evidence directory}"
: "${CELLTYPIST_REFERENCE_LIBRARY:?Set the independently installed exact author stack}"
: "${CELLTYPIST_MODELS:?Set the frozen Pan-immune v2 model directory}"
family=$(cd -- "$(dirname -- "$0")" && pwd)
image=$(python3 -c 'import pathlib,sys,tomllib;print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())["image"]["reference"])' "$family/manifest.toml")
test ! -e "$CELLTYPIST_EVIDENCE"
test -f "$CELLTYPIST_REFERENCE_LIBRARY/celltypist/__init__.py"
test -f "$CELLTYPIST_REFERENCE_LIBRARY/scanpy/__init__.py"
test -f "$CELLTYPIST_MODELS/Immune_All_Low.pkl"
test -f "$CELLTYPIST_MODELS/Immune_All_High.pkl"
mkdir -p -- "$CELLTYPIST_EVIDENCE"
evidence=$(realpath -- "$CELLTYPIST_EVIDENCE")
reference=$(realpath -- "$CELLTYPIST_REFERENCE_LIBRARY")
models=$(realpath -- "$CELLTYPIST_MODELS")
extra_mounts=()
extra_arguments=()
if [[ -n "${CELLTYPIST_PBMC3K_FILE:-}" ]]; then
  benchmark=$(realpath -- "$CELLTYPIST_PBMC3K_FILE")
  test -f "$benchmark"
  extra_mounts=(--mount "type=bind,src=$benchmark,dst=/benchmark.h5ad,ro=true")
  extra_arguments=(--pbmc3k-file /benchmark.h5ad)
fi
podman image inspect "$image" > "$evidence/image-inspect.json"

podman run --rm --pull=never --network=none --read-only --cpus=2 --memory=4g \
  --userns=keep-id --tmpfs /tmp:rw,size=512m --env PYTHONDONTWRITEBYTECODE=1 \
  --env NUMBA_CACHE_DIR=/tmp/numba --env NUMBA_NUM_THREADS=1 \
  --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$reference,dst=/reference,ro=true" \
  --mount "type=bind,src=$models,dst=/models,ro=true" \
  --mount "type=bind,src=$family,dst=/source,ro=true" \
  "${extra_mounts[@]}" --entrypoint python "$image" /source/tests/test_celltypist_container.py \
  /proof/official --reference-library /reference --models /models "${extra_arguments[@]}" \
  > "$evidence/official.stdout.txt" 2> "$evidence/official.stderr.txt"

podman run --rm --pull=never --network=none --read-only --cpus=2 --memory=4g \
  --userns=keep-id --tmpfs /tmp:rw,size=512m --env PYTHONDONTWRITEBYTECODE=1 \
  --env NUMBA_CACHE_DIR=/tmp/numba --env NUMBA_NUM_THREADS=1 \
  --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$models,dst=/models,ro=true" \
  --mount "type=bind,src=$family,dst=/source,ro=true" \
  --entrypoint python "$image" /source/tests/test_celltypist_boundaries.py \
  /proof/boundaries --models /models \
  > "$evidence/boundaries.stdout.txt" 2> "$evidence/boundaries.stderr.txt"

#!/usr/bin/env bash
set -euo pipefail

: "${QC_EVIDENCE:?Set a new evidence directory}"
: "${QC_REFERENCE_LIBRARY:?Set a separately installed official Scanpy/AnnData library}"

family=$(cd -- "$(dirname -- "$0")" && pwd)
image=$(python3 -c 'import pathlib,sys,tomllib;print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())["image"]["reference"])' "$family/manifest.toml")
test ! -e "$QC_EVIDENCE"
test -f "$QC_REFERENCE_LIBRARY/scanpy/__init__.py"
test -f "$QC_REFERENCE_LIBRARY/anndata/__init__.py"
mkdir -p -- "$QC_EVIDENCE"
evidence=$(realpath -- "$QC_EVIDENCE")
reference=$(realpath -- "$QC_REFERENCE_LIBRARY")
podman image inspect "$image" > "$evidence/image-inspect.json"

podman run --rm --pull=never --network=none --read-only --cpus=2 --memory=3g \
  --userns=keep-id --tmpfs /tmp:rw,size=256m \
  --env PYTHONDONTWRITEBYTECODE=1 --env NUMBA_CACHE_DIR=/tmp/numba \
  --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$reference,dst=/reference,ro=true" \
  --mount "type=bind,src=$family,dst=/source,ro=true" \
  --entrypoint python "$image" /source/tests/test_qc_container.py \
  /proof/official --reference-library /reference \
  > "$evidence/official.stdout.txt" 2> "$evidence/official.stderr.txt"

podman run --rm --pull=never --network=none --read-only --cpus=2 --memory=3g \
  --userns=keep-id --tmpfs /tmp:rw,size=256m \
  --env PYTHONDONTWRITEBYTECODE=1 --env NUMBA_CACHE_DIR=/tmp/numba \
  --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$family,dst=/source,ro=true" \
  --entrypoint python "$image" /source/tests/test_qc_boundaries.py \
  /proof/boundaries > "$evidence/boundaries.stdout.txt" 2> "$evidence/boundaries.stderr.txt"

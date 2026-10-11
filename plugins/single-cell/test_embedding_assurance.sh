#!/usr/bin/env bash
set -euo pipefail

: "${EMBEDDING_EVIDENCE:?Set a new evidence directory}"
: "${EMBEDDING_REFERENCE_LIBRARY:?Set the independently installed exact author stack}"
family=$(cd -- "$(dirname -- "$0")" && pwd)
image=$(python3 -c 'import pathlib,sys,tomllib;print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())["image"]["reference"])' "$family/manifest.toml")
test ! -e "$EMBEDDING_EVIDENCE"
test -f "$EMBEDDING_REFERENCE_LIBRARY/scanpy/__init__.py"
test -f "$EMBEDDING_REFERENCE_LIBRARY/pynndescent/__init__.py"
mkdir -p -- "$EMBEDDING_EVIDENCE"
evidence=$(realpath -- "$EMBEDDING_EVIDENCE")
reference=$(realpath -- "$EMBEDDING_REFERENCE_LIBRARY")
podman image inspect "$image" > "$evidence/image-inspect.json"

podman run --rm --pull=never --network=none --read-only --cpus=2 --memory=4g \
  --userns=keep-id --tmpfs /tmp:rw,size=512m --env PYTHONDONTWRITEBYTECODE=1 \
  --env NUMBA_CACHE_DIR=/tmp/numba --env NUMBA_NUM_THREADS=1 \
  --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$reference,dst=/reference,ro=true" \
  --mount "type=bind,src=$family,dst=/source,ro=true" \
  --entrypoint python "$image" /source/tests/test_embedding_container.py \
  /proof/official --reference-library /reference \
  > "$evidence/official.stdout.txt" 2> "$evidence/official.stderr.txt"

podman run --rm --pull=never --network=none --read-only --cpus=2 --memory=3g \
  --userns=keep-id --tmpfs /tmp:rw,size=512m --env PYTHONDONTWRITEBYTECODE=1 \
  --env NUMBA_CACHE_DIR=/tmp/numba --env NUMBA_NUM_THREADS=1 \
  --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$family,dst=/source,ro=true" \
  --entrypoint python "$image" /source/tests/test_embedding_boundaries.py \
  /proof/boundaries > "$evidence/boundaries.stdout.txt" 2> "$evidence/boundaries.stderr.txt"

#!/usr/bin/env bash
set -euo pipefail

: "${SINGLE_CELL_EVIDENCE:?Set a new evidence directory; outputs are retained}"
: "${SINGLE_CELL_REFERENCE_LIBRARY:?Set the fresh official Scanpy/AnnData wheel installation directory}"

family=$(cd -- "$(dirname -- "$0")" && pwd)
image=$(python3 -c 'import pathlib,sys,tomllib;print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())["image"]["reference"])' "$family/manifest.toml")
test ! -e "$SINGLE_CELL_EVIDENCE"
test -f "$SINGLE_CELL_REFERENCE_LIBRARY/scanpy/__init__.py"
test -f "$SINGLE_CELL_REFERENCE_LIBRARY/anndata/__init__.py"
mkdir -p -- "$SINGLE_CELL_EVIDENCE"
evidence=$(realpath -- "$SINGLE_CELL_EVIDENCE")
reference=$(realpath -- "$SINGLE_CELL_REFERENCE_LIBRARY")
podman image inspect "$image" > "$evidence/image-inspect.json"

podman run --rm --pull=never --network=none --read-only --cpus=2 --memory=3g \
  --userns=keep-id --tmpfs /tmp:rw,size=256m \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$reference,dst=/reference,ro=true" \
  --mount "type=bind,src=$family,dst=/source,ro=true" \
  --entrypoint python "$image" /source/tests/test_preprocess_container.py \
  /proof/official --reference-library /reference \
  > "$evidence/official.stdout.txt" 2> "$evidence/official.stderr.txt"

podman run --rm --pull=never --network=none --read-only --cpus=2 --memory=3g \
  --userns=keep-id --tmpfs /tmp:rw,size=256m \
  --mount "type=bind,src=$evidence,dst=/proof" \
  --mount "type=bind,src=$family,dst=/source,ro=true" \
  --entrypoint python "$image" /source/tests/test_preprocess_boundaries.py \
  /proof/boundaries > "$evidence/boundaries.stdout.txt" 2> "$evidence/boundaries.stderr.txt"

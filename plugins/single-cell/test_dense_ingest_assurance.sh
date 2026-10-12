#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
: "${SC_DENSE_EVIDENCE:?Set a new writable evidence directory}"
: "${SC_DENSE_REFERENCE_LIBRARY:?Set the independently verified official Python prefix}"
if [[ -e "$SC_DENSE_EVIDENCE" ]]; then
    printf 'Evidence directory already exists: %s\n' "$SC_DENSE_EVIDENCE" >&2
    exit 2
fi
reference=$(cd -- "$SC_DENSE_REFERENCE_LIBRARY" && pwd)
mkdir -p -- "$SC_DENSE_EVIDENCE"
evidence=$(cd -- "$SC_DENSE_EVIDENCE" && pwd)
podman run --rm --pull=never --network=none --read-only --cpus=1 --memory=2g \
    --userns=keep-id --tmpfs /tmp:rw,size=512m \
    --env PYTHONDONTWRITEBYTECODE=1 --env OPENBLAS_NUM_THREADS=1 \
    --env NUMBA_CACHE_DIR=/tmp/numba --env SC_DENSE_REFERENCE_LIBRARY=/reference \
    --mount "type=bind,src=$root,dst=/source,ro=true" \
    --mount "type=bind,src=$reference,dst=/reference,ro=true" \
    --mount "type=bind,src=$evidence,dst=/proof" \
    ghcr.io/zj-2002/single-cell-preprocessor@sha256:e2f9fcd5ccf9e97b0f0129466df5abb21ae47ed32f123f6953b79fd83d915e20 \
    python3 /source/tests/test_dense_ingest_assurance.py /proof/cases \
    > "$evidence/tests.stdout.txt" 2> "$evidence/tests.stderr.txt"

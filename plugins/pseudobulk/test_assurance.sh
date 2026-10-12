#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
: "${PSEUDOBULK_EVIDENCE:?Set a new writable evidence directory}"
if [[ -e "$PSEUDOBULK_EVIDENCE" ]]; then
    printf 'Evidence directory already exists: %s\n' "$PSEUDOBULK_EVIDENCE" >&2
    exit 2
fi
mkdir -p -- "$PSEUDOBULK_EVIDENCE"
evidence=$(cd -- "$PSEUDOBULK_EVIDENCE" && pwd)
podman run --rm --pull=never --network=none --read-only --cpus=1 --memory=2g \
    --userns=keep-id --tmpfs /tmp:rw,size=256m \
    --env PYTHONDONTWRITEBYTECODE=1 --env OPENBLAS_NUM_THREADS=1 \
    --mount "type=bind,src=$root,dst=/source,ro=true" \
    --mount "type=bind,src=$evidence,dst=/proof" \
    ghcr.io/zj-2002/biotools-py@sha256:7ad6aeafa87672699d28b61b6bed12fc81fcdbfc43222a0abf17e2d56fb806f5 \
    python3 /source/tests/test_assurance.py /proof/cases \
    > "$evidence/tests.stdout.txt" 2> "$evidence/tests.stderr.txt"

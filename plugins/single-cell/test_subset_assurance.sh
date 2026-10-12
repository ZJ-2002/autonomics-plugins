#!/usr/bin/env bash
set -euo pipefail
family="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
evidence="${SUBSET_ASSURANCE_EVIDENCE:?set SUBSET_ASSURANCE_EVIDENCE to a new evidence directory}"
mkdir -p "$evidence"
image="ghcr.io/zj-2002/single-cell-preprocessor@sha256:e2f9fcd5ccf9e97b0f0129466df5abb21ae47ed32f123f6953b79fd83d915e20"
for mode in positive boundary; do
  podman run --rm --pull=never --network=none --read-only --cpus=1 --memory=2g \
    --userns=keep-id --tmpfs /tmp:rw,size=128m --env PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,src=$family,dst=/source,ro=true" \
    --mount "type=bind,src=$evidence,dst=/proof" --entrypoint python "$image" \
    /source/tests/test_subset_by_obs.py "/proof/$mode" "$mode" \
    > "$evidence/$mode.stdout.txt" 2> "$evidence/$mode.stderr.txt"
done
